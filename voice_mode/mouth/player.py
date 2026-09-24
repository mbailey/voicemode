"""The player: one resident process, one utterance at a time, oldest first.

``say`` drops a JSON file into ``queue/`` and makes sure a player is running
(the ``player.lock`` flock is held by whoever plays); it never waits for
the audio. The player takes the oldest file, synthesises, and writes to the
heard log:

- ``saying`` at the FIRST audio frame handed to the device:
  ``utt text voice backend device requested_ts gen_s``
- ``said`` when playback ends:
  ``utt played_s dur_s cut cut_at_s text_played_est reason``, where reason
  is ``done``, ``stop``, ``barge-in``, ``device-absent`` or ``error``.

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
import time
from pathlib import Path
from typing import Optional

from voice_mode import heard

from . import backends as _backends
from . import output as _output
from .paths import mouth_dir


class _Cut(Exception):
    pass


def _read_stop(d: Path) -> Optional[dict]:
    try:
        return json.loads((d / "stop").read_text())
    except (FileNotFoundError, ValueError):
        return None


def _log_dir(item: dict) -> Optional[Path]:
    return Path(item["log_dir"]) if item.get("log_dir") else None


def _common(item: dict) -> dict:
    return {"utt": item["utt"], "voice": item.get("voice"), "backend": item.get("backend"),
            "backend_asked": item.get("backend_asked"),
            "session": item.get("session"), "agent": item.get("agent"),
            "requested_ts": item.get("requested_ts"), "directory": _log_dir(item)}


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


def said_unplayed(item: dict, reason: str, device: Optional[str] = None, detail: Optional[str] = None) -> dict:
    return heard.said(**_common(item), device=device or item.get("device"), played_s=0.0,
                      cut=True, cut_at_s=0.0, text_played_est="", reason=reason, detail=detail)


def play_one(item: dict, d: Path) -> dict:
    """Play one queued utterance; return its ``said`` record."""
    text, speed = item["text"], item.get("speed")
    try:
        backend, voice = _backends.resolve(item.get("backend") or "auto", item.get("voice") or "af_sky")
    except Exception as e:  # noqa: BLE001 - a bad voice must still close the utterance
        return said_unplayed(item, "error", detail=str(e)[:300])
    if backend.name != item.get("backend"):  # log what ran; keep what was asked (auto)
        item = {**item, "backend": backend.name, "backend_asked": item.get("backend")}
    try:
        out = _output.open_output(item["device"], backend.sample_rate)
    except _output.DeviceAbsent as e:
        return said_unplayed(item, "device-absent", detail=str(e)[:300])

    sr = backend.sample_rate
    step = int(sr * _backends.BLOCK_S)
    written = generated = 0
    reason, detail, finished_gen = "done", None, False
    t0 = time.monotonic()
    started = False
    gen = backend.stream(text, voice, speed)
    try:
        for block in gen:
            generated += len(block)
            for i in range(0, len(block), step):
                stop = _read_stop(d)
                if stop and stop.get("t", 0) >= item["requested_t"]:
                    reason = stop.get("reason") or "stop"
                    raise _Cut
                if not started:
                    heard.saying(text, **_common(item), device=getattr(out, "name", item["device"]),
                                 speed=speed, gen_s=round(time.monotonic() - t0, 3))
                    started = True
                sub = block[i:i + step]
                out.write(sub)
                written += len(sub)
        finished_gen = True
        out.drain()
    except _Cut:
        out.abort()
    except Exception as e:  # noqa: BLE001
        try:
            out.abort()
        except Exception:  # noqa: BLE001
            pass
        name = type(e).__name__
        reason = "device-absent" if "PortAudio" in name else "error"
        detail = f"{name}: {e}"[:300]
    finally:
        gen.close()  # a cut must not leave the synthesis request open

    cut = reason != "done"
    played = written / sr
    if cut:
        played = max(0.0, played - getattr(out, "latency", 0.0))
    dur = generated / sr if finished_gen else None
    est_dur = dur or max(generated / sr, len(text) / 15.0 / (speed or 1.0))
    return heard.said(
        **_common(item), device=getattr(out, "name", item["device"]),
        played_s=round(played, 3), dur_s=round(dur, 3) if dur is not None else None,
        cut=cut, cut_at_s=round(played, 3) if cut else None,
        text_played_est=text if not cut else text_at(text, played / est_dur if est_dur else 0.0),
        reason=reason, detail=detail)


def _oldest(q: Path) -> Optional[Path]:
    files = sorted(q.glob("*.json"))
    return files[0] if files else None


def _handle_stop(d: Path) -> None:
    """After a cut or while idle: flush what the stop covers, then retire it."""
    stop = _read_stop(d)
    if not stop:
        return
    if stop.get("flush", True):
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
        try:
            while True:
                f = _oldest(q)
                if f is None:
                    _handle_stop(d)
                    if time.monotonic() - idle_since > idle_exit_s:
                        break
                    time.sleep(poll_s)
                    continue
                playing = d / "playing.json"
                try:
                    f.rename(playing)
                except FileNotFoundError:
                    continue  # a stop flushed it first
                item = json.loads(playing.read_text())
                rec = play_one(item, d)
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
