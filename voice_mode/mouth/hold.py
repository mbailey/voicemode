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
``expired`` and it is never spoken. For a held line the clock starts when
his turn ENDS, not when the line was queued (an opener queued 30 s into a
90 s turn must not die before he stops).

**Stale** (Mike, voice 03:07-03:12 Sat, via Cora): a held line queued
before his current turn BEGAN is old news once he starts talking again:
*"chronology is important"*. It is kept (filed P) and never spoken, its
``said`` says ``stale``.
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
_cache: dict = {"t": 0.0, "v": None}  # v = (newest floor record, turn start t, last end t)


def idle_s() -> float:
    return float(os.environ.get("VOICEMODE_MOUTH_HOLD_IDLE_S", IDLE_S))


def _newest_mic(directory: Optional[Path] = None) -> Optional[dict]:
    """The newest mic record that moves the floor, today's log then yesterday's."""
    return _scan(directory)[0]


def _is_end(rec: dict) -> bool:
    return rec.get("kind") == "turn" or (rec.get("kind") == "event" and rec.get("event") in _ENDS)


def _scan(directory: Optional[Path] = None) -> tuple:
    """(the newest floor-moving mic record, when his current turn began, when
    his last turn ended). Begin is the first worded partial after the last
    end, and only while the newest record is a partial; either may be None."""
    newest, start_t, end_t = None, None, None
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
            if rec.get("kind") == "partial" and str(rec.get("text") or "").strip():
                if newest is None:
                    newest = rec
                start_t = _ts(rec) if _ts(rec) is not None else start_t
                continue
            if _is_end(rec):
                if newest is None:
                    return rec, None, _ts(rec)
                end_t = _ts(rec) if end_t is None else end_t
                # A pause inside the beat is the same turn (he went on before
                # a held line could speak), so the turn began before it.
                gap = (start_t - _ts(rec)) if start_t is not None and _ts(rec) is not None else None
                if gap is not None and gap < grace_s():
                    continue
                return newest, start_t, end_t
    return newest, start_t, end_t


def _ts(rec: dict) -> Optional[float]:
    try:
        return datetime.fromisoformat(rec["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _look(directory: Optional[Path] = None, now: Optional[float] = None,
          max_age_s: float = 0.1) -> tuple[Optional[dict], float]:
    """The newest floor-moving mic record, and ``now``; cached for ``max_age_s``."""
    rec, _, _, now = _look3(directory, now, max_age_s)
    return rec, now


def _look3(directory: Optional[Path] = None, now: Optional[float] = None,
           max_age_s: float = 0.1) -> tuple:
    """(newest floor record, turn start t, last end t, now); cached for ``max_age_s``."""
    now = time.time() if now is None else now
    if directory is None and _cache["v"] is not None and now - _cache["t"] < max_age_s:
        return (*_cache["v"], now)
    v = _scan(directory)
    if directory is None:
        _cache.update(t=now, v=v)
    return (*v, now)


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
    """What the player should do with a queued item: ``play``, ``wait``, ``expire`` or ``stale``."""
    now = time.time() if now is None else now
    held = item.get("hold") == "turn-end"
    exp_s = item.get("expires_s")
    exp = item.get("expires_t")
    if (not held or exp_s is None) and exp is not None and now >= float(exp):
        return "expire"
    if held:
        _, start_t, end_t, _ = _look3(directory, now)
        if floor(directory, now) == "speaking":
            asked = item.get("requested_t")
            if asked is not None and start_t is not None and float(asked) < start_t:
                return "stale"
            return "wait"
        if exp_s is not None:
            base = max(float(item.get("requested_t") or now), end_t or 0.0)
            if now >= base + float(exp_s):
                return "expire"
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


#: Mike's rule, 02:05 Sat: "remove stop words and then see if all the words
#: ... exist in the previous message out ... there'd need to be enough unique
#: words that are not in the set". And a backchannel is not a stop (Cora,
#: 02:07: his one-word "Fantastic!" cut her follower at 1.45 s).
STOP_WORDS = frozenset("""
a about above after again all am an and any are as at be been being below both
but by can could did do does doing down during each few for from further had
has have having he her here hers him his how i if in into is it its itself just
let me more most my myself no nor not now of off on once only or other our out
over own same she should so some such than that the their them then there these
they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself d ll m re s t ve
yeah yes yep yup ok okay mm mmm mhm hmm uh um ah oh huh right sure cool nice great
fantastic brilliant awesome lovely good wow thanks thank really totally exactly
indeed got see well like
""".split())
#: Words that ask the mouth to stop, whatever else was said.
STOP_ASKS = frozenset("stop wait hang hold pause shush quiet enough interrupt".split())
BARGE_WORDS = 3   # Mike, 02:09 Sat: "I should be able to say a certain amount
                  # without you stopping" - $VOICEMODE_MOUTH_BARGE_WORDS tunes it
RESUME_S = 20.0   # a cut line's unplayed rest waits this long for his turn to end


def barge_words() -> int:
    return int(os.environ.get("VOICEMODE_MOUTH_BARGE_WORDS", BARGE_WORDS))


def resume_s() -> float:
    return float(os.environ.get("VOICEMODE_MOUTH_RESUME_S", RESUME_S))


def rest_of(text: str, played: str) -> str:
    """What was not heard, from the start of the sentence it was cut in."""
    cut = len(played or "")
    start = max(text.rfind(c, 0, cut) for c in ".!?")
    return text[start + 1:].strip() if start >= 0 else text.strip()


def _mic_partials_since(since_t: float, directory: Optional[Path] = None) -> list:
    out = []
    for path in heard.log_files(directory)[-2:]:
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - _TAIL))
                lines = f.read().split(b"\n")
        except OSError:
            continue
        for raw in lines[:-1]:
            try:
                rec = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(rec, dict) and rec.get("kind") == "partial" \
                    and rec.get("source", "mic") == "mic" and str(rec.get("text") or "").strip():
                t = _ts(rec)
                if t is not None and t > since_t:
                    out.append(rec)
    return out


def barge(since_t: float, line_text: str, directory: Optional[Path] = None,
          now: Optional[float] = None) -> Optional[dict]:
    """His words since ``since_t`` (the line's first frame) that ask for the
    floor, or None. Echo partials are ignored; then an explicit stop word
    cuts at once, and otherwise BARGE_WORDS content words of his that are not
    the line's own, counted across his partials so far."""
    if not barge_on():
        return None
    rec, _ = _look(directory, now)
    if rec is None or rec.get("kind") != "partial":
        return None                                  # cheap: nothing new from him
    t = _ts(rec)
    if t is None or t <= since_t:
        return None
    have, novel, last = set(_words(line_text)), set(), None
    for p in _mic_partials_since(since_t, directory):
        text = str(p.get("text") or "")
        if is_echo(text, line_text):
            continue
        words = _words(text)
        if STOP_ASKS & set(words):
            return p
        novel |= {w for w in words if w not in STOP_WORDS and w not in have}
        last = p
    return last if len(novel) >= barge_words() else None
