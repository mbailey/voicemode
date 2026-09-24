"""The player: one resident process, one utterance at a time, oldest first.

``say`` drops a JSON file into ``queue/`` and makes sure a player is running
(the ``player.lock`` flock is held by whoever plays); it never waits for
the audio. The player takes the oldest file, synthesises, and writes to the
heard log:

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

from . import backends as _backends
from . import maillog
from . import output as _output
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
            "mail_id": item.get("mail_id")}


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
        out = _output.open_output(item["device"], backend.sample_rate, item.get("pan"))
    except Exception as e:  # noqa: BLE001 - absent, or PortAudio refusing to open it
        synth.cancel()
        detail = str(e) if isinstance(e, _output.DeviceAbsent) else f"{type(e).__name__}: {e}"
        return said_unplayed(item, "device-absent", detail=detail[:300])

    sr = backend.sample_rate
    step = int(sr * _backends.BLOCK_S)
    written = 0
    reason, detail = "done", None
    started = False

    def check_stop() -> None:
        nonlocal reason
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
    return _said(
        item, **_common(item), device=getattr(out, "name", item["device"]),
        played_s=round(played, 3), dur_s=round(dur, 3) if dur is not None else None,
        cut=cut, cut_at_s=round(played, 3) if cut else None,
        text_played_est=text if not cut else text_at(text, played / est_dur if est_dur else 0.0),
        underrun_s=round(getattr(out, "underrun_frames", 0) / sr, 3),
        underruns=getattr(out, "underruns", 0),
        reason=reason, detail=detail)


def _oldest(q: Path) -> Optional[Path]:
    files = sorted(q.glob("*.json"))
    return files[0] if files else None


def _handle_stop(d: Path) -> None:
    """After a cut or while idle: flush what the stop covers, then retire it."""
    stop = _read_stop(d)
    if not stop:
        return
    if stop.get("flush", True) and not stop.get("utt"):
        for f in sorted((d / "queue").glob("*.json")):
            try:
                item = json.loads(f.read_text())
            except (FileNotFoundError, ValueError):
                continue
            if item.get("requested_t", 0) <= stop.get("t", 0):
                f.unlink(missing_ok=True)
                rec = said_unplayed(item, stop.get("reason") or "stop")
                _done(d, item, rec)
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
    q = d / "queue"
    q.mkdir(parents=True, exist_ok=True)
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
                for f in sorted(q.glob("*.json")):
                    try:
                        item = json.loads(f.read_text())
                    except (FileNotFoundError, ValueError):
                        continue
                    if item.get("utt") == ahead["playing"]:
                        continue
                    try:
                        ahead["synth"] = Synth(item, on_done=prefetch)
                    except Exception:  # noqa: BLE001 - play_one reports it when its turn comes
                        pass
                    return

        try:
            while True:
                f = _oldest(q)
                if f is None:
                    _duck_off()
                    with guard:
                        if ahead["synth"] is not None:  # its item was flushed by a stop
                            ahead["synth"].cancel()
                            ahead["synth"] = None
                    _handle_stop(d)
                    if time.monotonic() - idle_since > idle_exit_s:
                        break
                    time.sleep(poll_s)
                    continue
                try:
                    item = json.loads(f.read_text())
                except (FileNotFoundError, ValueError):
                    continue  # a stop flushed it first
                with guard:
                    synth, ahead["synth"] = ahead["synth"], None
                    ahead["playing"] = item.get("utt")
                if synth is not None and (synth.utt != item.get("utt") or any(
                        synth.item.get(k) != item.get(k) for k in _SYNTH_KEYS)):  # amended
                    synth.cancel()
                    synth = None
                playing = d / "playing.json"
                try:
                    f.rename(playing)
                except FileNotFoundError:
                    if synth is not None:
                        synth.cancel()
                    continue
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
                playing.unlink(missing_ok=True)
                _done(d, item, rec)
                if rec.get("cut"):
                    _handle_stop(d)
                print(json.dumps({k: rec.get(k) for k in ("seq", "utt", "reason", "played_s", "dur_s")}),
                      flush=True)
                idle_since = time.monotonic()
        finally:
            (d / "player.pid").unlink(missing_ok=True)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        # A say that landed while we were letting go saw the lock held and did
        # not start a player: look once more before leaving.
        if _oldest(q) is None:
            return 0


if __name__ == "__main__":
    sys.exit(serve())
