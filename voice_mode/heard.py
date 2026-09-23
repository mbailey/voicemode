#!/usr/bin/env python3
"""heard - what VoiceMode hears, one JSON line per partial, turn or event.

The log is ``$VOICEMODE_BASE_DIR/logs/conversations/heard_YYYY-MM-DD.jsonl``,
a sibling of ``exchanges_YYYY-MM-DD.jsonl`` that rolls at the same local
midnight (ambient-listen Q6). Append-only: a line is never edited or
removed; a correction is a new line.

Every writer (``listen``, ``converse``, kin's Delta bridge) writes the same
shape through the same contract, so one reader serves every source:

1. take an exclusive ``flock`` on ``heard.lock`` beside the logs (one lock
   for every day's file, so two writers either side of midnight cannot mint
   the same ``seq``);
2. ``seq`` = the last ``seq`` in the newest ``heard_*.jsonl`` + 1. It keeps
   counting across midnight, so a ``seq`` names one line on its own and a
   cursor is one integer;
3. append the record as ONE ``write()`` of ``json + "\\n"`` to a file opened
   ``O_APPEND``, so a reader never sees half a line in practice;
4. release the lock.

This module imports nothing from ``voice_mode`` and nothing outside the
standard library, on purpose: the ride-along hook runs this same file as a
script on every tool call, under whatever ``python3`` is on PATH, and must
start fast and never fail on an import.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = 1

# kind
PARTIAL = "partial"
TURN = "turn"
EVENT = "event"
KINDS = (PARTIAL, TURN, EVENT)

# event names (kebab-case; the design's "listen started" etc.)
EV_LISTEN_STARTED = "listen-started"
EV_LISTEN_STOPPED = "listen-stopped"
EV_HEARTBEAT = "heartbeat"
EV_DEVICE_CHANGED = "device-changed"
EV_WAKE_WORD = "wake-word"
EV_END_WORD = "end-word"
EV_BARGE_IN = "barge-in"
EV_CALL_STARTED = "call-started"
EV_CALL_ENDED = "call-ended"

LOCK_NAME = "heard.lock"
RESERVED = frozenset({"ts", "seq", "kind", "v"})
_TAIL_BYTES = 64 * 1024


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def base_dir() -> Path:
    """``$VOICEMODE_BASE_DIR`` or ``~/.voicemode`` (the same rule as config)."""
    raw = os.environ.get("VOICEMODE_BASE_DIR") or str(Path.home() / ".voicemode")
    return Path(os.path.expanduser(os.path.expandvars(raw)))


def log_dir() -> Path:
    return base_dir() / "logs" / "conversations"


def log_path(day: Optional[date] = None, directory: Optional[Path] = None) -> Path:
    day = day or datetime.now().date()
    return (directory or log_dir()) / f"heard_{day.strftime('%Y-%m-%d')}.jsonl"


def log_files(directory: Optional[Path] = None) -> list[Path]:
    """Every heard log in the directory, oldest first (the name sorts by date)."""
    d = directory or log_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("heard_????-??-??.jsonl") if p.is_file())


# --------------------------------------------------------------------------
# Reading the tail of a file
# --------------------------------------------------------------------------

def _last_seq_in(path: Path) -> Optional[int]:
    """The ``seq`` of the last whole, parseable line in ``path``, or None.

    Reads at most the last 64 KiB. A final line with no trailing newline is
    a write in flight (or a torn one) and is skipped, not trusted.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return None
            f.seek(max(0, size - _TAIL_BYTES))
            chunk = f.read()
    except OSError:
        return None
    lines = chunk.split(b"\n")
    # lines[-1] is b"" when the file ends in a newline; otherwise it is a
    # partial line. Either way it is not a whole record.
    for raw in reversed(lines[:-1]):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        seq = rec.get("seq") if isinstance(rec, dict) else None
        if isinstance(seq, int):
            return seq
    return None


