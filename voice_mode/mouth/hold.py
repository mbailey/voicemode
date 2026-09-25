"""hold - a line that waits for the end of his turn (stacked openers).

Mike, voice 00:11-00:21 Sat 2026-09-26 (via Cora): *"filling the mouth, and
then it speaks when I finish."* An agent queues an opener while he is still
talking, supersedes it as its answer improves, and the mouth speaks the
latest version the moment his turn ends.

A line with ``hold="turn-end"`` stays in the queue, keeps its place, and is
synthesised ahead so it starts at once, until the floor is free:

- **speaking:** the newest mic record in the ears' heard log is a
  ``partial`` (he is mid-turn).
- **free:** the newest mic record is a ``turn`` (his turn has ended), or
  there has been no mic record for ``idle_s`` (the ears died, or nobody is
  talking), or there is no heard log at all.

Measured over 1,004 turns (heard logs of 25-26 Sep): the ``turn`` record
lands 1.46 s after the last ``partial`` at p50, 3.72 s at p99, 7.8 s at
worst; partials inside a turn are 3.39 s apart at p99. So the ``turn``
record is the release, and ``idle_s`` (8 s) is only the safety net.

An opener that arrives after his turn has ended plays at once: he is
waiting. One that arrives while he talks again waits for that turn.
``expires_s`` drops a line that has lost its moment: its ``said`` says
``expired`` and it is never spoken.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from voice_mode import heard

HOLDS = ("turn-end",)
IDLE_S = 8.0
_TAIL = 64 * 1024
_cache: dict = {"t": 0.0, "v": None}


def idle_s() -> float:
    return float(os.environ.get("VOICEMODE_MOUTH_HOLD_IDLE_S", IDLE_S))


def _newest_mic(directory: Optional[Path] = None) -> Optional[dict]:
    """The newest whole ``partial``/``turn`` record from the mic, today's log then yesterday's."""
    for path in reversed(heard.log_files(directory)[-2:]):
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - _TAIL))
                lines = f.read().split(b"\n")
        except OSError:
            continue
        for raw in reversed(lines[:-1]):  # the last piece is empty or a write in flight
            try:
                rec = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(rec, dict) and rec.get("kind") in ("partial", "turn") \
                    and rec.get("source", "mic") == "mic":
                return rec
    return None


def floor(directory: Optional[Path] = None, now: Optional[float] = None,
          max_age_s: float = 0.1) -> str:
    """``speaking`` or ``free`` (see the module doc). Cached for ``max_age_s``."""
    now = time.time() if now is None else now
    if directory is None and _cache["v"] is not None and now - _cache["t"] < max_age_s:
        return _cache["v"]
    rec = _newest_mic(directory)
    v = "free"
    if rec is not None and rec.get("kind") == "partial":
        try:
            age = now - datetime.fromisoformat(rec["ts"]).timestamp()
        except (KeyError, TypeError, ValueError):
            age = 0.0
        v = "speaking" if age < idle_s() else "free"
    if directory is None:
        _cache.update(t=now, v=v)
    return v


def check(item: dict, now: Optional[float] = None, directory: Optional[Path] = None) -> str:
    """What the player should do with a queued item: ``play``, ``wait`` or ``expire``."""
    now = time.time() if now is None else now
    exp = item.get("expires_t")
    if exp is not None and now >= float(exp):
        return "expire"
    if item.get("hold") == "turn-end" and floor(directory, now) == "speaking":
        return "wait"
    return "play"
