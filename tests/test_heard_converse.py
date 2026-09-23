"""converse writes its listen window into the heard log (VM-2270 1.2)."""

import json

import pytest

from voice_mode import heard
from voice_mode.tools import converse as converse_mod


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(converse_mod, "BASE_DIR", tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-env")
    monkeypatch.setenv("CLAUDE_CODE_AGENT", "pip")
    monkeypatch.delenv("VOICEMODE_SESSION_ID", raising=False)
    monkeypatch.delenv("VOICEMODE_AGENT", raising=False)
    return tmp_path / "logs" / "conversations"


def lines(d):
    files = list(d.glob("heard_*.jsonl"))
    return [json.loads(l) for f in files for l in f.read_text().splitlines()]


def test_a_reply_is_one_turn_via_converse(log):
    converse_mod._heard_turn("yes, ship it", session="sess-arg",
                             detector="converse-silence", transport="local")
    [rec] = lines(log)
    assert rec["kind"] == "turn" and rec["final"] is True
    assert rec["text"] == "yes, ship it" and rec["via"] == "converse"
    assert rec["source"] == "mic" and rec["detector"] == "converse-silence"
    assert rec["session"] == "sess-arg" and rec["agent"] == "pip"
    assert "device" not in rec  # task 4 names it; no PortAudio query here


def test_session_falls_back_to_the_environment(log):
    converse_mod._heard_turn("from a survey", transport="survey")
    assert lines(log)[0]["session"] == "sess-env"


def test_no_speech_no_line(log):
    for t in (None, "", "   ", "[no speech detected]"):
        converse_mod._heard_turn(t, transport="local")
    assert lines(log) == []


def test_a_remote_transport_is_its_own_source(log):
    converse_mod._heard_turn("over livekit", transport="livekit")
    assert lines(log)[0]["source"] == "livekit"


def test_never_raises(log, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(heard, "turn", boom)
    converse_mod._heard_turn("lost, and logged as lost", transport="local")


def test_the_hook_of_the_same_session_does_not_repeat_it(log, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(log.parent.parent))
    assert heard.run_hook(json.dumps({"session_id": "sess-arg"})) is None  # start
    assert heard.run_hook(json.dumps({"session_id": "other"})) is None
    converse_mod._heard_turn("mine already", session="sess-arg", transport="local")
    assert heard.run_hook(json.dumps({"session_id": "sess-arg"})) is None
    other = json.loads(heard.run_hook(json.dumps({"session_id": "other"})))
    assert other["hookSpecificOutput"]["additionalContext"].endswith("converse:pip] mine already")