def last_seq(directory: Optional[Path] = None) -> int:
    """The highest ``seq`` written so far, across days; 0 when none."""
    for path in reversed(log_files(directory)):
        seq = _last_seq_in(path)
        if seq is not None:
            return seq
    return 0


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def append(kind: str,
           *,
           text: Optional[str] = None,
           source: str = "mic",
           device: Optional[str] = None,
           session: Optional[str] = None,
           agent: Optional[str] = None,
           final: Optional[bool] = None,
           event: Optional[str] = None,
           directory: Optional[Path] = None,
           **extra: Any) -> dict:
    """Append one record and return it, ``seq`` and ``ts`` filled in.

    ``kind`` is ``partial``, ``turn`` or ``event``. ``final`` defaults to
    False for a partial and True for a turn. Extra keyword fields (``via``,
    ``detector``, ``age_at_return``, ``word``, ``listen_id`` ...) are written
    as given; None values are dropped. Raises ValueError on a bad kind, and
    OSError if the log cannot be written: callers that must not fail
    (``converse``) wrap the call; a listener that cannot write should stop
    and say so.
    """
    if kind not in KINDS:
        raise ValueError(f"heard: kind must be one of {KINDS}, not {kind!r}")
    if kind in (PARTIAL, TURN) and not isinstance(text, str):
        raise ValueError(f"heard: a {kind} needs text")
    if kind == EVENT and not event:
        raise ValueError("heard: an event needs its name (event=...)")
    clash = RESERVED & extra.keys()
    if clash:
        raise ValueError(f"heard: {sorted(clash)} are the writer's to set, not the caller's")
    if final is None and kind != EVENT:
        final = kind == TURN

    d = directory or log_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(d / LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        record = _clean({
            "ts": _now_iso(),
            "seq": last_seq(d) + 1,
            "kind": kind,
            "event": event,
            "text": text,
            "source": source,
            "device": device,
            "session": session,
            "agent": agent,
            "final": final,
            **extra,
            "v": SCHEMA,
        })
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        path = log_path(directory=d)
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            written = os.write(fd, line)
            if written != len(line):  # never seen on a local disk; say so if it is
                raise OSError(errno.EIO, f"heard: short write {written}/{len(line)} to {path}")
        finally:
            os.close(fd)
        return record
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def partial(text: str, **kw: Any) -> dict:
    """A recognised chunk that a later turn will subsume (``final: false``)."""
    return append(PARTIAL, text=text, **kw)


def turn(text: str, *, detector: Optional[str] = None, **kw: Any) -> dict:
    """A finished turn: the joined text, and the detector that ended it."""
    return append(TURN, text=text, detector=detector, **kw)


def event(name: str, **kw: Any) -> dict:
    """An event line: listen-started, heartbeat, listen-stopped, wake-word ..."""
    return append(EVENT, event=name, **kw)


# --------------------------------------------------------------------------
# Identity helpers for writers inside VoiceMode
# --------------------------------------------------------------------------

def caller_session() -> Optional[str]:
    """The harness session id, by converse's own precedence."""
    return (os.environ.get("VOICEMODE_SESSION_ID")
            or os.environ.get("CLAUDE_CODE_SESSION_ID")
            or os.environ.get("CLAUDE_SESSION_ID"))


def caller_agent() -> Optional[str]:
    return os.environ.get("VOICEMODE_AGENT") or os.environ.get("CLAUDE_CODE_AGENT")


def input_device_name() -> Optional[str]:
    """The OS name of the default input device, or None. Never raises.

    A label for WHERE the words came from, never WHO said them (VM-1010).
    Imports sounddevice lazily so the hook path never loads it.
    """
    try:
        import sounddevice as sd  # type: ignore
        info = sd.query_devices(kind="input")
        name = info.get("name") if isinstance(info, dict) else None
        return str(name) if name else None
    except Exception:
        return None
