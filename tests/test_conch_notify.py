"""Tests for notify-on-give (VM-1625): the *push* half of the conch's delivery.

Two layers are covered:

- ``voice_mode.conch_notify.notify_granted`` in isolation — the mode gate
  (callback ⇒ push, wait ⇒ no push), local-vs-remote routing, the
  session-id→project-basename fallback, and its never-raises contract.
- the ``voicemode conch give`` CLI path that calls it after writing a grant.

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py (re-pins ``Conch.LOCK_FILE`` into a per-test fake home; ConchQueue
derives its paths from there). The local push shells out to the skillbox
``session send``; every test that can reach it monkeypatches ``subprocess.run``
so nothing is ever typed into a real tmux pane.
"""

import os

import pytest
from click.testing import CliRunner

from voice_mode.conch_queue import ConchQueue, WaiterEntry
from voice_mode.cli_commands.conch import conch
from voice_mode.conch_notify import NUDGE_TEXT, notify_granted


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _RecordingRun:
    """Stand-in for ``subprocess.run`` that records argv and never spawns.

    ``returncode`` controls the simulated exit status (drives the
    session-id→project fallback); ``raises`` simulates a missing ``session``
    binary / tmux failure.
    """

    def __init__(self, returncode=0, raises=None):
        self.calls = []
        self.returncode = returncode
        self.raises = raises

    def __call__(self, *args, **kwargs):
        self.calls.append(args[0] if args else kwargs.get("args"))
        if self.raises is not None:
            raise self.raises

        class _Result:
            pass

        result = _Result()
        result.returncode = self.returncode
        return result


@pytest.fixture
def runner():
    return CliRunner()


def _entry(session_id, *, mode="callback", pid=os.getpid(), project_path=None):
    return WaiterEntry(
        session_id=session_id, seq=1, agent="x", pid=pid,
        mode=mode, project_path=project_path,
    )


# --------------------------------------------------------------------------- #
# notify_granted — the mode gate
# --------------------------------------------------------------------------- #

class TestModeGate:
    def test_callback_local_pushes_session_send(self, monkeypatch):
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("abc-123", mode="callback"))
        assert len(rec.calls) == 1
        argv = rec.calls[0]
        assert argv[:3] == ["session", "send", "abc-123"]
        assert argv[3] == NUDGE_TEXT

    def test_wait_mode_does_not_push(self, monkeypatch):
        """A wait-mode waiter self-acquires (pull wins) — no push, no double."""
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("abc-123", mode="wait"))
        assert rec.calls == []

    def test_remote_callback_does_not_tmux_push(self, monkeypatch):
        """A remote grantee (pid=None) gets no tmux nudge — the grant is its marker."""
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("remote-1", mode="callback", pid=None))
        assert rec.calls == []

    def test_none_entry_is_noop(self, monkeypatch):
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(None)
        assert rec.calls == []


# --------------------------------------------------------------------------- #
# notify_granted — local push: fallback + never-raises
# --------------------------------------------------------------------------- #

class TestLocalPush:
    def test_falls_back_to_project_basename_on_session_id_miss(self, monkeypatch):
        # returncode=1 => the session-id token misses, so the project basename
        # is tried as a second match token.
        rec = _RecordingRun(returncode=1)
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("ghost-sid", mode="callback",
                              project_path="/home/me/work/voicemode"))
        assert len(rec.calls) == 2
        assert rec.calls[0][2] == "ghost-sid"          # tried session id first
        assert rec.calls[1][2] == "voicemode"          # then project basename
        assert rec.calls[0][3] == NUDGE_TEXT
        assert rec.calls[1][3] == NUDGE_TEXT

    def test_no_fallback_when_session_id_hits(self, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("good-sid", mode="callback",
                              project_path="/home/me/work/voicemode"))
        assert len(rec.calls) == 1                      # hit on first try
        assert rec.calls[0][2] == "good-sid"

    def test_missing_session_binary_is_silent_noop(self, monkeypatch):
        rec = _RecordingRun(raises=FileNotFoundError("no session binary"))
        monkeypatch.setattr("subprocess.run", rec)
        # Must not raise — best-effort push.
        notify_granted(_entry("abc-123", mode="callback"))

    def test_subprocess_timeout_is_silent_noop(self, monkeypatch):
        import subprocess
        rec = _RecordingRun(raises=subprocess.TimeoutExpired("session", 10))
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("abc-123", mode="callback"))  # no raise


# --------------------------------------------------------------------------- #
# CLI: `conch give` calls the push after writing the grant
# --------------------------------------------------------------------------- #

class TestGiveNotifies:
    def test_give_callback_waiter_pushes_nudge(self, runner, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        ConchQueue.register("cb-abc-111", agent="cbagent", mode="callback")
        result = runner.invoke(conch, ["give", "cb-abc-111"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "cb-abc-111"
        assert len(rec.calls) == 1
        argv = rec.calls[0]
        assert argv[:3] == ["session", "send", "cb-abc-111"]
        assert argv[3] == NUDGE_TEXT

    def test_give_wait_waiter_does_not_push(self, runner, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        ConchQueue.register("w-abc-111", agent="wagent", mode="wait")
        result = runner.invoke(conch, ["give", "w-abc-111"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "w-abc-111"
        assert rec.calls == []  # pull wins; idempotent, no push

    def test_give_push_failure_still_grants_and_exits_zero(self, runner, monkeypatch):
        rec = _RecordingRun(raises=FileNotFoundError("no session binary"))
        monkeypatch.setattr("subprocess.run", rec)
        ConchQueue.register("cb-abc-111", agent="cbagent", mode="callback")
        result = runner.invoke(conch, ["give", "cb-abc-111"])
        assert result.exit_code == 0  # best-effort push never breaks give
        assert ConchQueue.granted_to() == "cb-abc-111"

    def test_give_remote_callback_no_push_grant_is_marker(self, runner, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        # Remote waiter: pid=None, no expires => kept live, liveness via heartbeat.
        ConchQueue.register("remote-abc-111", agent="rem", mode="callback", pid=None)
        result = runner.invoke(conch, ["give", "remote-abc-111"])
        assert result.exit_code == 0
        assert rec.calls == []  # no tmux nudge for a remote grantee
        assert ConchQueue.granted_to() == "remote-abc-111"  # grant file is the marker
