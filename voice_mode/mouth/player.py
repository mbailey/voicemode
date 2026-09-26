"""The player: one resident process, one utterance at a time, in playlist order.

``say`` drops a mail into the queue maildir's ``new/`` (box.py) and makes
sure a player is running (the ``player.lock`` flock is held by whoever
plays); it never waits for the audio. Mail to mouth@<host> lands in the same
``new/``. The player takes the first line in play order (priority, then
arrival) to ``cur/``, synthesises, flags it when done (S spoken, T not, P
passed), and writes to the heard log:

- ``saying`` at the FIRST audio frame handed to the device:
  ``utt text voice backend device requested_ts gen_s``
- ``said`` when playback ends:
  ``utt played_s dur_s cut cut_at_s text_played_est underrun_s underruns
  reason`` (``underrun_s``: silence the device got mid-line because synthesis
  fell behind real time), where reason
  is ``done``, ``stop``, ``barge-in``, ``device-absent`` (not there at the
  start), ``device-lost`` (stopped taking audio mid-play) or ``error``.

``text_played_est`` is an ESTIMATE: the text cut at the played fraction of
the audio, back to a word boundary, until the backends give word timings.
``dur_s`` is absent when a cut came before synthesis finished.

A stop is a file, ``stop``: ``{"t": epoch, "reason": ..., "flush": bool}``.
It cuts every utterance requested at or before ``t`` (the one playing within
50 ms, and, with flush, the queued ones: each gets a ``said`` with
``played_s`` 0 and no ``saying``, so every requested utterance is accounted
for). A stop never touches an utterance requested after it.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from voice_mode import heard

from . import audio as _audio
from . import backends as _backends
from . import box as _box
from . import maillog
from . import output as _output
from . import hold as _hold
from .paths import mouth_dir


_SYNTH_KEYS = ("text", "voice", "speed", "backend", "file", "start", "end")


_duck: dict = {"prev": None, "ctl": None}


def _duck_on() -> None:
    """Lower the DJ's music while the mouth speaks ($VOICEMODE_MOUTH_DUCK, a volume 0-100).

    mpv stays its own stream: no mixing, just its volume, through the DJ's
    controller. Once per run of lines; _duck_off restores it when the queue
    is empty, so stacked lines don't pump the music between them.
    """
    level = os.environ.get("VOICEMODE_MOUTH_DUCK")
    if not level or _duck["prev"] is not None:
        return
    try:
        from voice_mode.dj import DJController

        ctl = DJController()
        prev = ctl.volume()
        if prev is not None and prev > int(level):
            ctl.volume(int(level))
            _duck.update(prev=prev, ctl=ctl)
    except Exception:  # noqa: BLE001 - no DJ, no ducking; never a reason not to speak
        pass


def _duck_off() -> None:
    if _duck["prev"] is None:
        return
    try:
        _duck["ctl"].volume(_duck["prev"])
    except Exception:  # noqa: BLE001
        pass
    finally:
        _duck.update(prev=None, ctl=None)


class _Cut(Exception):
    pass


def _abort(out) -> None:
    """Abort without trusting the device: a dead one may hang abort() too."""
    import threading

    t = threading.Thread(target=out.abort, daemon=True)
    t.start()
    t.join(1.0)


def _read_stop(d: Path) -> Optional[dict]:
    try:
        return json.loads((d / "stop").read_text())
    except (FileNotFoundError, ValueError):
        return None


def _log_dir(item: dict) -> Optional[Path]:
    return Path(item["log_dir"]) if item.get("log_dir") else None


def _common(item: dict) -> dict:
    return {"utt": item["utt"], "voice": item.get("voice"), "backend": item.get("backend"),
            "backend_asked": item.get("backend_asked"), "pan": item.get("pan"),
            "session": item.get("session"), "agent": item.get("agent"),
            "requested_ts": item.get("requested_ts"), "directory": _log_dir(item),
            "file": item.get("file"), "start": item.get("start"), "end": item.get("end"),
            "mail_id": item.get("mail_id"), "hold": item.get("hold"),
            "interest": item.get("interest"), "resume_of": item.get("resume_of"),
            "expires_t": item.get("expires_t")}


def text_at(text: str, fraction: float) -> str:
    """The text cut at ``fraction`` of its length, back to a word boundary."""
    if fraction >= 1.0:
        return text
    if fraction <= 0.0:
        return ""
    cut = int(len(text) * fraction)
    head = text[:cut]
    if cut < len(text) and not text[cut].isspace() and " " in head:
        head = head[: head.rfind(" ")]
    return head.rstrip()


def _said(item: dict, **fields) -> dict:
    rec = heard.said(**fields)
    maillog.entry(item, "said", rec)
    return rec


def _saying(item: dict, text: str, **fields) -> dict:
    rec = heard.saying(text, **fields)
    maillog.entry(item, "saying", rec)
    return rec


def said_unplayed(item: dict, reason: str, device: Optional[str] = None, detail: Optional[str] = None) -> dict:
    return _said(item, **_common(item), device=device or item.get("device"), played_s=0.0,
                 cut=True, cut_at_s=0.0, text_played_est="", reason=reason, detail=detail)


class Synth:
    """Synthesis in its own thread, running ahead of playback into a buffer.

    Playback reads the buffer, so synthesis never waits on the device. When
    one utterance's synthesis finishes, the player starts the NEXT one while
    this one is still playing (Cora, 20:43: stacked lines had 0.3 s of dead
    air between them, the next item's synthesis). One at a time on the TTS
    server, never two at once.
    """

    def __init__(self, item: dict, on_done=None) -> None:
        self.item = item
        self.utt = item["utt"]
        if item.get("file"):
            self.backend, self.voice = _backends.FileSound(item["file"], item.get("start"),
                                                           item.get("end")), ""
        else:
            self.backend, self.voice = _backends.resolve(item.get("backend") or "auto",
                                                         item.get("voice") or "af_sky")
        self.sample_rate = self.backend.sample_rate
        self.frames = 0
        self.t0 = time.monotonic()
        self.t_first: Optional[float] = None
        self.done = False
        self.finished = False  # every block synthesised: not cancelled first, no error
        self.error: Optional[BaseException] = None
        self._blocks: list = []
        self._cond = threading.Condition()
        self._cancel = threading.Event()
        self._on_done = on_done
        threading.Thread(target=self._run, daemon=True, name=f"synth-{self.utt}").start()

    def _run(self) -> None:
        gen = None
        try:
            gen = self.backend.stream(self.item["text"], self.voice, self.item.get("speed"))
            for block in gen:
                if self._cancel.is_set():
                    break
                with self._cond:
                    if self.t_first is None:
                        self.t_first = time.monotonic()
                    self._blocks.append(block)
                    self.frames += len(block)
                    self._cond.notify_all()
            else:
                self.finished = True
        except BaseException as e:  # noqa: BLE001 - surfaced to the player through blocks()
            self.error = e
        finally:
            if gen is not None:
                try:
                    gen.close()  # a cancel must not leave the request open
                except Exception:  # noqa: BLE001
                    pass
            with self._cond:
                self.done = True
                self._cond.notify_all()
        if self.finished and self._on_done and not self._cancel.is_set():
            try:
                self._on_done(self)
            except Exception:  # noqa: BLE001
                pass

    @property
    def gen_s(self) -> Optional[float]:
        return round(self.t_first - self.t0, 3) if self.t_first is not None else None

    def cancel(self) -> None:
        self._cancel.set()

    def snapshot(self) -> list:
        """The blocks synthesised so far (all of them once ``finished``)."""
        with self._cond:
            return list(self._blocks)

    def blocks(self, tick: float = _backends.BLOCK_S):
        """Yield audio blocks as they arrive; ``None`` every ``tick`` while waiting,
        so the player can look for a stop during a slow synthesis."""
        i = 0
        while True:
            with self._cond:
                if i >= len(self._blocks) and not self.done:
                    self._cond.wait(tick)
                if i < len(self._blocks):
                    block = self._blocks[i]
                    i += 1
                elif self.done:
                    if self.error is not None:
                        raise self.error
                    return
                else:
                    block = None
            yield block


def _cut_by_mail(q: "_box.Queue", item: dict) -> Optional[str]:
    """Why a mail that landed meanwhile cuts this line, if one does: a retract
    naming it (``retracted``), or a ``now`` line queued after it
    (``interrupted``). ``say --now`` and ``mouth retract`` cut at once instead."""
    for e in q.entries():
        if e["_retract"] and e["_sup"] and e["_sup"] == item.get("mail_id") and e["_allowed"]:
            return "retracted"
    for x in q.lines():
        if x.get("priority") == "now" and x["requested_t"] > item["requested_t"] and x["utt"] != item["utt"]:
            return "interrupted"
    return None


def play_one(item: dict, d: Path, synth: Optional[Synth] = None, prefetched: bool = False) -> dict:
    """Play one queued utterance; return its ``said`` record.

    ``synth`` is its synthesis if already started; ``prefetched`` says it was
    started while the previous utterance played (logged on ``saying``).
    """
    text, speed = item["text"], item.get("speed")
    if synth is None:
        try:
            synth = Synth(item)
        except Exception as e:  # noqa: BLE001 - a bad voice must still close the utterance
            return said_unplayed(item, "error", detail=str(e)[:300])
    backend = synth.backend
    if backend.name != item.get("backend"):  # log what ran; keep what was asked (auto)
        item = {**item, "backend": backend.name, "backend_asked": item.get("backend")}
    try:
        out = _output.open_output(item["device"], backend.sample_rate, item.get("pan"),
                                  meta={"text": text, "who": item.get("agent")})
    except Exception as e:  # noqa: BLE001 - absent, or PortAudio refusing to open it
        synth.cancel()
        detail = str(e) if isinstance(e, _output.DeviceAbsent) else f"{type(e).__name__}: {e}"
        return said_unplayed(item, "device-absent", detail=detail[:300])

    sr = backend.sample_rate
    step = int(sr * _backends.BLOCK_S)
    written = 0
    reason, detail = "done", None
    started = False

    first_frame_t = None
    barge_here = _hold.barge_device(getattr(out, "name", item["device"]))
    nq = _box.Queue(d)
    next_look = [0.0]

    def check_stop() -> None:
        nonlocal reason
        if time.monotonic() >= next_look[0]:
            next_look[0] = time.monotonic() + 0.1
            why = None if (d / "stop").exists() else _cut_by_mail(nq, item)
            if why:
                _write_stop(d, {"t": time.time(), "reason": why, "flush": False, "utt": item["utt"]})
        if first_frame_t is not None and barge_here:
            est = max(synth.frames / sr, len(text) / 15.0 / (speed or 1.0))
            words = _hold.barge(first_frame_t, _hold.near(text, written / sr, est),
                                sources=_hold.sources_for(item["device"]))
            if words is not None:
                # His words cut the line, and every line queued before them
                # (stale now); an opener queued after them survives.
                _write_stop(d, {"t": _hold._ts(words) or time.time(), "reason": "barge-in",
                                "flush": True, "heard": str(words.get("text") or "")[:120]})
        stop = _read_stop(d)
        if not stop:
            return
        # A stop aimed at one line (retract, --now) cuts only that line;
        # a general stop cuts every line requested at or before it.
        hit = stop["utt"] == item["utt"] if stop.get("utt") else stop.get("t", 0) >= item["requested_t"]
        if hit:
            reason = stop.get("reason") or "stop"
            raise _Cut

    try:
        for block in synth.blocks():
            if block is None:
                check_stop()
                continue
            for i in range(0, len(block), step):
                check_stop()
                if not started:
                    first_frame_t = time.time()
                    _duck_on()
                    _saying(item, text, **_common(item), device=getattr(out, "name", item["device"]),
                                 speed=speed, gen_s=synth.gen_s, prefetched=prefetched or None,
                                 pan_ignored=getattr(out, "pan_ignored", None))
                    started = True
                sub = block[i:i + step]
                out.write(sub)
                written += len(sub)
        out.drain()
    except _Cut:
        synth.cancel()
        _abort(out)
    except Exception as e:  # noqa: BLE001
        synth.cancel()
        try:
            _abort(out)
        except Exception:  # noqa: BLE001
            pass
        name = type(e).__name__
        lost = isinstance(e, _output.DeviceLost) or "PortAudio" in name
        reason = "device-lost" if lost else "error"
        detail = f"{name}: {e}"[:300]

    cut = reason != "done"
    played = getattr(out, "frames_played", written) / sr
    if cut:
        played = max(0.0, played - getattr(out, "latency", 0.0))
    dur = synth.frames / sr if synth.finished else None
    est_dur = dur or max(synth.frames / sr, len(text) / 15.0 / (speed or 1.0))
    # The mouth keeps what it says (audio.py): the whole line, once its
    # synthesis finished, even if the playback was cut.
    kept = _audio.keep(item, synth.snapshot(), sr, backend.name) if synth.finished else None
    return _said(
        item, **_common(item), device=getattr(out, "name", item["device"]),
        audio=str(kept) if kept else None,
        played_s=round(played, 3), dur_s=round(dur, 3) if dur is not None else None,
        cut=cut, cut_at_s=round(played, 3) if cut else None,
        text_played_est=text if not cut else text_at(text, played / est_dur if est_dur else 0.0),
        underrun_s=round(getattr(out, "underrun_frames", 0) / sr, 3),
        underruns=getattr(out, "underruns", 0),
        reason=reason, detail=detail)


def _next(d: Path, q: "_box.Queue") -> tuple[Optional[dict], bool]:
    """The first line that may play now, and whether any line is held back.

    A held line (hold.py) keeps its place and is skipped while he talks; a
    line past its expiry is filed P with ``said reason=expired``, and a held
    line queued before his turn began is filed P with ``reason=stale`` (kept,
    never spoken: Mike 03:07-03:12 Sat). Lines with neither just play.
    """
    held = False
    for x in q.lines(act=True, playing=_read_playing(d)):
        if not x.get("hold") and x.get("expires_t") is None:
            return x, held
        verdict = _hold.check(x)
        if verdict == "play":
            return x, held
        if verdict in ("expire", "stale"):
            if q.drop_line(x, "P"):
                item = _box.public(x)
                _done(d, item, said_unplayed(item, "expired" if verdict == "expire" else "stale"))
            continue
        held = True
    return None, held


def _read_playing(d: Path) -> Optional[dict]:
    try:
        return json.loads((d / "playing.json").read_text())
    except (FileNotFoundError, ValueError):
        return None


def _flags(rec: dict) -> str:
    """S if any of it was heard; P if it passed its moment; else T."""
    if (rec.get("played_s") or 0) > 0:
        return "S"
    return "P" if rec.get("reason") in ("expired", "stale") else "T"


def _resume(d: Path, item: dict, rec: dict) -> None:
    """The fast follow (Mike, 02:08 Sat; Cora's split): a line his words cut is
    queued again from the start of the sentence it was cut in, HELD for the
    end of his turn and expiring in resume_s(). A short turn then hears it
    with no agent round trip; its agent may amend or retract it meanwhile
    (``resume_of`` names the cut line)."""
    if _hold.resume_s() <= 0 or item.get("backend") == "file":
        return
    rest = _hold.rest_of(item["text"], rec.get("text_played_est") or "")
    if not rest:
        return
    from . import say

    try:
        say(rest, voice=item.get("voice"), speed=item.get("speed"),
            backend=item.get("backend_asked") or item.get("backend"), device=item.get("device"),
            pan=item.get("pan"), log_dir=Path(item["log_dir"]) if item.get("log_dir") else None,
            d=d, spawn=False, hold="turn-end", expires_s=_hold.resume_s(),
            extra={"agent": item.get("agent"), "session": item.get("session"),
                   "resume_of": item["utt"]})
    except (ValueError, OSError) as e:  # a resume must never stall the player
        print(json.dumps({"resume_failed": item["utt"], "error": str(e)[:200]}), flush=True)


def _write_stop(d: Path, rec: dict) -> None:
    """The player's own stop (barge-in): the same file `mouth stop` writes."""
    part = d / f".stop.player.{os.getpid()}.part"
    part.write_text(json.dumps(rec))
    part.rename(d / "stop")


def _handle_stop(d: Path, q: "Optional[_box.Queue]" = None) -> None:
    """After a cut or while idle: flush what the stop covers, then retire it."""
    stop = _read_stop(d)
    if not stop:
        return
    if stop.get("flush", True) and not stop.get("utt"):
        q = q or _box.Queue(d)
        for x in q.lines():
            if x.get("requested_t", 0) <= stop.get("t", 0) and q.drop_line(x, "T"):
                item = _box.public(x)
                _done(d, item, said_unplayed(item, stop.get("reason") or "stop"))
    (d / "stop").unlink(missing_ok=True)


def _done(d: Path, item: dict, rec: dict) -> None:
    if item.get("wait"):
        p = d / "done" / f"{item['utt']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec))
        tmp.rename(p)


def serve(d: Optional[Path] = None, idle_exit_s: Optional[float] = None, poll_s: float = 0.02) -> int:
    """Play the queue until it has been empty ``idle_exit_s``. 0 if another player holds the lock."""
    d = d or mouth_dir()
    d.mkdir(parents=True, exist_ok=True)
    q = _box.Queue(d)
    _box.ensure(q.bx)
    pq = _box.Queue(d)  # prefetch's own view (it runs on synth threads too)
    if idle_exit_s is None:
        idle_exit_s = float(os.environ.get("VOICEMODE_MOUTH_IDLE_S", "600"))
    while True:
        lock_fd = os.open(str(d / "player.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock_fd)
            return 0
        (d / "player.pid").write_text(str(os.getpid()))
        idle_since = time.monotonic()
        ahead: dict = {"synth": None, "playing": None}
        guard = threading.Lock()

        def prefetch(_finished: Optional[Synth] = None) -> None:
            """Start synthesising the next queued item, one ahead, never the one playing."""
            with guard:
                if ahead["synth"] is not None:
                    return
                for x in pq.lines():
                    item = _box.public(x)
                    if item.get("utt") == ahead["playing"]:
                        continue
                    try:
                        ahead["synth"] = Synth(item, on_done=prefetch)
                    except Exception:  # noqa: BLE001 - play_one reports it when its turn comes
                        pass
                    return

        try:
            while True:
                f, held = _next(d, q)
                if f is None and held:
                    # Lines wait for the end of his turn: keep their synthesis
                    # warm, honour a stop, and do not idle out.
                    _handle_stop(d, q)
                    prefetch()
                    idle_since = time.monotonic()
                    time.sleep(poll_s)
                    continue
                if f is None:
                    _duck_off()
                    with guard:
                        if ahead["synth"] is not None:  # its item was flushed by a stop
                            ahead["synth"].cancel()
                            ahead["synth"] = None
                    _handle_stop(d, q)
                    if time.monotonic() - idle_since > idle_exit_s:
                        break
                    time.sleep(poll_s)
                    continue
                item = _box.public(f)
                with guard:
                    synth, ahead["synth"] = ahead["synth"], None
                    ahead["playing"] = item.get("utt")
                if synth is not None and (synth.utt != item.get("utt") or any(
                        synth.item.get(k) != item.get(k) for k in _SYNTH_KEYS)):  # amended
                    synth.cancel()
                    synth = None
                playing = d / "playing.json"
                taken = q.take(f)
                if taken is None:  # retracted or flushed meanwhile
                    if synth is not None:
                        synth.cancel()
                    continue
                tmp = d / ".playing.json.part"
                tmp.write_text(json.dumps({**item, "box_file": str(taken)}))
                tmp.rename(playing)
                if synth is None:
                    try:
                        synth = Synth(item, on_done=prefetch)
                    except Exception:  # noqa: BLE001 - play_one makes the said line
                        synth = None
                    prefetched = False
                else:
                    prefetched = True
                if synth is not None and synth.finished:
                    prefetch()
                try:
                    rec = play_one(item, d, synth, prefetched)
                except Exception as e:  # noqa: BLE001 - one bad utterance must not stall the queue
                    rec = said_unplayed(item, "error", detail=f"{type(e).__name__}: {e}"[:300])
                _box.file_to(taken, _flags(rec))
                playing.unlink(missing_ok=True)
                _done(d, item, rec)
                if rec.get("cut"):
                    _handle_stop(d, q)
                if rec.get("reason") == "barge-in":
                    _resume(d, item, rec)
                print(json.dumps({k: rec.get(k) for k in ("seq", "utt", "reason", "played_s", "dur_s")}),
                      flush=True)
                idle_since = time.monotonic()
        finally:
            (d / "player.pid").unlink(missing_ok=True)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        # A say that landed while we were letting go saw the lock held and did
        # not start a player: look once more before leaving.
        if not q.lines():
            return 0


if __name__ == "__main__":
    sys.exit(serve())
