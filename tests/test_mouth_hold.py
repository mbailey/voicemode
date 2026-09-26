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
        for c in hold._caches.values():
            c.update(t=0.0, v=None)
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


def test_a_call_line_listens_to_the_call_too(ears):
    """call:<N> (Mike, 12:43 Sat 2026-09-26): on the phone his words arrive from
    the call. A line into the call waits for them; a line on the AirPods does
    not - someone else's call must not hold the room."""
    assert hold.sources_for("call:5531") == ("mic", "call")
    assert hold.sources_for("call") == ("mic", "call")
    assert hold.sources_for("airpods") == ("mic",) and hold.sources_for(None) == ("mic",)
    ears("partial", source="call")
    assert hold.check({"hold": "turn-end", "device": "call:5531"}) == "wait"
    assert hold.check({"hold": "turn-end", "device": "airpods"}) == "play"
    ears("turn", source="call")
    assert hold.check({"hold": "turn-end", "device": "call:5531"}) == "play"
    ears("partial")                                    # the room mic still counts on a call
    assert hold.check({"hold": "turn-end", "device": "call:5531"}) == "wait"


def test_barge_in_on_a_call_hears_the_call(ears, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_BARGE", "1")
    t0 = time.time() - 1
    ears("partial", source="call", text="stop")
    assert hold.barge(t0, "a long line about the van") is None      # the mic heard nothing
    got = hold.barge(t0, "a long line about the van", sources=hold.sources_for("call:5531"))
    assert got is not None and got["text"] == "stop"


def test_check_play_wait_expire(ears):
    ears("partial")
    assert hold.check({"hold": "turn-end"}) == "wait"
    assert hold.check({}) == "play"                     # an ordinary line never waits
    assert hold.check({"hold": "turn-end", "expires_t": time.time() - 1}) == "expire"
    ears("turn")
    assert hold.check({"hold": "turn-end"}) == "play"          # beat 0 (Mike, 01:59)


def test_a_beat_when_one_is_set(ears, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_HOLD_GRACE_S", "0.7")
    ears("partial")
    ears("turn")
    assert hold.check({"hold": "turn-end"}) == "wait"          # he may go on
    assert hold.check({"hold": "turn-end", "priority": "now"}) == "play"   # now skips it
    assert hold.check({"hold": "turn-end"}, now=time.time() + 0.8) == "play"


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
    assert gap < 0.5, f"release {gap:.2f}s after his turn"


def test_a_better_opener_supersedes_the_held_one(box, ears):
    ears("partial")
    first = deliver(box, "Hmm, let me think", X_Mouth_When="turn-end")
    th = run_player(box.d, idle=0.3)
    time.sleep(0.3)
    deliver(box, "Yes: the app reads the real store", Supersedes=first)
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
    """Held behind a line that outlasts its expiry, counted from his turn's end."""
    ears("partial")
    mouth.say("word " * 9, d=box.d, spawn=False)            # about 3 s, not held
    deliver(box, "too late now", X_Mouth_When="turn-end", X_Mouth_Expires="0.3")
    th = run_player(box.d, idle=0.3)
    time.sleep(0.2)
    ears("turn")
    th.join(8)
    got = lines(box.logs)
    assert [x["text"] for x in got if x["kind"] == "saying"] == ["word " * 9]
    assert [x.get("reason") for x in got if x["kind"] == "said"] == ["done", "expired"]


def test_expiry_counts_from_the_end_of_his_turn(box, ears):
    """Mike's flaw (Sat 01:xx): a 30 s opener died in a 90 s turn. Now the clock
    starts when he stops: an opener that waits out a long turn still speaks."""
    ears("partial")
    mouth.say("Still with you", hold="turn-end", expires_s=0.5, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    time.sleep(1.0)                                          # he talks past the 0.5 s
    ears("partial")
    ears("turn")
    th.join(8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["Still with you"]


def test_a_held_line_from_before_his_turn_is_stale(box, ears):
    """Mike, 03:07-03:12 Sat: lines queued before he started speaking are kept,
    marked unspoken, and never played."""
    ears("turn", age_s=5)                                    # his last turn ended
    old = mouth.say("an answer to the last turn", hold="turn-end", d=box.d, spawn=False)
    time.sleep(0.05)
    ears("partial")                                          # he starts again first
    th = run_player(box.d, idle=2.0)
    time.sleep(0.4)
    new = mouth.say("an opener for this turn", hold="turn-end", d=box.d, spawn=False)
    ears("turn")
    th.join(8)
    got = lines(box.logs)
    assert [x["text"] for x in got if x["kind"] == "saying"] == ["an opener for this turn"]
    said = {x["utt"]: x["reason"] for x in got if x["kind"] == "said"}
    assert said == {old["utt"]: "stale", new["utt"]: "done"}
    cur = sorted(f.name.split(":2,")[1] for f in (box.mail / "cur").iterdir())
    assert cur == ["P", "S"], "stale is kept (filed P), not deleted"


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


def test_the_beat_keeps_holding_if_he_starts_again(box, ears, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_HOLD_GRACE_S", "0.7")
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


def test_now_skips_the_beat(box, ears, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_HOLD_GRACE_S", "0.7")
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


@pytest.fixture
def headphones(monkeypatch):
    # The null device stands in for headphones in these tests.
    monkeypatch.setenv("VOICEMODE_MOUTH_BARGE_DEVICES", "null")


def test_his_words_cut_the_line_and_the_stale_queue(box, ears, headphones, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_RESUME_S", "0")
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


def test_the_mouth_heard_through_the_mic_is_not_a_barge(box, ears, headphones):
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    time.sleep(0.2)
    ears("partial", text="four five six seven")        # its own words, coming back
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_barge_can_be_switched_off(box, ears, headphones, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_BARGE", "off")
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    ears("partial", text="hang on, wait")
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_is_echo():
    assert hold.is_echo("four five six", LONG)           # the line, coming back
    assert not hold.is_echo("hang on, wait", LONG)
    assert not hold.is_echo("", LONG)


def test_his_words_are_not_echo_just_because_the_line_has_them():
    # Cora, 01:51-01:52 Sat: his real partials against a line full of common
    # words. Bag-of-words called all but one of them echo; a run does not.
    line = ("Oh my gosh, hi. Hi! Sorry, I'm not usually like this. I don't actually know "
            "what I'm doing here. It is now late, and I'm talking to my friend on a bench.")
    for heard_ in ("Actually, I'm--", "I'm actually, I'm on a.", "Oh, now.", "AI. So..."):
        assert not hold.is_echo(heard_, line), heard_
    assert hold.is_echo("sorry I'm not usually like", line)


def test_near_is_the_stretch_around_the_playhead():
    text = "a" * 150 + "b" * 150                        # 20 s at 15 chars/s
    assert set(hold.near(text, 2.0, 20.0)) == {"a"}      # early: only the start
    assert "b" in hold.near(text, 15.0, 20.0) and "a" in hold.near(text, 12.0, 20.0)


def test_no_barge_on_speakers(box, ears):
    # default device list: 'null' is not headphones, so his words do not cut
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    ears("partial", text="hang on, wait")
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_barge_devices():
    assert hold.barge_device("airpods") and hold.barge_device("Mike's AirPods Pro")
    assert not hold.barge_device("MacBook Pro Speakers")
    assert not hold.barge_device(None)


def test_a_backchannel_is_not_a_barge(box, ears, headphones):
    mouth.say(MID, d=box.d, spawn=False)
    th = run_player(box.d, idle=0.3)
    assert _wait_for(lambda: _saying(box, MID))
    time.sleep(0.2)
    ears("partial", text="Fantastic!")                 # Cora, 02:07: this cut her follower
    ears("partial", text="yeah, mm, right")
    th.join(15)
    assert [x.get("reason") for x in lines(box.logs) if x["kind"] == "said"] == ["done"]


def test_barge_rules(ears):
    t0 = time.time() - 1
    line = "the echo canceller is how FaceTime keeps your own voice out"
    ears("partial", text="Fantastic!")
    assert hold.barge(t0, line) is None                            # backchannel
    ears("partial", text="hang on")
    assert hold.barge(t0, line) is not None                        # a stop word, at once


def test_his_words_add_up_across_partials(ears):
    t0 = time.time() - 1
    line = "the echo canceller is how FaceTime keeps your own voice out"
    ears("partial", text="I'm actually")                           # 1 word of his
    assert hold.barge(t0, line) is None
    ears("partial", text="on a call now")                           # 2 words: not yet
    assert hold.barge(t0, line) is None
    ears("partial", text="with my AI")                              # 3: a barge
    assert hold.barge(t0, line) is not None


def test_ok_is_not_a_barge(ears):
    # Cora, 02:10: "OK." cut a line at 1.59 s
    ears("partial", text="OK.")
    assert hold.barge(time.time() - 1, "No, I don't get told when I'm cut") is None


def test_rest_of():
    t = "First part. Second part is long. Third."
    assert hold.rest_of(t, "First part. Second pa") == "Second part is long. Third."
    assert hold.rest_of(t, "Fir") == t
    assert hold.rest_of(t, t) == ""


def test_a_cut_line_comes_back_after_his_turn(box, ears, headphones):
    text = "This part you heard. This part you did not hear, it comes back after you."
    mouth.say(text, d=box.d, spawn=False, extra={"agent": "cora"})
    th = run_player(box.d, idle=0.5)
    assert _wait_for(lambda: _saying(box, text))
    time.sleep(0.3)
    ears("partial", text="hang on")                    # cut
    assert _wait_for(lambda: [x for x in lines(box.logs) if x["kind"] == "said" and x.get("reason") == "barge-in"])
    time.sleep(0.5)
    assert len(_saying(box)) == 1, "the rest played over him"
    ears("turn", text="hang on")
    th.join(15)
    said = [x for x in lines(box.logs) if x["kind"] == "saying"]
    assert len(said) == 2 and said[1]["text"].startswith("This part") and "comes back" in said[1]["text"]
    assert said[1].get("agent") == "cora", "the resume must keep the cut line's agent"
    assert said[1].get("hold") == "turn-end"


def test_interest_rides_on_the_saying_record(box, ears):
    mouth.say("Which of the two?", interest="high", d=box.d, spawn=False)
    run_player(box.d, idle=0.3).join(8)
    assert [x.get("interest") for x in lines(box.logs) if x["kind"] == "saying"] == ["high"]
    with pytest.raises(ValueError):
        mouth.say("x", interest="some", d=box.d, spawn=False)
