"""Each session gets its own name in the conch (#536).

converse() built its Conch with a hardcoded ``agent_name="converse"`` and
registered queue waiters the same way, so with several agents sharing the
channel ``voicemode conch status`` listed every holder and waiter as
"converse", and ``voicemode conch give <name>`` -- which matches on that
field -- had nothing to tell them apart by. The payload already carried the
field; only its value was missing.

The name now resolves VOICEMODE_SESSION_NAME > the project directory's
basename > "converse", so the old value is still what you get when nothing
better is known.
"""
import os
from unittest.mock import patch

import pytest

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue
from voice_mode.tools.converse import _conch_agent_name


def _converse():
    """The undecorated converse coroutine (FastMCP wraps it as ``.fn``)."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


@pytest.fixture
def clean_conch():
    """No conch lock or queue state before/after each test."""
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()
    for e in ConchQueue.list():
        ConchQueue.deregister(e.session_id)
    ConchQueue.clear_grant()
    yield
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()
    for e in ConchQueue.list():
        ConchQueue.deregister(e.session_id)


@pytest.fixture
def no_session_name(monkeypatch):
    monkeypatch.delenv("VOICEMODE_SESSION_NAME", raising=False)


# --------------------------------------------------------------------------- #
# Resolution order
# --------------------------------------------------------------------------- #

def test_env_var_wins_over_project_dir(monkeypatch):
    monkeypatch.setenv("VOICEMODE_SESSION_NAME", "reviewer")
    assert _conch_agent_name("/home/me/src/voicemode") == "reviewer"


def test_env_var_is_stripped(monkeypatch):
    monkeypatch.setenv("VOICEMODE_SESSION_NAME", "  reviewer \n")
    assert _conch_agent_name("/home/me/src/voicemode") == "reviewer"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_env_var_falls_through_to_project_dir(monkeypatch, value):
    monkeypatch.setenv("VOICEMODE_SESSION_NAME", value)
    assert _conch_agent_name("/home/me/src/voicemode") == "voicemode"


def test_project_dir_basename_is_the_default(no_session_name):
    assert _conch_agent_name("/home/me/src/voicemode") == "voicemode"


def test_trailing_separator_does_not_empty_the_name(no_session_name):
    assert _conch_agent_name("/home/me/src/voicemode/") == "voicemode"


@pytest.mark.parametrize("project_path", [None, "", os.sep])
def test_falls_back_to_converse_when_nothing_resolves(no_session_name, project_path):
    """No env var and no usable directory name: today's value, never worse."""
    assert _conch_agent_name(project_path) == "converse"


# --------------------------------------------------------------------------- #
# The name reaches the conch -- both as holder and as queued waiter
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_holder_payload_carries_the_session_name(clean_conch, monkeypatch):
    """While converse holds the floor, the lock file names this session."""
    monkeypatch.setenv("VOICEMODE_SESSION_NAME", "reviewer")
    seen = {}

    async def fake_tts(*args, **kwargs):
        seen["holder"] = Conch.get_holder()
        return False, {}, {"provider": "test"}

    with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=fake_tts):
        await _converse()(message="Hello", wait_for_response=False, session_id="sess-a")

    assert seen.get("holder"), "converse should hold the conch while speaking"
    assert seen["holder"]["agent"] == "reviewer"
    assert seen["holder"]["session_id"] == "sess-a"


@pytest.mark.asyncio
async def test_queued_waiter_shows_its_name_in_conch_status(clean_conch, monkeypatch):
    """A queued converse appears in `conch status` under its own name."""
    from voice_mode.cli_commands.conch import _status_payload

    monkeypatch.setenv("VOICEMODE_SESSION_NAME", "reviewer")
    holder = {"pid": 999999, "agent": "other_agent", "session_id": "holder-x"}
    with patch.object(Conch, "try_acquire", return_value=False), \
         patch.object(Conch, "get_holder", return_value=holder):
        await _converse()(
            message="Hello",
            wait_for_response=False,
            wait_for_conch=True,
            conch_mode="callback",
            session_id="sess-a",
        )

    queued = {q["session_id"]: q for q in _status_payload()["queue"]}
    assert queued["sess-a"]["agent"] == "reviewer"


@pytest.mark.asyncio
async def test_conch_give_can_target_the_session_by_name(clean_conch, monkeypatch):
    """`conch give <name>` matches on the agent field, so the name is usable there."""
    from voice_mode.conch_ops import resolve_session

    holder = {"pid": 999999, "agent": "other_agent", "session_id": "holder-x"}
    with patch.object(Conch, "try_acquire", return_value=False), \
         patch.object(Conch, "get_holder", return_value=holder):
        for name, sid in (("reviewer", "sess-a"), ("writer", "sess-b")):
            monkeypatch.setenv("VOICEMODE_SESSION_NAME", name)
            await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
                session_id=sid,
            )

    assert resolve_session("writer", ConchQueue.list()).session_id == "sess-b"
