"""mouth: say returns at once, one player, saying/said on the heard log, stop, device-bound.

No sound and no server: the ``silence`` backend and the ``null`` device,
paced in real time so a stop cuts as it would live.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_mode import heard, mouth
from voice_mode.mouth import output, player


@pytest.fixture
def box(tmp_path, monkeypatch):
    d, logs = tmp_path / "mouth", tmp_path / "logs"
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(logs))
    monkeypatch.setenv("VOICEMODE_AGENT", "pip")
    monkeypatch.setenv("VOICEMODE_SESSION_ID", "s-test")
    return SimpleNamespace(d=d, logs=logs)


def lines(logs: Path) -> list[dict]:
    return [json.loads(x) for f in sorted(logs.glob("heard_*.jsonl")) for x in f.read_text().splitlines()]


def run_player(d: Path, idle: float = 0.3) -> threading.Thread:
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": idle}, daemon=True)
    t.start()
    return t


def say(text, **kw):
    kw.setdefault("device", "null")
    kw.setdefault("backend", "silence")
    return mouth.say(text, spawn=False, **kw)


# -- heard: the two new kinds ------------------------------------------------

def test_saying_and_said_are_kinds_with_final_like_partial_and_turn(tmp_path):
    a = heard.saying("hello", utt="u1", directory=tmp_path)
    b = heard.said(utt="u1", played_s=0.4, reason="done", directory=tmp_path)
    assert (a["kind"], a["final"], a["source"]) == ("saying", False, "mouth")
    assert (b["kind"], b["final"]) == ("said", True)
    assert b["seq"] == a["seq"] + 1


def test_saying_needs_text_and_both_need_an_utt(tmp_path):
    with pytest.raises(ValueError):
        heard.append("saying", utt="u", directory=tmp_path)
    with pytest.raises(ValueError):
        heard.append("said", directory=tmp_path)


def test_collapse_shows_another_sessions_said_and_hides_saying_and_its_own(tmp_path):
    heard.saying("hi there", utt="u1", session="cora-s", agent="cora", directory=tmp_path)
    heard.said(utt="u1", session="cora-s", agent="cora", text_played_est="hi there",
               played_s=0.5, reason="done", directory=tmp_path)
    heard.said(utt="u2", session="me", agent="pip", text_played_est="mine",
               played_s=0.5, reason="done", directory=tmp_path)
    recs, _ = heard._scan(heard.log_path(directory=tmp_path))
    shown = [i.text for i in heard.collapse(recs, session="me") if i.text]
    assert len(shown) == 1 and shown[0].startswith("[said cora mouth") and shown[0].endswith("hi there")


def test_format_record_renders_both():
    assert "utt u1" in heard.format_record({"seq": 1, "kind": "saying", "text": "x", "utt": "u1"})
    out = heard.format_record({"seq": 2, "kind": "said", "text_played_est": "x", "utt": "u1",
                               "reason": "stop", "played_s": 0.4, "dur_s": 2.0})
    assert "stop 0.4/2.0s" in out


# -- the mouth ---------------------------------------------------------------

def test_say_returns_at_once_and_the_player_writes_saying_then_said(box):
    t0 = time.monotonic()
    item = say("Hello Mike.")  # 11 chars: ~0.7 s of audio
    assert time.monotonic() - t0 < 0.2
    run_player(box.d).join(5)
    got = lines(box.logs)
    assert [r["kind"] for r in got] == ["saying", "said"]
    saying, said = got
    for k in ("utt", "text", "voice", "backend", "device", "requested_ts", "gen_s", "agent", "session"):
        assert k in saying, k
    assert saying["utt"] == said["utt"] == item["utt"]
    assert (said["reason"], said["cut"], said["text_played_est"]) == ("done", False, "Hello Mike.")
    assert said["played_s"] == pytest.approx(said["dur_s"], abs=0.01)
    assert said["played_s"] == pytest.approx(11 / 15, abs=0.06)


def test_one_at_a_time_oldest_first(box):
    a, b = say("first one"), say("second one")
    run_player(box.d).join(8)
    order = [(r["kind"], r["utt"]) for r in lines(box.logs)]
    assert order == [("saying", a["utt"]), ("said", a["utt"]), ("saying", b["utt"]), ("said", b["utt"])]


def test_stop_cuts_within_a_block_and_flushes_the_queue(box):
    long = say("word " * 20)          # ~6.7 s
    queued = say("never heard")
    th = run_player(box.d)
    time.sleep(0.5)
    mouth.stop()
    th.join(5)
    got = lines(box.logs)
    said = {r["utt"]: r for r in got if r["kind"] == "said"}
    assert said[long["utt"]]["reason"] == "stop" and said[long["utt"]]["cut"] is True
    assert 0.3 < said[long["utt"]]["cut_at_s"] < 0.75
    est = said[long["utt"]]["text_played_est"]  # ~0.5 s at 15 chars/s: about one word
    assert est.startswith("word") and len(est) < 15
    assert "dur_s" not in said[long["utt"]]  # synthesis never finished
    assert said[queued["utt"]]["played_s"] == 0.0 and said[queued["utt"]]["reason"] == "stop"
    assert not [r for r in got if r["kind"] == "saying" and r["utt"] == queued["utt"]]


def test_stop_current_keeps_the_queue_and_reason_passes_through(box):
    long, nxt = say("word " * 20), say("next")
    th = run_player(box.d)
    time.sleep(0.4)
    mouth.stop("barge-in", flush=False)
    th.join(5)
    said = {r["utt"]: r for r in lines(box.logs) if r["kind"] == "said"}
    assert said[long["utt"]]["reason"] == "barge-in"
    assert said[nxt["utt"]]["reason"] == "done"


def test_a_stop_never_touches_a_later_say(box):
    mouth.stop()
    time.sleep(0.01)
    item = say("after the stop")
    run_player(box.d).join(5)
    said = [r for r in lines(box.logs) if r["kind"] == "said"]
    assert said[0]["utt"] == item["utt"] and said[0]["reason"] == "done"


def test_an_absent_device_refuses_and_never_falls_back(box, monkeypatch):
    def absent(name, sr):
        raise output.DeviceAbsent(f"output device {name!r} is not present")
    monkeypatch.setattr(output, "open_output", absent)
    item = say("hello", device="airpods")
    run_player(box.d).join(5)
    got = lines(box.logs)
    assert [r["kind"] for r in got] == ["said"]
    assert (got[0]["reason"], got[0]["played_s"], got[0]["utt"]) == ("device-absent", 0.0, item["utt"])


def test_wait_returns_the_said_record(box):
    run_player(box.d, idle=1.0)
    rec = say("short", wait=True, timeout=5)
    assert rec["kind"] == "said" and rec["reason"] == "done"


def test_no_device_is_an_error_not_a_default(box, monkeypatch):
    monkeypatch.delenv("VOICEMODE_MOUTH_DEVICE", raising=False)
    with pytest.raises(ValueError, match="no device"):
        mouth.say("hi", backend="silence", spawn=False)


# -- device names: exact, never a substring ------------------------------------

class FakeSd:
    default = SimpleNamespace(device=(0, 1))

    def _terminate(self):
        pass

    def _initialize(self):
        pass

    def query_devices(self, i=None):
        devs = [{"name": "MacBook Pro Microphone", "max_output_channels": 0},
                {"name": "MacBook Pro Speakers", "max_output_channels": 2},
                {"name": "Speakers + AirPods", "max_output_channels": 2}]
        return devs if i is None else devs[i]


def test_airpods_never_matches_the_speakers_plus_airpods_aggregate(monkeypatch):
    monkeypatch.setattr(output, "_sd", lambda: FakeSd())
    with pytest.raises(output.DeviceAbsent, match="not present"):
        output.resolve("airpods")
    assert output.resolve("speakers + airpods") == (2, "Speakers + AirPods")
    assert output.resolve("default") == (None, "MacBook Pro Speakers")


def test_text_at_cuts_back_to_a_word():
    assert player.text_at("hello there world", 0.5) == "hello"
    assert player.text_at("hello there", 1.0) == "hello there"
    assert player.text_at("hello there", 0.0) == ""
