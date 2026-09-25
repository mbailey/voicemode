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

    def write(kind, age_s=0.0, source="mic", text="x", event=None):
        ts = datetime.fromtimestamp(time.time() - age_s).astimezone().isoformat(timespec="milliseconds")
        rec = {"ts": ts, "seq": 1, "kind": kind, "text": text, "source": source}
        if event:
            rec["event"] = event
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
    assert hold.check({"hold": "turn-end"}) == "wait"          # the beat: he may go on
    assert hold.check({"hold": "turn-end", "priority": "now"}) == "play"   # now skips it
    assert hold.check({"hold": "turn-end"}, now=time.time() + hold.GRACE_S + 0.1) == "play"


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
    assert saying[0].get("hold") == "turn-end", "the log should say the line was held"
    started = datetime.fromisoformat(saying[0]["ts"]).timestamp()
    gap = started - t_end
    assert hold.GRACE_S <= gap < hold.GRACE_S + 0.5, f"release {gap:.2f}s after his turn"


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


def test_speech_that_ends_without_a_turn_frees_the_floor(ears):
    ears("partial")
    ears("event", event="turn-discarded")              # a blip, no words recognised
    assert hold.floor() == "free"
    ears("partial")
    ears("event", event="listen-stopped")              # the ears stopped
    assert hold.floor() == "free"
    ears("partial")
    ears("event", event="heartbeat")                   # other events do not move it
    assert hold.floor() == "speaking"


def test_a_partial_with_no_words_is_not_speech(ears):
    ears("turn")
    ears("partial", text="  ")
    assert hold.floor() == "free"


def test_the_beat_keeps_holding_if_he_starts_again(box, ears):
    ears("partial")
    mouth.say("held", hold="turn-end", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.3)
    ears("turn")                                       # a pause...
    time.sleep(0.3)
    ears("partial")                                    # ...and he goes on, inside the beat
    time.sleep(1.0)
    assert not [x for x in lines(box.logs) if x["kind"] == "saying"], "jumped in on a pause"
    ears("turn")
    th.join(8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["held"]


def test_now_skips_the_beat(box, ears):
    ears("partial")
    mouth.say("urgent", hold="turn-end", priority="now", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(0.3)
    t_end = time.time()
    ears("turn")
    th.join(8)
    saying = [x for x in lines(box.logs) if x["kind"] == "saying"]
    assert datetime.fromisoformat(saying[0]["ts"]).timestamp() - t_end < 0.5


LONG = "one two three four five six seven eight nine ten " * 6   # ~20 s on the silence backend
MID = "one two three four five six seven eight nine ten " * 2    # ~7 s: long enough to talk over


def _saying(box, text=None):
    return [x for x in lines(box.logs) if x["kind"] == "saying" and (text is None or x["text"] == text)]


def _wait_for(pred, s=5.0):
    end = time.time() + s
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_his_words_cut_the_line_and_the_stale_queue(box, ears):
    mouth.say(LONG, d=box.d, spawn=False)
    stale = mouth.say("queued before he spoke", d=box.d, spawn=False)
    th = run_player(box.d, idle=0.5)
    assert _wait_for(lambda: _saying(box, LONG)), "the long line never started"
    time.sleep(0.2)
    ears("partial", text="hang on, wait")              # his words, mid-line
    time.sleep(0.2)
    fresh = mouth.say("an opener for what he just said", hold="turn-end", d=box.d, spawn=False)
    ears("turn", text="hang on, wait")
    th.join(10)
    said = {x["utt"]: x for x in lines(box.logs) if x["kind"] == "said"}
    first = [x for x in said.values() if x.get("reason") == "barge-in" and x.get("cut")]
    assert first, f"the line was not cut by his words: {[(x.get('reason'), x.get('cut')) for x in said.values()]}"
    assert said[stale["utt"]]["reason"] == "barge-in", "a line queued before his words was not flushed"
    assert said[fresh["utt"]]["reason"] == "done", "the opener queued after his words was lost"


def test_the_mouth_heard_through_the_mic_is_not_a_barge(box, ears):
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    time.sleep(0.2)
    ears("partial", text="four five six seven")        # its own words, coming back
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_barge_can_be_switched_off(box, ears, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_BARGE", "off")
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    ears("partial", text="hang on, wait")
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_is_echo():
    assert hold.is_echo("four five six", LONG)
    assert not hold.is_echo("hang on, wait", LONG)
    assert not hold.is_echo("", LONG)
