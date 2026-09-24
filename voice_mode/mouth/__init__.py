"""mouth - the speaking half of the ears: ``mouth say TEXT`` returns at once.

The complement to ``voice_mode.listen`` (the ears), built new and small
(Mike, voice 19:39-20:00 Thu 2026-09-24: "a little thing to speak back ...
a stack, maybe a pluggable backend ... simple and new"). It replaces
nothing yet; converse still speaks. Spec card: the commons [AMBIENT]
channel, Cora 20:07 Thu 2026-09-24.

- ``say`` queues and returns; ONE resident player speaks, oldest first,
  so stacked openers come for free.
- It speaks to ONE named device (``--device`` or
  ``$VOICEMODE_MOUTH_DEVICE``), exact name, and refuses when it is absent,
  with a ``said reason=device-absent``. Never the default by accident.
- It writes ``saying`` (first audio frame) and ``said`` (end, with the cut
  point) into the heard log, on the ears' timeline, through ``heard.append``.
- ``stop`` cuts within 50 ms; ``reason`` says why (``stop``, ``barge-in``).
- Backends are pluggable (``backends.py``): kokoro, clone, silence.

    python -m voice_mode.mouth say --device airpods --voice pip "Hello."
    python -m voice_mode.mouth stop --reason barge-in
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from voice_mode import heard

from .paths import mouth_dir


def _player_running(d: Path) -> bool:
    fd = os.open(str(d / "player.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def ensure_player(d: Optional[Path] = None) -> bool:
    """Start a player unless one holds the lock. True if one was started."""
    d = d or mouth_dir()
    d.mkdir(parents=True, exist_ok=True)
    if _player_running(d):
        return False
    env = {**os.environ, "VOICEMODE_MOUTH_DIR": str(d)}
    with open(d / "player.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "voice_mode.mouth", "serve"], env=env,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    return True


def say(text: str, *, voice: Optional[str] = None, speed: Optional[float] = None,
        backend: Optional[str] = None, device: Optional[str] = None,
        log_dir: Optional[Path] = None, wait: bool = False, timeout: float = 300.0,
        d: Optional[Path] = None, spawn: bool = True) -> dict:
    """Queue ``text``; return the queued item (``utt``), or with ``wait`` its ``said`` record."""
    device = device or os.environ.get("VOICEMODE_MOUTH_DEVICE")
    if not device:
        raise ValueError("mouth: no device. Pass --device NAME or set VOICEMODE_MOUTH_DEVICE "
                         "('null' plays nothing; 'default' is the system default, by name only)")
    if not text.strip():
        raise ValueError("mouth: nothing to say")
    d = d or mouth_dir()
    q = d / "queue"
    q.mkdir(parents=True, exist_ok=True)
    now = time.time()
    item = {
        "utt": uuid.uuid4().hex[:12],
        "text": text,
        "voice": voice or os.environ.get("VOICEMODE_MOUTH_VOICE") or "af_sky",
        "speed": speed,
        "backend": backend or os.environ.get("VOICEMODE_MOUTH_BACKEND") or "auto",
        "device": device,
        "requested_t": now,
        "requested_ts": datetime.fromtimestamp(now).astimezone().isoformat(timespec="milliseconds"),
        "agent": heard.caller_agent(),
        "session": heard.caller_session(),
        "log_dir": str(log_dir) if log_dir else os.environ.get("VOICEMODE_MOUTH_LOG_DIR"),
        "wait": wait,
    }
    part = q / f".{item['utt']}.part"
    part.write_text(json.dumps(item))
    part.rename(q / f"{time.time_ns()}-{item['utt']}.json")
    if spawn:
        ensure_player(d)
    if not wait:
        return item
    done = d / "done" / f"{item['utt']}.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if done.exists():
            rec = json.loads(done.read_text())
            done.unlink(missing_ok=True)
            return rec
        time.sleep(0.02)
    raise TimeoutError(f"mouth: no said for {item['utt']} within {timeout:.0f}s")


def stop(reason: str = "stop", *, flush: bool = True, d: Optional[Path] = None) -> dict:
    """Cut what is playing (and, with flush, what is queued) within 50 ms."""
    d = d or mouth_dir()
    d.mkdir(parents=True, exist_ok=True)
    rec = {"t": time.time(), "reason": reason, "flush": flush}
    part = d / ".stop.part"
    part.write_text(json.dumps(rec))
    part.rename(d / "stop")
    return rec


def status(d: Optional[Path] = None) -> dict:
    d = d or mouth_dir()
    playing = None
    try:
        p = json.loads((d / "playing.json").read_text())
        playing = {"utt": p["utt"], "text": p["text"][:80]}
    except (FileNotFoundError, ValueError):
        pass
    pid = (d / "player.pid").read_text().strip() if (d / "player.pid").exists() else None
    return {"dir": str(d), "player": _player_running(d) if d.exists() else False, "pid": pid,
            "queued": len(list((d / "queue").glob("*.json"))) if (d / "queue").exists() else 0,
            "playing": playing}
