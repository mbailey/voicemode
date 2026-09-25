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
- ``amend``/``retract`` change a line before it is spoken; ``say --next``
  jumps the queue and ``--now`` interrupts. See DESIGN.md.
- ``play FILE [--start S] [--end S]`` queues a sound; ``$VOICEMODE_MOUTH_DUCK``
  lowers the DJ's music while the mouth speaks.
- ``hold="turn-end"`` waits for the end of his turn; ``expires_s`` drops a
  line that lost its moment (hold.py: stacked openers).
- ``pan`` puts it in one ear: -1 left, 1 right (``--channel left|right``).
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
from .voices import default_voice


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


PAN_NAMES = {"left": -1.0, "right": 1.0, "both": None}

#: How much the speaker wants his reply (Mike, voice 02:42-02:45 Sat, via Cora:
#: "speaking subscribes you ... there should be levels of your interest"):
#: high - wake me on his partials as they pile up (I asked, "lay it on me");
#: normal - wake me on his turn; low - signed off; zero - "speak and leave".
#: Carried on saying/said so a waiter (heard-first reply:AGENT) can read it.
INTERESTS = ("high", "normal", "low", "zero")


def pan_value(pan) -> Optional[float]:
    """A pan as given (-1..1, 'left', 'right', 'both'); None asks $VOICEMODE_MOUTH_PAN."""
    if pan is None:
        env = os.environ.get("VOICEMODE_MOUTH_PAN")
        return pan_value(env) if env else None
    if isinstance(pan, str):
        if pan in PAN_NAMES:
            return PAN_NAMES[pan]
        pan = float(pan)
    if not -1.0 <= float(pan) <= 1.0:
        raise ValueError("mouth: pan is -1 (left) .. 1 (right)")
    return float(pan)


def say(text: str, *, voice: Optional[str] = None, speed: Optional[float] = None,
        backend: Optional[str] = None, device: Optional[str] = None,
        pan=None, log_dir: Optional[Path] = None, wait: bool = False, timeout: float = 300.0,
        priority: Optional[str] = None, d: Optional[Path] = None, spawn: bool = True,
        extra: Optional[dict] = None, hold: Optional[str] = None,
        expires_s: Optional[float] = None, interest: Optional[str] = None) -> dict:
    """Queue ``text``; return the queued item (``utt``), or with ``wait`` its ``said`` record.

    ``priority``: None (the back of the queue), ``next`` (the front), or ``now``
    (the front, and the line playing now is cut with ``reason=interrupted``;
    only that line, never the queue behind it).
    """
    if priority not in (None, "next", "now"):
        raise ValueError("mouth: priority is next or now")
    from .hold import HOLDS

    if hold not in (None, *HOLDS):
        raise ValueError("mouth: hold is " + " or ".join(HOLDS))
    if expires_s is not None and expires_s <= 0:
        raise ValueError("mouth: expires is seconds from now, above 0")
    if interest not in (None, *INTERESTS):
        raise ValueError("mouth: interest is " + ", ".join(INTERESTS))
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
        "voice": voice or default_voice(d)[0],
        "speed": speed,
        "backend": backend or os.environ.get("VOICEMODE_MOUTH_BACKEND") or "auto",
        "device": device,
        "pan": pan_value(pan),
        "requested_t": now,
        "requested_ts": datetime.fromtimestamp(now).astimezone().isoformat(timespec="milliseconds"),
        "agent": heard.caller_agent(),
        "session": heard.caller_session(),
        "log_dir": str(log_dir) if log_dir else os.environ.get("VOICEMODE_MOUTH_LOG_DIR"),
        "wait": wait,
        "priority": priority,
        "hold": hold,
        "interest": interest,
        "expires_t": (now + expires_s) if expires_s is not None else None,
        **(extra or {}),
    }
    from . import maillog

    item["mail_log"] = maillog.box_from_env()
    if item["mail_log"]:
        # The thread root: the request mail if it came by mail, else this entry.
        queued = maillog.entry({**item, "log_root": item.get("mail_id")}, "queued",
                               {k: item.get(k) for k in ("utt", "text", "voice", "device", "pan",
                                                         "priority", "hold", "expires_t",
                                                         "agent", "session",
                                                         "requested_ts", "file", "mail_id")})
        item["log_root"] = item.get("mail_id") or queued
    part = q / f".{item['utt']}.part"
    part.write_text(json.dumps(item))
    # Names sort into play order: '0-' (next, now) before plain time_ns.
    part.rename(q / f"{'0-' if priority else ''}{time.time_ns()}-{item['utt']}.json")
    if priority == "now":
        cur = _playing(d)
        if cur:
            _stop_file(d, {"t": time.time(), "reason": "interrupted", "flush": False, "utt": cur["utt"]})
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


