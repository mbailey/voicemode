"""hold - a line that waits for the end of his turn (stacked openers).

Mike, voice 00:11-00:21 Sat 2026-09-26 (via Cora): *"filling the mouth, and
then it speaks when I finish."* An agent queues an opener while he is still
talking, supersedes it as its answer improves, and the mouth speaks the
latest version the moment his turn ends.

A line with ``hold="turn-end"`` stays in the queue, keeps its place, and is
synthesised ahead so it starts at once, until the floor is free:

- **speaking:** the newest mic record in the ears' heard log is a
  ``partial`` with words in it (he is mid-turn).
- **free:** the newest mic record is a ``turn`` (his turn has ended), a
  ``turn-discarded`` or ``listen-stopped`` event (speech ended with no words,
  or the ears stopped), or
  there has been no mic record for ``idle_s`` (the ears died, or nobody is
  talking), or there is no heard log at all.

Measured over 1,004 turns (heard logs of 25-26 Sep): the ``turn`` record
lands 1.46 s after the last ``partial`` at p50, 3.72 s at p99, 7.8 s at
worst; partials inside a turn are 3.39 s apart at p99. So the ``turn``
record is the release, and ``idle_s`` (8 s) is only the safety net.

An opener that arrives after his turn has ended plays once ``grace_s``
has passed since it ended (0 by default, Mike 01:59: the ears' 2 s silence
rule is the beat; $VOICEMODE_MOUTH_HOLD_GRACE_S sets one); a ``now`` line
skips it. Lines queued behind a held one are never blocked.
``barge()`` is the other half: his words during a line cut it. One that arrives while he talks again waits for that turn.
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
GRACE_S = 0.0   # Mike, voice 01:59:19 Sat: "yes, beat 0" - the ears' 2 s silence
                # rule already IS the beat; 0.7 s on top measured +0.7 s per opener
_TAIL = 64 * 1024
# Events that end speech without a turn record: a blip with no words
# ("no text recognised", ~0.3 s; 46 on 25-26 Sep), or the ears stopping.
_ENDS = ("turn-discarded", "listen-stopped")
_cache: dict = {"t": 0.0, "v": None}


def idle_s() -> float:
    return float(os.environ.get("VOICEMODE_MOUTH_HOLD_IDLE_S", IDLE_S))


def _newest_mic(directory: Optional[Path] = None) -> Optional[dict]:
    """The newest mic record that moves the floor, today's log then yesterday's."""
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
            if not isinstance(rec, dict) or rec.get("source", "mic") != "mic":
                continue
            kind = rec.get("kind")
            if kind == "partial" and str(rec.get("text") or "").strip():
                return rec
            if kind == "turn" or (kind == "event" and rec.get("event") in _ENDS):
                return rec
    return None


def _ts(rec: dict) -> Optional[float]:
    try:
        return datetime.fromisoformat(rec["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _look(directory: Optional[Path] = None, now: Optional[float] = None,
          max_age_s: float = 0.1) -> tuple[Optional[dict], float]:
    """The newest floor-moving mic record, and ``now``; cached for ``max_age_s``."""
    now = time.time() if now is None else now
    if directory is None and _cache["v"] is not None and now - _cache["t"] < max_age_s:
        return _cache["v"][0], now
    rec = _newest_mic(directory)
    if directory is None:
        _cache.update(t=now, v=(rec,))
    return rec, now


def floor(directory: Optional[Path] = None, now: Optional[float] = None,
          max_age_s: float = 0.1) -> str:
    """``speaking`` or ``free`` (see the module doc). Cached for ``max_age_s``."""
    rec, now = _look(directory, now, max_age_s)
    if rec is not None and rec.get("kind") == "partial":
        t = _ts(rec)
        age = now - t if t is not None else 0.0
        return "speaking" if age < idle_s() else "free"
    return "free"


def grace_s() -> float:
    """The beat a held line waits after his turn ends (Mike, 01:40 Sat: "let me
    jump in first"). If he starts again inside it, the line keeps holding."""
    return float(os.environ.get("VOICEMODE_MOUTH_HOLD_GRACE_S", GRACE_S))


def check(item: dict, now: Optional[float] = None, directory: Optional[Path] = None) -> str:
    """What the player should do with a queued item: ``play``, ``wait`` or ``expire``."""
    now = time.time() if now is None else now
    exp = item.get("expires_t")
    if exp is not None and now >= float(exp):
        return "expire"
    if item.get("hold") == "turn-end":
        if floor(directory, now) == "speaking":
            return "wait"
        rec, _ = _look(directory, now)
        t = _ts(rec) if rec is not None else None
        # The beat: a turn that ended less than grace_s ago might not be over.
        # ``now`` priority skips it (urgent lines do not wait a beat).
        if t is not None and rec.get("kind") != "partial" and item.get("priority") != "now" \
                and now - t < grace_s():
            return "wait"
    return "play"


# -- barge-in on words (Mike, 01:42 Sat 2026-09-26) ---------------------------
# Stop the mouth when the ears log a PARTIAL - whisper decoded words - not on
# voice activity, so road noise that trips the detector never cuts a line. A
# partial that is the line itself coming back through the mic is not a barge.
ECHO_RUN = 0.7     # share of a partial that must be ONE run of the line's words
BACK_S, AHEAD_S = 8.0, 3.0   # the stretch of the line the mic could be hearing now


def barge_on() -> bool:
    return os.environ.get("VOICEMODE_MOUTH_BARGE", "partial").lower() not in ("off", "0", "no")


#: Barge-in only where the mic cannot hear the mouth (Cora, 02:02 Sat): on the
#: MacBook speakers the mic hears the line GARBLED ("the echo canceler faced--
#: time use" for "the echo canceller FaceTime uses"), no word match survives
#: that, and two lines cut themselves. Headphones only, until a real echo
#: canceller shares the output as its reference (/ASKS 4760).
#: $VOICEMODE_MOUTH_BARGE_DEVICES is a regex over the output device's name.
BARGE_DEVICES = r"airpods|headphone|headset|buds|beats"


def barge_device(name: Optional[str]) -> bool:
    import re
    pat = os.environ.get("VOICEMODE_MOUTH_BARGE_DEVICES", BARGE_DEVICES)
    return bool(name) and re.search(pat, str(name), re.I) is not None


def _words(text: str) -> list:
    return [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]


def near(text: str, played_s: float, est_dur_s: float) -> str:
    """The part of a line around the playhead: what the mic could be hearing."""
    if not est_dur_s or est_dur_s <= 0:
        return text
    n = len(text)
    a = int(n * max(0.0, (played_s - BACK_S) / est_dur_s))
    b = int(n * min(1.0, (played_s + AHEAD_S) / est_dur_s))
    return text[a:max(b, a + 1)]


def is_echo(partial: str, line: str) -> bool:
    """The mic heard the mouth: most of the partial is ONE run of the line's words.

    Not a bag of words (Cora, 01:52 Sat, measured): against a whole 36 s line
    every common word is "in" it, so "actually, I'm..." scored 3/3 as echo and
    his barge-in took 7.9 s. A run keeps the words' order, and ``near()``
    keeps it to what is being played now.
    """
    p, l = _words(partial), _words(line)
    if not p or not l:
        return False
    best = 0
    for i in range(len(l)):
        for j in range(len(p)):
            k = 0
            while i + k < len(l) and j + k < len(p) and l[i + k] == p[j + k]:
                k += 1
            best = max(best, k)
    if len(p) == 1:
        return best == 1
    return best >= 2 and best / len(p) >= ECHO_RUN


def barge(since_t: float, line_text: str, directory: Optional[Path] = None,
          now: Optional[float] = None) -> Optional[dict]:
    """His words since ``since_t`` (the line's first frame), or None."""
    if not barge_on():
        return None
    rec, _ = _look(directory, now)
    if rec is None or rec.get("kind") != "partial":
        return None
    t = _ts(rec)
    if t is None or t <= since_t or is_echo(str(rec.get("text") or ""), line_text):
        return None
    return rec
