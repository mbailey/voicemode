"""Tests for notify-on-give (VM-1625): the *push* half of the conch's delivery.

VM-2078 removed converse's callback mode and, with it, the mode gate this
module used to run (``callback`` waiter ⇒ push, ``wait`` waiter ⇒ no push):
every ordinary waiter now polls and pulls its own grant, so the ordinary
``give``/``bump`` nudges are gone too. The one caller left is the summon path
(``conch_ops.summon_and_grant``, VM-1637, exercised via ``conch give`` to a
running non-waiter in ``test_conch_cli.py`` / ``test_conch_mcp.py``) — a
summoned session has no poll loop of its own, so it still needs telling.

What is covered here, at the ``notify_granted`` level directly:

- local-vs-remote routing (``pid`` set ⇒ tmux push; ``pid is None`` ⇒ the
  remote-marker seam, no tmux),
- the session-id→project-basename fallback and never-raises contract of the
  local push,
- blocking vs non-blocking dispatch (``block=True`` inline, ``block=False``
  off a daemon thread).

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py. The local push shells out to the skillbox ``session send``;
every test that can reach it monkeypatches ``subprocess.run`` so nothing is
ever typed into a real tmux pane.
"""

import os
import threading

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


class _FakeEntry:
    """Minimal duck-typed stand-in for notify_granted's entry contract.

    ``notify_granted`` only reads ``pid``, ``session_id``, ``project_path`` —
    it no longer carries (or reads) a ``mode`` field (VM-2078).
    """

    def __init__(self, session_id, *, pid=os.getpid(), project_path=None):
        self.session_id = session_id
        self.pid = pid
        self.project_path = project_path


def _entry(session_id, *, pid=os.getpid(), project_path=None):
    return _FakeEntry(session_id, pid=pid, project_path=project_path)


# --------------------------------------------------------------------------- #
# notify_granted — local-vs-remote routing (no mode gate any more)
# --------------------------------------------------------------------------- #

class TestRouting:
    def test_local_pushes_session_send(self, monkeypatch):
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("abc-123"))
        assert len(rec.calls) == 1
        argv = rec.calls[0]
        assert argv[:3] == ["session", "send", "abc-123"]
        assert argv[3] == NUDGE_TEXT

    def test_remote_does_not_tmux_push(self, monkeypatch):
        """A remote grantee (pid=None) gets no tmux nudge — the grant is its marker."""
        rec = _RecordingRun()
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("remote-1", pid=None))
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
        notify_granted(_entry("ghost-sid", project_path="/home/me/work/voicemode"))
        assert len(rec.calls) == 2
        assert rec.calls[0][2] == "ghost-sid"          # tried session id first
        assert rec.calls[1][2] == "voicemode"          # then project basename
        assert rec.calls[0][3] == NUDGE_TEXT
        assert rec.calls[1][3] == NUDGE_TEXT

    def test_no_fallback_when_session_id_hits(self, monkeypatch):
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("good-sid", project_path="/home/me/work/voicemode"))
        assert len(rec.calls) == 1                      # hit on first try
        assert rec.calls[0][2] == "good-sid"

    def test_missing_session_binary_is_silent_noop(self, monkeypatch):
        rec = _RecordingRun(raises=FileNotFoundError("no session binary"))
        monkeypatch.setattr("subprocess.run", rec)
        # Must not raise — best-effort push.
        notify_granted(_entry("abc-123"))

    def test_subprocess_timeout_is_silent_noop(self, monkeypatch):
        import subprocess
        rec = _RecordingRun(raises=subprocess.TimeoutExpired("session", 10))
        monkeypatch.setattr("subprocess.run", rec)
        notify_granted(_entry("abc-123"))  # no raise


# --------------------------------------------------------------------------- #
# notify_granted — blocking vs non-blocking local push (impl-002)
# --------------------------------------------------------------------------- #

class TestNonBlockingDispatch:
    """``block=True`` (default) runs the local push inline; ``block=False``
    fires it off-thread so a caller never waits on session discovery / tmux
    (VM-1625 impl-002)."""

    def test_block_true_runs_synchronously(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            "voice_mode.conch_notify._dispatch_async",
            lambda fn, *a: dispatched.append((fn, a)),
        )
        rec = _RecordingRun(returncode=0)
        monkeypatch.setattr("subprocess.run", rec)

        notify_granted(_entry("cb-sync"), block=True)

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

        notify_granted(_entry("cb-async"), block=False)

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

        notify_granted(_entry("cb-thread"), block=False)

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

        notify_granted(_entry("remote-x", pid=None), block=False)

        assert rec.calls == []
        assert dispatched == []
