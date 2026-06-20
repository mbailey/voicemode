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
import threading

import pytest
from click.testing import CliRunner

from voice_mode.conch_queue import ConchQueue, WaiterEntry
from voice_mode.cli_commands.conch import conch
from voice_mode.conch_notify import NUDGE_TEXT, notify_granted, _local_nudge


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


# --------------------------------------------------------------------------- #
# CLI: `conch bump` pushes to a lone callback waiter it promotes
# --------------------------------------------------------------------------- #

class TestBumpNotifies:
    def test_bump_lone_callback_waiter_pushes_nudge(self, runner, monkeypatch):
        """Bump promoting a lone callback waiter pushes the nudge synchronously.

        With only a callback waiter (no blocking waiter to starve) ``grant_next``
        grants the head and pings no one -- so it is ``bump``'s own CLI seam that
        must deliver the nudge. The one-shot CLI path stays synchronous, so the
        ``session send`` is captured here without any thread to join. (Asserted
        directly now, not just by comment -- impl-001 review coverage gap.)
        """
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        # Conch free (no holder/lock in the isolated home) + one idle callback waiter.
        ConchQueue.register("cb-solo-1", agent="cbagent", mode="callback")

        result = runner.invoke(conch, ["bump"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "cb-solo-1"  # promoted as next in line
        # ...and the lone callback was actively pushed by the CLI seam.
        assert len(rec.calls) == 1
        argv = rec.calls[0]
        assert argv[:3] == ["session", "send", "cb-solo-1"]
        assert argv[3] == NUDGE_TEXT


# --------------------------------------------------------------------------- #
# notify_granted — blocking vs non-blocking (release-path) local push (impl-002)
# --------------------------------------------------------------------------- #

class TestNonBlockingDispatch:
    """``block=True`` (default, one-shot CLI) runs the local push inline;
    ``block=False`` (the converse release hot path) fires it off-thread so a
    grant site never waits on session discovery / tmux (VM-1625 impl-002)."""

    def test_block_true_runs_synchronously(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            "voice_mode.conch_notify._dispatch_async",
            lambda fn, *a: dispatched.append((fn, a)),
        )
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)

        notify_granted(_entry("cb-sync", mode="callback"), block=True)

        # Inline: the session send ran now; the async dispatcher was untouched.
        assert dispatched == []
        assert len(rec.calls) == 1
        assert rec.calls[0][2] == "cb-sync"

    def test_block_false_dispatches_async(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            "voice_mode.conch_notify._dispatch_async",
            lambda fn, *a: dispatched.append((fn, a)),
        )
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)

        notify_granted(_entry("cb-async", mode="callback"), block=False)

        # Routed through the async dispatcher with the real worker + entry, and
        # NOT run inline (the dispatcher is intercepted here).
        assert rec.calls == []
        assert len(dispatched) == 1
        fn, fn_args = dispatched[0]
        assert fn is _local_nudge
        assert fn_args[0].session_id == "cb-async"

    def test_block_false_real_thread_delivers_and_reaps(self, monkeypatch):
        """The real daemon thread runs the nudge to completion.

        ``subprocess.run`` (here the recording stand-in) waits on and reaps its
        child inside the thread, so nothing is left a zombie; joining the named
        ``conch-notify`` thread lets us assert the side effect deterministically.
        """
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)

        notify_granted(_entry("cb-thread", mode="callback"), block=False)

        for t in list(threading.enumerate()):
            if t.name == "conch-notify":
                t.join(timeout=5.0)
        assert len(rec.calls) == 1
        assert rec.calls[0][2] == "cb-thread"

    def test_block_false_remote_does_not_dispatch(self, monkeypatch):
        """A remote grantee (pid=None) takes the remote-marker seam, never the
        async local dispatcher -- regardless of ``block``."""
        dispatched = []
        monkeypatch.setattr(
            "voice_mode.conch_notify._dispatch_async",
            lambda fn, *a: dispatched.append((fn, a)),
        )
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)

        notify_granted(_entry("remote-x", mode="callback", pid=None), block=False)

        assert rec.calls == []
        assert dispatched == []