def _stop_file(d: Path, rec: dict) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    part = d / f".stop.{os.getpid()}.part"
    part.write_text(json.dumps(rec))
    part.rename(d / "stop")
    return rec


def _playing(d: Path) -> Optional[dict]:
    try:
        return json.loads((d / "playing.json").read_text())
    except (FileNotFoundError, ValueError):
        return None


def _queued(d: Path, utt: str) -> Optional[Path]:
    hits = sorted((d / "queue").glob(f"*-{utt}.json")) if (d / "queue").exists() else []
    return hits[0] if hits else None


def play(source: str, *, start: Optional[float] = None, end: Optional[float] = None,
         extra_tag: Optional[dict] = None, **kw) -> dict:
    """Queue a sound file or URL (or ``start``..``end`` seconds of it). Same queue, stop, log."""
    if "://" not in source:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"mouth: no such file {source}")
        source = str(path)
    if start is not None and end is not None and end <= start:
        raise ValueError("mouth: --end must be after --start")
    span = f" {start or 0:g}-{end:g}s" if end is not None else (f" from {start:g}s" if start else "")
    label = f"[sound {Path(source).name}{span}]"
    return say(label, backend="file", extra={"file": source, "start": start, "end": end,
                                             **(extra_tag or {})}, **kw)


def stop(reason: str = "stop", *, flush: bool = True, d: Optional[Path] = None) -> dict:
    """Cut what is playing (and, with flush, what is queued) within 50 ms."""
    return _stop_file(d or mouth_dir(), {"t": time.time(), "reason": reason, "flush": flush})


def amend(utt: str, text: str, *, d: Optional[Path] = None) -> dict:
    """Rewrite a queued line in place, keeping its place (the queue's ``Supersedes:``).

    Refuses a line already playing (retract it instead) or already gone.
    """
    d = d or mouth_dir()
    if not text.strip():
        raise ValueError("mouth: nothing to say; retract it instead")
    f = _queued(d, utt)
    claim = d / "queue" / f".amend-{utt}"
    try:
        f.rename(claim)  # the player cannot take it while it is claimed
    except (AttributeError, FileNotFoundError):
        cur = _playing(d)
        if cur and cur.get("utt") == utt:
            raise ValueError(f"mouth: {utt} is already playing; retract it and say again") from None
        raise ValueError(f"mouth: no queued line {utt}") from None
    item = json.loads(claim.read_text())
    item["amended_from"] = item.get("amended_from") or item["text"]
    item["text"] = text
    claim.write_text(json.dumps(item))
    claim.rename(f)
    return item


def retract(utt: str, *, d: Optional[Path] = None) -> dict:
    """Drop a queued line, or cut it if it is playing. Its ``said`` says ``retracted``."""
    d = d or mouth_dir()
    f = _queued(d, utt)
    claim = d / "queue" / f".retract-{utt}"
    try:
        f.rename(claim)
    except (AttributeError, FileNotFoundError):
        cur = _playing(d)
        if cur and cur.get("utt") == utt:
            return _stop_file(d, {"t": time.time(), "reason": "retracted", "flush": False, "utt": utt})
        raise ValueError(f"mouth: no queued or playing line {utt}") from None
    item = json.loads(claim.read_text())
    claim.unlink()
    from .player import _done, said_unplayed

    rec = said_unplayed(item, "retracted")
    _done(d, item, rec)
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
