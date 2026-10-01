"""aged_turn: the waiter's rule (do-003), a pure function over heard lines (VM-2274)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from voice_mode.listen import aged_turn

T0 = datetime(2026, 9, 24, 4, 0, 0, tzinfo=timezone(timedelta(hours=10)))


def line(seq, kind, at, **kw):
    return {"seq": seq, "kind": kind, "ts": (T0 + timedelta(seconds=at)).isoformat(timespec="milliseconds"), **kw}


LOG = [
    line(1, "event", 0, event="listen-started"),
    line(2, "partial", 1, text="so the bot"),
    line(3, "turn", 3, text="so the bot"),
]


def test_no_turn_is_not_aged():
    assert aged_turn(LOG[:2], 8, T0 + timedelta(seconds=60)) is None


def test_a_young_turn_is_not_aged():
    assert aged_turn(LOG, 8, T0 + timedelta(seconds=10.9)) is None


def test_a_turn_older_than_age_is_returned():
    assert aged_turn(LOG, 8, T0 + timedelta(seconds=11))["seq"] == 3


def test_now_may_be_an_epoch_float():
    assert aged_turn(LOG, 8, (T0 + timedelta(seconds=11)).timestamp())["seq"] == 3


def test_speech_after_the_turn_holds_it():
    log = LOG + [line(4, "partial", 9, text="and another")]
    assert aged_turn(log, 8, T0 + timedelta(seconds=30)) is None


def test_the_newest_turn_is_the_one_that_ages():
    log = LOG + [line(4, "partial", 9, text="and"), line(5, "turn", 11, text="and")]
    assert aged_turn(log, 8, T0 + timedelta(seconds=18)) is None
    assert aged_turn(log, 8, T0 + timedelta(seconds=19))["seq"] == 5


def test_events_after_the_turn_do_not_hold_it():
    log = LOG + [line(4, "event", 9, event="heartbeat")]
    assert aged_turn(log, 8, T0 + timedelta(seconds=11))["seq"] == 3


def test_turns_at_or_before_the_cursor_are_already_shown():
    assert aged_turn(LOG, 8, T0 + timedelta(seconds=60), after_seq=3) is None
    assert aged_turn(LOG, 8, T0 + timedelta(seconds=60), after_seq=2)["seq"] == 3
