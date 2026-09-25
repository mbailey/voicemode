"""Stacked openers: a line held for the end of his turn (hold.py).

Mike, voice 00:11-00:21 Sat 2026-09-26: "filling the mouth, and then it
speaks when I finish." The ears are faked by writing partial/turn records
into a scratch heard log; no sound (silence backend, null device).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from voice_mode import heard, mouth
from voice_mode.mouth import hold, inbox

from test_mouth_inbox import box, deliver, lines, run_player  # noqa: F401  (fixture)


@pytest.fixture
def ears(tmp_path, monkeypatch):
    base = tmp_path / "vm"
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(base))
    hold._cache.update(t=0.0, v=None)
    d = heard.log_dir()
    d.mkdir(parents=True, exist_ok=True)

    def write(kind, age_s=0.0, source="mic"):
        ts = datetime.fromtimestamp(time.time() - age_s).astimezone().isoformat(timespec="milliseconds")
        rec = {"ts": ts, "seq": 1, "kind": kind, "text": "x", "source": source}
        with open(heard.log_path(), "a") as f:
            f.write(json.dumps(rec) + "\n")
        hold._cache.update(t=0.0, v=None)
    return write


def test_the_floor_from_the_heard_log(ears):
    assert hold.floor() == "free"                      # no log: nobody is talking
    ears("partial")
    assert hold.floor() == "speaking"
    ears("turn")
    assert hold.floor() == "free"
    ears("partial", age_s=hold.IDLE_S + 1)             # partials stopped: the ears died
    assert hold.floor() == "free"
    ears("partial")
    ears("partial", source="call")                     # not the mic: does not count
    assert hold.floor() == "speaking"


def test_check_play_wait_expire(ears):
    ears("partial")
    assert hold.check({"hold": "turn-end"}) == "wait"
    assert hold.check({}) == "play"                     # an ordinary line never waits
    assert hold.check({"hold": "turn-end", "expires_t": time.time() - 1}) == "expire"
    ears("turn")
    assert hold.check({"hold": "turn-end"}) == "play"


def test_held_opener_speaks_only_after_his_turn_ends(box, ears):
    ears("partial")                                    # he is mid-turn
    item = mouth.say("Right, I've got that", hold="turn-end", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.6)
    assert not [x for x in lines(box.logs) if x["kind"] == "saying"], "spoke over him"
    t_end = time.time()
    ears("turn")                                       # his turn ends
    th.join(8)
    saying = [x for x in lines(box.logs) if x["kind"] == "saying"]
    assert [x["utt"] for x in saying] == [item["utt"]]
    started = datetime.fromisoformat(saying[0]["ts"]).timestamp()
    assert started - t_end < 0.5, f"slow release: {started - t_end:.2f}s"


def test_a_better_opener_supersedes_the_held_one(box, ears):
    ears("partial")
    first = deliver(box, "Hmm, let me think", X_Mouth_When="turn-end")
    inbox.process_new(box.mail, box.d)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.3)
    deliver(box, "Yes: the app reads the real store", Supersedes=first)
    assert inbox.process_new(box.mail, box.d)[0]["action"] == "amended"
    ears("turn")
    th.join(8)
    spoken = [x["text"] for x in lines(box.logs) if x["kind"] == "saying"]
    assert spoken == ["Yes: the app reads the real store"]


def test_an_opener_that_arrives_after_his_turn_plays_at_once(box, ears):
    ears("turn")
    mouth.say("Here", hold="turn-end", d=box.d, spawn=False)
    run_player(box.d, idle=0.3).join(8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["Here"]


def test_an_ordinary_line_is_not_blocked_by_a_held_one(box, ears):
    ears("partial")
    mouth.say("held opener", hold="turn-end", d=box.d, spawn=False)
    mouth.say("an announcement", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["an announcement"]
    ears("turn")
    th.join(8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["an announcement", "held opener"]


def test_an_opener_that_lost_its_moment_expires_unspoken(box, ears):
    ears("partial")
    deliver(box, "too late now", X_Mouth_When="turn-end", X_Mouth_Expires="0.3")
    inbox.process_new(box.mail, box.d)
    run_player(box.d, idle=0.3).join(8)
    got = lines(box.logs)
    assert not [x for x in got if x["kind"] == "saying"]
    assert [x.get("reason") for x in got if x["kind"] == "said"] == ["expired"]


def test_a_stop_flushes_held_lines(box, ears):
    ears("partial")
    mouth.say("held", hold="turn-end", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.3)
    mouth.stop(d=box.d)
    th.join(8)
    got = lines(box.logs)
    assert not [x for x in got if x["kind"] == "saying"]
    assert [x.get("reason") for x in got if x["kind"] == "said"] == ["stop"]


def test_bad_hold_and_expiry_are_refused(box):
    with pytest.raises(ValueError):
        mouth.say("x", hold="whenever", d=box.d, spawn=False)
    with pytest.raises(ValueError):
        mouth.say("x", expires_s=0, d=box.d, spawn=False)
