"""mouth - the speaking half of the ears: ``mouth say TEXT`` returns at once.

The complement to ``voice_mode.listen`` (the ears), built new and small
(Mike, voice 19:39-20:00 Thu 2026-09-24: "a little thing to speak back ...
a stack, maybe a pluggable backend ... simple and new"). It replaces
nothing yet; converse still speaks. Spec card: the commons [AMBIENT]
channel, Cora 20:07 Thu 2026-09-24.

- ``say`` queues and returns; ONE resident player speaks, in playlist
  order, so stacked openers come for free. The queue is a maildir (box.py):
  a line is a mail in ``new/``, done is ``cur/`` with a flag.
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

    ``priority`` (a playlist, lower plays sooner): None (50, the back of the
    list), a number (10, 20, 30...), ``next`` (0, the front), or ``now`` (-1,
    the front, and the line playing now is cut with ``reason=interrupted``;
    only that line, never the queue behind it).
    """
    priority = _priority(priority)
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
    d.mkdir(parents=True, exist_ok=True)
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
        "expires_s": expires_s,
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
    from .box import box_dir, drop

    drop(box_dir(d), item)
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


def _priority(p):
    """None, ``next``, ``now``, or a number (a numeric string counts); else ValueError."""
    if p is None or p in ("next", "now"):
        return p
    try:
        f = float(p)
    except (TypeError, ValueError):
        raise ValueError("mouth: priority is next, now, or a number (lower plays sooner)") from None
    return int(f) if f == int(f) else f


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
    from .box import Queue, drop, public

    q = Queue(d)
    x = q.find(utt)
    if x is None:
        cur = _playing(d)
        if cur and cur.get("utt") == utt:
            raise ValueError(f"mouth: {utt} is already playing; retract it and say again")
        raise ValueError(f"mouth: no queued line {utt}")
    # A new mail that supersedes the line: it takes the line's place and utt.
    # If the player takes the old one first, this plays after it, as news.
    item = public(x)
    target = item.pop("mail_id")
    item.pop("mail_from", None)
    item["amended_from"] = x.get("amended_from") or x["text"]
    item["text"] = text
    drop(q.bx, item, supersedes=target)
    return item


def retract(utt: str, *, d: Optional[Path] = None) -> dict:
    """Drop a queued line, or cut it if it is playing. Its ``said`` says ``retracted``."""
    d = d or mouth_dir()
    from .box import Queue, public
    from .player import _done, said_unplayed

    q = Queue(d)
    x = q.find(utt)
    if x is not None and q.drop_line(x, "T"):
        item = public(x)
        rec = said_unplayed(item, "retracted")
        _done(d, item, rec)
        return rec
    cur = _playing(d)
    if cur and cur.get("utt") == utt:
        return _stop_file(d, {"t": time.time(), "reason": "retracted", "flush": False, "utt": utt})
    raise ValueError(f"mouth: no queued or playing line {utt}")


def status(d: Optional[Path] = None) -> dict:
    d = d or mouth_dir()
    playing = None
    try:
        p = json.loads((d / "playing.json").read_text())
        playing = {"utt": p["utt"], "text": p["text"][:80]}
    except (FileNotFoundError, ValueError):
        pass
    pid = (d / "player.pid").read_text().strip() if (d / "player.pid").exists() else None
    from .box import Queue

    q = Queue(d)
    return {"dir": str(d), "box": str(q.bx), "player": _player_running(d) if d.exists() else False,
            "pid": pid, "queued": len(q.lines()), "playing": playing}
