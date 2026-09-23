"""Has the newest turn aged? A pure function, for the waiter (do-003).

Capture never returns on a turn (the design split, ROADMAP 04:07: capture
outlives the call). Waking an idle agent on an aged turn is a separate,
short waiter process that reads the ``heard`` log; this is its rule, kept
here beside the capture that writes the lines it reads:

    the newest ``turn`` is at least ``age`` seconds old, and nothing newer
    is being spoken -- no ``partial`` has been written after it.

Caveat for the waiter: speech is only visible in the log once its first
chunk is recognised (a 0.35 s quiet or the max chunk length after onset,
plus STT time), so "no partial after the turn" can briefly miss an
utterance that has just begun.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Union

Now = Union[datetime, float]


def _epoch(ts: Union[str, datetime, float]) -> float:
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts.timestamp()


def aged_turn(lines: Iterable[dict], age: float, now: Now, *, after_seq: int = 0) -> Optional[dict]:
    """The newest ``turn`` line past ``after_seq`` if it has aged, else None.

    ``lines`` are ``heard`` records in ``seq`` order; ``now`` is an aware
    datetime or an epoch float. Returns None when there is no turn past
    ``after_seq``, when the newest is younger than ``age``, or when a
    ``partial`` follows it (the speaker has started again).
    """
    newest: Optional[dict] = None
    speaking = False
    for line in lines:
        if line.get("seq", 0) <= after_seq:
            continue
        kind = line.get("kind")
        if kind == "turn":
            newest, speaking = line, False
        elif kind == "partial" and newest is not None:
            speaking = True
    if newest is None or speaking:
        return None
    return newest if _epoch(now) - _epoch(newest["ts"]) >= age else None
