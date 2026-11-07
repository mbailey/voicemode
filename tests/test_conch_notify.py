"""Tests for the operator-path summon nudge (VM-1625, narrowed VM-2078 D2).

VM-2078 removed converse's callback mode and, with it, the mode gate this
module used to run (``callback`` waiter ⇒ push, ``wait`` waiter ⇒ no push):
every ordinary waiter now polls and pulls its own grant, so the ordinary
``give``/``bump`` nudges are gone too. The one caller left is the summon path
(``conch_ops.summon_and_grant``, VM-1637, exercised via ``conch give`` to a
running non-waiter in ``test_conch_cli.py`` / ``test_conch_mcp.py``) — a
summoned session has no poll loop of its own, so it still needs telling.

D2's whole point was that the old push's return value was never checked, so
delivery failure was silent. :func:`push_nudge` is the fix at the unit level:
a small, synchronous function that reports one of three CHECKED outcomes
(``"delivered"`` / ``"failed"`` / ``"remote"``) instead of swallowing the
result — the module docstring explains what each means and what the caller
(``summon_and_grant``) must do with it.

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py (unused directly here, but present for consistency with the
other conch test modules). The push shells out to the skillbox
``session send``; every test that can reach it monkeypatches
``subprocess.run`` so nothing is ever typed into a real tmux pane.
"""

import os

from voice_mode.conch_notify import NUDGE_TEXT, push_nudge


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _RecordingRun:
    """Stand-in for ``subprocess.run`` that records argv and never spawns.

    ``returncode`` controls the simulated exit status (drives the
    session-id→project fallback) — a single int applies to every call, or a
    list is consumed one-per-call (for a miss-then-hit fallback sequence).
    ``raises`` simulates a missing ``session`` binary / tmux failure;
    ``returns_none`` simulates a badly-shaped mock (or a genuinely malformed
    result) that has no ``.returncode`` at all.
    """

    def __init__(self, returncode=0, raises=None, returns_none=False):
        self.calls = []
        self._returncodes = returncode if isinstance(returncode, list) else None
        self.returncode = returncode
        self.raises = raises
        self.returns_none = returns_none

    def __call__(self, *args, **kwargs):
        self.calls.append(args[0] if args else kwargs.get("args"))
        if self.raises is not None:
            raise self.raises
        if self.returns_none:
            return None

        class _Result:
            pass

        result = _Result()
        if self._returncodes is not None:
            result.returncode = self._returncodes[len(self.calls) - 1]
        else:
            result.returncode = self.returncode
        return result


class _FakeEntry:
    """Minimal duck-typed stand-in for push_nudge's entry contract.

    ``push_nudge`` only reads ``pid``, ``session_id``, ``project_path`` — the
    same shape as a ``WaiterEntry`` or a ``conch_ops.RunningSession``.
    """

    def __init__(self, session_id, *, pid=os.getpid(), project_path=None):
        self.session_id = session_id
        self.pid = pid
        self.project_path = project_path


def _entry(session_id, *, pid=os.getpid(), project_path=None):
    return _FakeEntry(session_id, pid=pid, project_path=project_path)


# --------------------------------------------------------------------------- #
# push_nudge — the three checked outcomes
# --------------------------------------------------------------------------- #

class TestPushNudge:
    def test_local_delivered(self, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("abc-123")) == "delivered"
        assert len(rec.calls) == 1
        argv = rec.calls[0]
        assert argv[:3] == ["session", "send", "abc-123"]
        assert argv[3] == NUDGE_TEXT

    def test_local_failed_on_no_match(self, monkeypatch):
        # Non-zero on both the session-id AND the project-basename fallback
        # (no project_path here, so there is no fallback to try at all).
        rec = _RecordingRun(returncode=1)
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("abc-123")) == "failed"

    def test_remote_no_pid_never_attempts_a_nudge(self, monkeypatch):
        """A remote grantee (pid=None) — no local pane to nudge at all."""
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("remote-1", pid=None)) == "remote"
        assert rec.calls == []

    def test_none_entry_is_failed_not_delivered(self, monkeypatch):
        """No entry (vanished waiter) means no delivery evidence — never
        report success on nothing to nudge."""
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(None) == "failed"
        assert rec.calls == []

    def test_missing_session_binary_is_failed_not_raised(self, monkeypatch):
        rec = _RecordingRun(raises=FileNotFoundError("no session binary"))
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("abc-123")) == "failed"

    def test_subprocess_timeout_is_failed_not_raised(self, monkeypatch):
        import subprocess
        rec = _RecordingRun(raises=subprocess.TimeoutExpired("session", 10))
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("abc-123")) == "failed"

    def test_malformed_result_is_failed_not_raised(self, monkeypatch):
        """A mock (or a genuinely odd result) with no ``.returncode`` must
        still resolve to "failed", never propagate an AttributeError."""
        rec = _RecordingRun(returns_none=True)
        monkeypatch.setattr("subprocess.run", rec)
        assert push_nudge(_entry("abc-123")) == "failed"


class TestLocalPushFallback:
    def test_falls_back_to_project_basename_on_session_id_miss(self, monkeypatch):
        # First call (session id) misses, second call (project basename) hits.
        rec = _RecordingRun(returncode=[1, 0])
        monkeypatch.setattr("subprocess.run", rec)
        outcome = push_nudge(_entry("ghost-sid", project_path="/home/me/work/voicemode"))
        assert outcome == "delivered"
        assert len(rec.calls) == 2
        assert rec.calls[0][2] == "ghost-sid"      # tried session id first
        assert rec.calls[1][2] == "voicemode"      # then project basename
        assert rec.calls[0][3] == NUDGE_TEXT
        assert rec.calls[1][3] == NUDGE_TEXT

    def test_no_fallback_when_session_id_hits(self, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        outcome = push_nudge(_entry("good-sid", project_path="/home/me/work/voicemode"))
        assert outcome == "delivered"
        assert len(rec.calls) == 1                      # hit on first try
        assert rec.calls[0][2] == "good-sid"

    def test_no_project_path_no_fallback_attempted(self, monkeypatch):
        rec = _RecordingRun(returncode=1)
        monkeypatch.setattr("subprocess.run", rec)
        outcome = push_nudge(_entry("abc-123", project_path=None))
        assert outcome == "failed"
        assert len(rec.calls) == 1  # no second attempt without a project_path
