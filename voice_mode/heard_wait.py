"""heard_wait - block until an idle agent should be woken by what was heard.

``python -m voice_mode.heard_wait`` is the waiter half of ambient listen
(spec 3.2/3.3, VM-2274 do-003). The ears are a separate, long-lived
capture process that writes ``heard_*.jsonl``; this is short-lived, like
``pager listen``: the agent runs it with Bash ``run_in_background``, it
blocks cheaply, prints ONE JSON line and exits, and the agent re-arms it.
The capture never restarts, so a re-arm loses nothing.

It reads the session's cursor, the one the ride-along hook moves (the
pager's rule): a turn the hook already showed a busy agent is not past the
cursor, so it never wakes for it; what it wakes with it takes (renders and
advances), so the hook never repeats it.

Returns, one JSON line on stdout ``{reason, text, cursor, ...}``:

- ``turn``          a turn past the cursor, and the newest speech past the
                    cursor is at least ``--age`` s old (default 8, Q2).
                    exit 0
- ``end-word``      an end-word event past the cursor: at once.   exit 0
- ``capture-down``  the ears are not running: a ``listen-stopped`` event,
                    no heartbeat for more than 2x the period, or no capture
                    seen within ``--grace`` s of arming. A dead ear is never
                    a quiet room.                                 exit 3
- ``timeout``       ``--timeout`` s passed (default: none).       exit 124
- ``stopped``       SIGTERM or SIGINT.                            exit 0

Converse's own turns (``via: "converse"``) never wake it: they are
someone's direct conversation, and the hook shows them.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from voice_mode import heard

DEFAULT_AGE = 8.0            # Q2, ruled as recommended
DEFAULT_PERIOD = 30.0        # heartbeat period when the capture names none
DEFAULT_GRACE = 30.0         # how long to wait for a capture that is not up yet
DEFAULT_POLL = 0.25
ARM_SLACK = 0.05             # a line stamped this close before arming counts as after it
PERIOD_KEYS = ("period", "heartbeat_period", "period_s", "interval_s")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_CANNOT_LOOK = 2
EXIT_CAPTURE_DOWN = 3
EXIT_TIMEOUT = 124

REARM = "re-arm: python -m voice_mode.heard_wait (Bash run_in_background) is the next thing you do"
REARM_DOWN = ("the ears are down: restart the capture (or tell the human it is down), "
              "THEN re-arm; re-arming alone returns capture-down again")


def _epoch(rec: dict) -> Optional[float]:
    try:
        return datetime.fromisoformat(rec["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _is_speech(rec: dict) -> bool:
    return rec.get("kind") in (heard.PARTIAL, heard.TURN) and rec.get("via") != "converse"


def _alive_line(rec: dict) -> bool:
    """A line only a running capture writes."""
    if _is_speech(rec):
        return True
    return rec.get("kind") == heard.EVENT and rec.get("event") in (
        heard.EV_HEARTBEAT, heard.EV_LISTEN_STARTED)


class Waiter:
    """One armed wait. ``check()`` is one poll; ``run()`` polls until a result."""

    def __init__(self, session: str, *, age: float = DEFAULT_AGE,
                 timeout: Optional[float] = None, grace: float = DEFAULT_GRACE,
                 period: Optional[float] = None, poll: float = DEFAULT_POLL,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 log_directory: Optional[Path] = None,
                 cursor_directory: Optional[Path] = None):
        self.session = session
        self.age = age
        self.timeout = timeout
        self.grace = grace
        self.period_override = period
        self.poll = poll
        self.clock = clock
        self.sleep = sleep
        self.log_directory = log_directory
        self.cursor_directory = cursor_directory
        self.armed_at = clock()
        # The ears' state, from our own follow of the log (not the cursor:
        # the hook moves the cursor past heartbeats and listen-stopped).
        self.capture: Optional[str] = None      # None never seen | "up" | "down"
        self.stop_reason: Optional[str] = None
        self.last_alive: Optional[float] = None
        # The newest line from ANY capture (alive or listen-stopped). Grace
        # holds while nothing has been seen since arming: the log's history
        # (yesterday's stop, a capture that crashed an hour ago) must not
        # decide before a new capture has had its chance (engineer's refine
        # of do-003, 04:27: arm-then-start failed once the log had history).
        self.last_line_at: Optional[float] = None
        self.period: float = period or DEFAULT_PERIOD
        self._follow_seq = -1
        self._hint: Optional[tuple[Path, int]] = None
        self._replayed = False
        self._follow()                           # the log's history, once
        self._replayed = True
        heard.pending(session, log_directory=log_directory,
                      cursor_directory=cursor_directory)  # a new session's cursor starts now

    # -- the ears ---------------------------------------------------------

    def _follow(self) -> None:
        recs, tail = heard.read_after(
            self._follow_seq,
            hint_file=self._hint[0].name if self._hint else None,
            hint_offset=self._hint[1] if self._hint else 0,
            directory=self.log_directory)
        for r in recs:
            rec = r.rec
            self._follow_seq = r.seq
            t = _epoch(rec)
            if t is None and self._replayed:
                t = self.clock()   # a new line with no usable ts: seen now
            is_stop = rec.get("kind") == heard.EVENT and rec.get("event") == heard.EV_LISTEN_STOPPED
            if rec.get("kind") == heard.EVENT and rec.get("event") == heard.EV_LISTEN_STARTED:
                self.capture, self.stop_reason = "up", None
            elif is_stop:
                self.capture = "down"
                self.stop_reason = rec.get("reason") or "listen-stopped"
            if (is_stop or _alive_line(rec)) and t is not None:
                if self.last_line_at is None or t > self.last_line_at:
                    self.last_line_at = t
            if _alive_line(rec):
                if t is not None and (self.last_alive is None or t > self.last_alive):
                    self.last_alive = t
                if self.capture is None:
                    self.capture = "up"   # lines without a listen-started: someone is writing
            if self.period_override is None and rec.get("kind") == heard.EVENT:
                for k in PERIOD_KEYS:
                    if isinstance(rec.get(k), (int, float)) and rec[k] > 0:
                        self.period = float(rec[k])
                        break
        if tail:
            self._hint = tail

    def _capture_down(self, now: float) -> Optional[str]:
        seen_since_arm = (self.last_line_at is not None
                          and self.last_line_at >= self.armed_at - ARM_SLACK)
        if not seen_since_arm and now - self.armed_at < self.grace:
            return None        # a capture may be starting: history does not decide yet
        if self.capture == "down":
            tail = "" if seen_since_arm else f"; no new capture in the {self.grace:.0f}s since arming"
            return f"listen stopped ({self.stop_reason}){tail}"
        if self.capture == "up":
            # no timed line at all: count from arming, so a dead ear still goes stale
            ref = self.last_alive if self.last_alive is not None else self.armed_at
            if now - ref > 2 * self.period:
                return f"no heartbeat for {now - ref:.0f}s (period {self.period:.0f}s)"
            return None
        if now - self.armed_at >= self.grace:
            return f"no capture seen in the {self.grace:.0f}s since arming"
        return None

    # -- one poll -----------------------------------------------------------

    def _result(self, reason: str, text: str = "", cursor: Optional[int] = None,
                **extra) -> dict:
        if cursor is None:
            cur = heard.load_cursor(self.session, self.cursor_directory)
            cursor = cur.seq if cur else None
        out = {"reason": reason, "text": text, "cursor": cursor, "session": self.session}
        out.update({k: v for k, v in extra.items() if v is not None})
        out["rearm"] = REARM
        return out

    def _take(self, reason: str, **extra) -> Optional[dict]:
        text, cursor = heard.take(self.session, log_directory=self.log_directory,
                                  cursor_directory=self.cursor_directory)
        if cursor is None:
            return None      # the hook holds the lock this instant; next poll
        return self._result(reason, text, cursor, **extra)

    def check(self) -> Optional[dict]:
        now = self.clock()
        self._follow()
        pend = heard.pending(self.session, log_directory=self.log_directory,
                             cursor_directory=self.cursor_directory)
        if pend is None:
            return None
        if any(r.get("kind") == heard.EVENT and r.get("event") == heard.EV_END_WORD
               for r in pend):
            got = self._take("end-word")
            if got:
                return got
        turns = [r for r in pend if r.get("kind") == heard.TURN and _is_speech(r)]
        if turns:
            speech = [t for t in (_epoch(r) for r in pend if _is_speech(r)) if t is not None]
            newest = max(speech) if speech else None
            if newest is not None and now - newest >= self.age:
                got = self._take("turn", seq=turns[-1]["seq"],
                                 age=round(now - _epoch(turns[-1]), 1)
                                 if _epoch(turns[-1]) else None)
                if got:
                    return got
        down = self._capture_down(now)
        if down:
            # Hand over whatever was heard before the ears went, so nothing
            # is lost; then say plainly that re-arming alone will not help.
            got = self._take("capture-down", detail=down) if pend else None
            got = got or self._result("capture-down", "", detail=down)
            got["rearm"] = REARM_DOWN
            return got
        if self.timeout is not None and now - self.armed_at >= self.timeout:
            return self._result("timeout", "")
        return None

    def run(self, should_stop: Optional[Callable[[], Optional[str]]] = None) -> dict:
        """Poll until a result. ``should_stop()`` returning a name (the
        signal's) ends it between polls, never inside one: a signal that
        lands mid-``take()`` must not consume a turn without printing it."""
        while True:
            why = should_stop() if should_stop else None
            if why:
                return self._result("stopped", "", signal=why)
            got = self.check()
            if got:
                return got
            self.sleep(self.poll)

    def banner(self) -> str:
        cur = heard.load_cursor(self.session, self.cursor_directory)
        if self.capture == "up" and self.last_alive is not None:
            ears = f"capture up, last line {self.clock() - self.last_alive:.0f}s ago, period {self.period:.0f}s"
        elif self.capture == "down":
            ears = f"capture DOWN ({self.stop_reason})"
        else:
            ears = f"no capture seen yet; capture-down after {self.grace:.0f}s"
        return (f"heard_wait: session {self.session}, cursor {cur.seq if cur else '?'}, "
                f"age {self.age:g}s, {ears}")


_signalled: list[str] = []


def _on_signal(signum, frame):
    _signalled.append(signal.Signals(signum).name)   # a flag; run() stops between polls


EXIT_BY_REASON = {"turn": EXIT_OK, "end-word": EXIT_OK, "stopped": EXIT_OK,
                  "capture-down": EXIT_CAPTURE_DOWN, "timeout": EXIT_TIMEOUT}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m voice_mode.heard_wait",
        description="Block until what was heard should wake this agent; print one JSON line; exit. "
                    "Run it with Bash run_in_background, and re-arm it every time it returns.")
    p.add_argument("--session", help="default: $CLAUDE_CODE_SESSION_ID (or VOICEMODE_SESSION_ID)")
    p.add_argument("--age", type=float, default=DEFAULT_AGE,
                   help="seconds of quiet after a turn before waking (default %(default)s)")
    p.add_argument("--timeout", type=float, default=None, help="give up after this many seconds")
    p.add_argument("--grace", type=float, default=DEFAULT_GRACE,
                   help="seconds to wait for a capture that is not up yet (default %(default)s)")
    p.add_argument("--period", type=float, default=None,
                   help="heartbeat period, when the capture's events do not name one "
                        f"(default {DEFAULT_PERIOD:g})")
    p.add_argument("--poll", type=float, default=DEFAULT_POLL, help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    session = a.session or heard.caller_session()
    if not session:
        sys.stderr.write("heard_wait: no session: pass --session or run inside Claude Code "
                         "($CLAUDE_CODE_SESSION_ID)\n")
        return EXIT_USAGE
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    try:
        w = Waiter(session, age=a.age, timeout=a.timeout, grace=a.grace,
                   period=a.period, poll=a.poll)
        sys.stderr.write(w.banner() + "\n")
        sys.stderr.flush()
        result = w.run(should_stop=lambda: _signalled[0] if _signalled else None)
    except OSError as e:
        sys.stderr.write(f"heard_wait: could not look: {e}\n")
        return EXIT_CANNOT_LOOK
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return EXIT_BY_REASON.get(result["reason"], EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
