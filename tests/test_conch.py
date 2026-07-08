"""Tests for the Conch lock file mechanism."""

import json
import multiprocessing
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import psutil
import pytest

from voice_mode.conch import Conch


def _dead_pid():
    """Spawn a child, let it exit, reap it -> a genuinely dead PID.

    subprocess instead of os.fork() so it also works on Windows. Avoids the
    flaky "PID 999999" pattern -- high-PID systems may have it in use.
    """
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not psutil.pid_exists(proc.pid)
    return proc.pid


def _idle_child():
    """Module-level target for multiprocessing: a live process that just sleeps.

    Used by hold tests that need a real, *other* live PID (the parent's own PID
    is treated as 'self', so two Conch instances in one process can't exercise
    the cross-process hold path)."""
    time.sleep(60)


def _write_marker(pid, *, held, acquired=None, agent="other",
                  session_id=None, project_path=None, expires=None):
    """Write a raw lock-file payload (simulating another holder)."""
    Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    Conch.LOCK_FILE.write_text(json.dumps({
        "pid": pid,
        "agent": agent,
        "session_id": session_id,
        "project_path": project_path,
        "acquired": acquired or datetime.now().isoformat(),
        "held": held,
        "expires": expires,
    }))


@pytest.fixture
def clean_conch():
    """Ensure no conch file exists before/after tests."""
    conch_file = Conch.LOCK_FILE
    if conch_file.exists():
        conch_file.unlink()
    yield
    if conch_file.exists():
        conch_file.unlink()


class TestConch:
    """Tests for Conch class."""

    def test_is_active_returns_false_when_no_lock_file(self, clean_conch):
        """is_active() returns False when lock file doesn't exist."""
        assert Conch.is_active() is False

    def test_acquire_creates_lock_file(self, clean_conch):
        """acquire() creates the lock file with correct content."""
        conch = Conch(agent_name="test_agent")
        conch.acquire()

        assert Conch.LOCK_FILE.exists()

        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["pid"] == os.getpid()
        assert data["agent"] == "test_agent"
        assert "acquired" in data
        assert data["expires"] is None

        conch.release()

    def test_release_removes_lock_file(self, clean_conch):
        """release() removes the lock file."""
        conch = Conch()
        conch.acquire()
        assert Conch.LOCK_FILE.exists()

        conch.release()
        assert not Conch.LOCK_FILE.exists()

    def test_is_active_returns_true_when_lock_held(self, clean_conch):
        """is_active() returns True when lock file exists and PID is alive."""
        conch = Conch()
        conch.acquire()

        assert Conch.is_active() is True

        conch.release()

    def test_is_active_returns_false_for_stale_lock(self, clean_conch):
        """is_active() returns False when PID in lock file is dead."""
        # Create a lock file with a non-existent PID
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": 999999999,  # Very unlikely to be a valid PID
            "agent": "dead_agent",
            "acquired": "2026-01-01T00:00:00",
            "expires": None
        }
        Conch.LOCK_FILE.write_text(json.dumps(data))

        assert Conch.is_active() is False

    def test_context_manager_acquires_and_releases(self, clean_conch):
        """Context manager properly acquires and releases lock."""
        assert Conch.is_active() is False

        with Conch(agent_name="context_test"):
            assert Conch.is_active() is True

        assert Conch.is_active() is False

    def test_context_manager_releases_on_exception(self, clean_conch):
        """Context manager releases lock even if exception occurs."""
        assert Conch.is_active() is False

        try:
            with Conch(agent_name="exception_test"):
                assert Conch.is_active() is True
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert Conch.is_active() is False

    def test_get_holder_returns_lock_info(self, clean_conch):
        """get_holder() returns lock holder information."""
        assert Conch.get_holder() is None

        with Conch(agent_name="holder_test"):
            holder = Conch.get_holder()
            assert holder is not None
            assert holder["agent"] == "holder_test"
            assert holder["pid"] == os.getpid()

        assert Conch.get_holder() is None

    def test_acquire_with_override_agent_name(self, clean_conch):
        """acquire() can override agent name set in constructor."""
        conch = Conch(agent_name="original")
        conch.acquire(agent_name="override")

        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["agent"] == "override"

        conch.release()

    def test_release_handles_missing_file_gracefully(self, clean_conch):
        """release() doesn't error if lock file doesn't exist."""
        conch = Conch()
        # This should not raise
        conch.release()

    def test_is_active_handles_invalid_json(self, clean_conch):
        """is_active() returns False for invalid JSON in lock file."""
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        Conch.LOCK_FILE.write_text("not valid json {{{")

        assert Conch.is_active() is False


class TestConchConfig:
    """Tests for conch configuration options."""

    def test_conch_enabled_default(self):
        """CONCH_ENABLED defaults to True."""
        from voice_mode.config import CONCH_ENABLED
        # Default should be True (unless env var overrides)
        assert isinstance(CONCH_ENABLED, bool)

    def test_conch_timeout_default(self):
        """CONCH_TIMEOUT defaults to 300 seconds (VM-1433: wait through a held
        floor's between-turn gaps rather than bouncing at 60s)."""
        from voice_mode.config import CONCH_TIMEOUT
        assert isinstance(CONCH_TIMEOUT, float)
        assert CONCH_TIMEOUT == 300.0

    def test_conch_hold_expiry_default(self):
        """CONCH_HOLD_EXPIRY defaults to 10s — a SHORT refreshed TTL (VM-1649).

        Was 300s, which let an idle holder wedge the floor for ~5 minutes. A
        between-turns hold only needs to cover the gap between two turns, so the
        default is now 10s (tune toward 5s later).
        """
        from voice_mode.config import CONCH_HOLD_EXPIRY
        assert isinstance(CONCH_HOLD_EXPIRY, float)
        assert CONCH_HOLD_EXPIRY == 10.0

    def test_conch_check_interval_default(self):
        """CONCH_CHECK_INTERVAL defaults to 0.5 seconds."""
        from voice_mode.config import CONCH_CHECK_INTERVAL
        assert isinstance(CONCH_CHECK_INTERVAL, float)
        assert CONCH_CHECK_INTERVAL == 0.5

    def test_conch_enabled_env_var(self):
        """CONCH_ENABLED can be set via environment variable."""
        import os
        import importlib
        import voice_mode.config

        # Test with false
        os.environ["VOICEMODE_CONCH_ENABLED"] = "false"
        importlib.reload(voice_mode.config)
        assert voice_mode.config.CONCH_ENABLED is False

        # Test with true
        os.environ["VOICEMODE_CONCH_ENABLED"] = "true"
        importlib.reload(voice_mode.config)
        assert voice_mode.config.CONCH_ENABLED is True

        # Clean up
        del os.environ["VOICEMODE_CONCH_ENABLED"]
        importlib.reload(voice_mode.config)

    def test_conch_timeout_env_var(self):
        """CONCH_TIMEOUT can be set via environment variable."""
        import os
        import importlib
        import voice_mode.config

        os.environ["VOICEMODE_CONCH_TIMEOUT"] = "120"
        importlib.reload(voice_mode.config)
        assert voice_mode.config.CONCH_TIMEOUT == 120.0

        # Clean up
        del os.environ["VOICEMODE_CONCH_TIMEOUT"]
        importlib.reload(voice_mode.config)


def _pin_lock_file(lock_file):
    """Point this (possibly spawned) process's Conch at the given lock path.

    Spawned child processes re-import voice_mode.conch fresh, so they do NOT
    inherit the parent test's monkeypatched Conch.LOCK_FILE — they'd otherwise
    fall back to the real ~/.voicemode/conch and collide with a live voicemode
    process. Tests pass the isolated lock path explicitly so parent and children
    all share the same (isolated) file.
    """
    if lock_file is not None:
        Conch.LOCK_FILE = lock_file
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)


def _try_acquire_worker(name: str, queue: multiprocessing.Queue, hold_time: float = 0.5,
                        lock_file=None):
    """Worker function for multiprocessing tests.

    Args:
        name: Agent name for the conch
        queue: Queue to report results back
        hold_time: How long to hold the lock if acquired
        lock_file: Isolated conch lock path to use (see _pin_lock_file)
    """
    _pin_lock_file(lock_file)
    conch = Conch(agent_name=name)
    acquired = conch.try_acquire()
    queue.put((name, acquired))
    if acquired:
        time.sleep(hold_time)
        conch.release()


def _acquire_release_then_signal(name: str, queue: multiprocessing.Queue, barrier,
                                 lock_file=None):
    """Acquire, release, then signal completion via barrier."""
    _pin_lock_file(lock_file)
    conch = Conch(agent_name=name)
    acquired = conch.try_acquire()
    queue.put((name, "first_try", acquired))
    if acquired:
        time.sleep(0.1)
        conch.release()
    barrier.wait()


def _wait_then_acquire(name: str, queue: multiprocessing.Queue, barrier,
                       lock_file=None):
    """Wait for barrier then try to acquire."""
    _pin_lock_file(lock_file)
    barrier.wait()
    time.sleep(0.05)  # Small delay to ensure release is complete
    conch = Conch(agent_name=name)
    acquired = conch.try_acquire()
    queue.put((name, "second_try", acquired))
    if acquired:
        conch.release()


class TestConchAtomicLocking:
    """Tests for atomic fcntl-based locking."""

    @pytest.fixture(autouse=True)
    def clean_conch_file(self):
        """Ensure no conch file exists before/after tests."""
        conch_file = Conch.LOCK_FILE
        if conch_file.exists():
            conch_file.unlink()
        yield
        if conch_file.exists():
            conch_file.unlink()

    def test_try_acquire_succeeds_when_not_held(self):
        """try_acquire() returns True when lock is not held."""
        conch = Conch(agent_name="test_agent")
        assert conch.try_acquire() is True
        conch.release()

    def test_try_acquire_fails_when_held(self):
        """try_acquire() returns False when lock is held by another."""
        conch1 = Conch(agent_name="first")
        conch2 = Conch(agent_name="second")

        assert conch1.try_acquire() is True
        assert conch2.try_acquire() is False

        conch1.release()

    def test_try_acquire_returns_true_if_already_holding(self):
        """try_acquire() returns True if we already hold the lock."""
        conch = Conch(agent_name="test")
        assert conch.try_acquire() is True
        # Second call should also return True
        assert conch.try_acquire() is True
        conch.release()

    def test_release_allows_next(self):
        """After release, another process can acquire."""
        conch1 = Conch(agent_name="first")
        conch2 = Conch(agent_name="second")

        assert conch1.try_acquire() is True
        assert conch2.try_acquire() is False

        conch1.release()

        assert conch2.try_acquire() is True
        conch2.release()

    def test_held_seconds_tracking(self):
        """release() returns correct held duration."""
        conch = Conch(agent_name="timing_test")
        conch.try_acquire()
        time.sleep(0.1)
        held = conch.release()
        # Allow some timing slack
        assert 0.09 < held < 0.3, f"Expected held time ~0.1s, got {held}s"

    def test_held_seconds_zero_when_not_acquired(self):
        """release() returns 0.0 when lock was never acquired."""
        conch = Conch()
        held = conch.release()
        assert held == 0.0

    def test_atomic_acquisition_multiprocess(self):
        """Only one process can acquire at a time (multiprocessing test)."""
        results = multiprocessing.Queue()

        # Start two processes simultaneously. Pass the isolated lock path so the
        # spawned children share the parent's (home-isolated) conch file rather
        # than the real ~/.voicemode/conch.
        lock_file = Conch.LOCK_FILE
        p1 = multiprocessing.Process(
            target=_try_acquire_worker, args=("agent1", results, 0.5, lock_file))
        p2 = multiprocessing.Process(
            target=_try_acquire_worker, args=("agent2", results, 0.5, lock_file))

        p1.start()
        p2.start()
        p1.join(timeout=5)
        p2.join(timeout=5)

        # Collect results
        acquisitions = []
        while not results.empty():
            acquisitions.append(results.get())

        # Exactly one should have acquired
        acquired_count = sum(1 for _, acq in acquisitions if acq)
        assert acquired_count == 1, f"Expected 1 acquisition, got {acquired_count}: {acquisitions}"

    def test_sequential_acquisition_after_release_multiprocess(self):
        """After first process releases, second can acquire (multiprocessing)."""
        results = multiprocessing.Queue()
        barrier = multiprocessing.Barrier(2)

        lock_file = Conch.LOCK_FILE
        p1 = multiprocessing.Process(
            target=_acquire_release_then_signal,
            args=("first", results, barrier, lock_file)
        )
        p2 = multiprocessing.Process(
            target=_wait_then_acquire,
            args=("second", results, barrier, lock_file)
        )

        p1.start()
        p2.start()
        p1.join(timeout=5)
        p2.join(timeout=5)

        # Collect results
        acquisitions = {}
        while not results.empty():
            name, phase, acquired = results.get()
            acquisitions[(name, phase)] = acquired

        # First should acquire on first try
        assert acquisitions.get(("first", "first_try")) is True
        # Second should acquire after first releases
        assert acquisitions.get(("second", "second_try")) is True

    def test_lock_file_contains_correct_data(self):
        """Lock file contains PID, agent, and timestamp after try_acquire."""
        conch = Conch(agent_name="data_test")
        conch.try_acquire()

        assert Conch.LOCK_FILE.exists()
        data = json.loads(Conch.LOCK_FILE.read_text())

        assert data["pid"] == os.getpid()
        assert data["agent"] == "data_test"
        assert "acquired" in data
        assert data["expires"] is None

        conch.release()

    def test_try_acquire_with_override_agent_name(self):
        """try_acquire() can override agent name set in constructor."""
        conch = Conch(agent_name="original")
        conch.try_acquire(agent_name="override")

        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["agent"] == "override"

        conch.release()

    def test_try_acquire_clears_dead_holder_lock(self):
        """try_acquire() unlinks a lock owned by a dead PID and acquires.

        Uses the spawn-and-reap pattern: run a child to completion, then
        write a lock file with the reaped (now dead) PID.
        """
        pid = _dead_pid()

        # Write a lock file with the dead PID and a fresh timestamp
        # (so timestamp-based expiry would NOT fire).
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        data = {
            "pid": pid,
            "agent": "dead_agent",
            "acquired": datetime.now().isoformat(),
            "expires": None,
        }
        Conch.LOCK_FILE.write_text(json.dumps(data))

        # A fresh Conch should clear the dead-holder lock and acquire.
        new_conch = Conch(agent_name="new_agent")
        assert new_conch.try_acquire() is True

        # The lock should now be ours.
        new_data = json.loads(Conch.LOCK_FILE.read_text())
        assert new_data["pid"] == os.getpid()
        assert new_data["agent"] == "new_agent"

        new_conch.release()

    def test_try_acquire_clears_dead_holder_lock_with_expiry_disabled(self):
        """Dead-PID clearance works even when CONCH_LOCK_EXPIRY <= 0.

        Operators may opt out of timestamp-based expiry, but a dead holder
        is unambiguously stale and must still be cleared.
        """
        pid = _dead_pid()

        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        data = {
            "pid": pid,
            "agent": "dead_agent",
            "acquired": datetime.now().isoformat(),
            "expires": None,
        }
        Conch.LOCK_FILE.write_text(json.dumps(data))

        # Patch the deferred lock-expiry getter to simulate disabled expiry.
        with patch("voice_mode.conch._get_lock_expiry", return_value=0):
            new_conch = Conch(agent_name="new_agent")
            assert new_conch.try_acquire() is True

        new_conch.release()

    def test_try_acquire_respects_live_holder_lock(self):
        """try_acquire() returns False when a live PID holds a fresh lock."""
        # Write a lock file with our own (live) PID and fresh timestamp.
        # We DON'T use Conch.acquire() because that doesn't take an flock --
        # we need a flock-protected lock to genuinely block try_acquire.
        holder = Conch(agent_name="holder")
        assert holder.try_acquire() is True

        # Sanity: lock file has our live PID.
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["pid"] == os.getpid()

        # A fresh Conch should NOT acquire.
        contender = Conch(agent_name="contender")
        assert contender.try_acquire() is False

        # Lock file is unchanged (still belongs to holder).
        assert Conch.LOCK_FILE.exists()

        holder.release()

    def test_try_acquire_clears_stale_timestamp_with_live_pid(self):
        """Existing behavior: live PID + expired timestamp still clears."""
        # Write a lock file with our live PID but an ancient timestamp.
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": os.getpid(),
            "agent": "stuck_agent",
            "acquired": "2000-01-01T00:00:00",  # Way past any expiry
            "expires": None,
        }
        Conch.LOCK_FILE.write_text(json.dumps(data))

        # A fresh Conch should clear the stale-timestamp lock and acquire.
        new_conch = Conch(agent_name="new_agent")
        assert new_conch.try_acquire() is True

        new_data = json.loads(Conch.LOCK_FILE.read_text())
        assert new_data["agent"] == "new_agent"

        new_conch.release()

    def test_holder_owned_by_another_user_is_treated_as_alive(self):
        """A holder that exists but is not signalable by us must NOT be cleared.

        psutil.pid_exists() returns True for a process owned by another user
        (on POSIX that is the kill(pid, 0) -> EPERM/PermissionError case:
        the kernel refuses the signal, which itself proves the process is
        alive). Clearing the lock would steal the floor from a live holder.
        """
        # Write a lock file with a fresh timestamp and some PID.
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        data = {
            "pid": 12345,
            "agent": "other_user_agent",
            "acquired": datetime.now().isoformat(),
            "expires": None,
        }
        Conch.LOCK_FILE.write_text(json.dumps(data))

        # Mock the liveness probe: process exists (though we couldn't signal it).
        with patch("voice_mode.conch.psutil.pid_exists", return_value=True):
            conch = Conch(agent_name="probe")
            conch._check_and_clear_stale_lock()

        # Lock file must still exist -- treated as alive.
        assert Conch.LOCK_FILE.exists()
        preserved = json.loads(Conch.LOCK_FILE.read_text())
        assert preserved["pid"] == 12345
        assert preserved["agent"] == "other_user_agent"

    def test_release_without_acquire_does_not_delete_lock_file(self):
        """release() on non-holder must NOT delete the lock file.

        Regression test: Previously, release() would unconditionally delete
        ~/.voicemode/conch even when the caller never acquired the lock. This
        destroyed the flock held by the actual owner (on a different inode),
        allowing multiple agents to speak simultaneously.
        """
        # Agent A acquires the conch
        holder = Conch(agent_name="holder")
        assert holder.try_acquire() is True
        assert Conch.LOCK_FILE.exists()

        # Agent B fails to acquire
        blocked = Conch(agent_name="blocked")
        assert blocked.try_acquire() is False

        # Agent B calls release() — this should NOT delete the lock file
        blocked.release()

        # Lock file should still exist (belongs to Agent A)
        assert Conch.LOCK_FILE.exists(), (
            "release() on non-holder deleted the lock file, "
            "breaking flock coordination for the actual holder"
        )

        # Agent A should still be holding the lock
        assert Conch.is_active()

        # Clean up
        holder.release()

    def test_non_holder_release_preserves_flock_coordination(self):
        """After non-holder release(), a third agent cannot acquire.

        This tests the full failure scenario: if release() deletes the file,
        a third caller creates a new file (new inode) and gets its own flock,
        resulting in two agents holding 'exclusive' locks simultaneously.
        """
        # Agent A acquires
        agent_a = Conch(agent_name="agent_a")
        assert agent_a.try_acquire() is True

        # Agent B fails and releases (should be a no-op for the file)
        agent_b = Conch(agent_name="agent_b")
        assert agent_b.try_acquire() is False
        agent_b.release()

        # Agent C should NOT be able to acquire (Agent A still holds it)
        agent_c = Conch(agent_name="agent_c")
        assert agent_c.try_acquire() is False, (
            "Agent C acquired the conch while Agent A still holds it! "
            "This means release() destroyed the lock file and broke coordination."
        )

        # Clean up
        agent_a.release()


class TestConchPayload:
    """VM-1562 / CID-62: enriched lock payload."""

    def test_try_acquire_writes_enriched_payload(self, clean_conch):
        """try_acquire() records session_id, project_path, voice and held=False."""
        conch = Conch(agent_name="cora", session_id="sess-123",
                      project_path="/home/mike/proj", voice="af_sky")
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["session_id"] == "sess-123"
        assert data["project_path"] == "/home/mike/proj"
        assert data["voice"] == "af_sky"
        assert data["held"] is False
        assert data["agent"] == "cora"
        conch.release()

    def test_payload_fields_null_when_not_provided(self, clean_conch):
        """session_id / project_path / voice are null (not missing) when absent."""
        conch = Conch(agent_name="cora")
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["session_id"] is None
        assert data["project_path"] is None
        assert data["voice"] is None
        conch.release()

    def test_voice_visible_to_other_agent_via_get_holder(self, clean_conch):
        """VM-914: another agent can read the holder's voice for clash avoidance."""
        conch = Conch(agent_name="cora-a", voice="af_sky")
        assert conch.try_acquire() is True
        holder = Conch.get_holder()
        assert holder is not None
        assert holder["voice"] == "af_sky"  # a second agent would pick a different one
        conch.release()

    def test_acquire_also_writes_enriched_payload(self, clean_conch):
        """The non-atomic acquire() path carries the same fields."""
        conch = Conch(agent_name="cora")
        conch.acquire(session_id="s9", project_path="/p")
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["session_id"] == "s9"
        assert data["project_path"] == "/p"
        assert data["held"] is False
        conch.release()


class TestConchHold:
    """VM-1433: between-turns hold on the single conch file."""

    def test_hold_keeps_file_and_marks_held(self, clean_conch):
        """release(hold=True) leaves the file with held=True and re-stamps it."""
        conch = Conch(agent_name="cora", session_id="s1", project_path="/p",
                      voice="af_sky")
        assert conch.try_acquire() is True
        conch.release(hold=True)

        assert Conch.LOCK_FILE.exists(), "hold must NOT unlink the file"
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        assert data["pid"] == os.getpid()
        # Enriched fields survive the hand-off to the held state.
        assert data["session_id"] == "s1"
        assert data["project_path"] == "/p"
        assert data["voice"] == "af_sky"

    def test_default_release_still_unlinks(self, clean_conch):
        """release() with no hold is unchanged: file is removed."""
        conch = Conch(agent_name="cora")
        conch.try_acquire()
        conch.release()  # hold defaults to False
        assert not Conch.LOCK_FILE.exists()

    def test_holder_reclaims_its_own_hold(self, clean_conch):
        """The same process re-acquires across a hold (its pid isn't 'other')."""
        conch = Conch(agent_name="cora")
        conch.try_acquire()
        conch.release(hold=True)

        # Next turn: same instance re-acquires the floor it reserved.
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is False  # active call again
        conch.release()

    def test_live_other_hold_blocks_acquire(self, clean_conch):
        """A live hold owned by ANOTHER process blocks try_acquire."""
        proc = multiprocessing.Process(target=_idle_child, daemon=True)
        proc.start()
        try:
            _write_marker(proc.pid, held=True)  # fresh hold by a live other pid
            conch = Conch(agent_name="cora")
            assert conch.try_acquire() is False
            assert Conch.LOCK_FILE.exists(), "must not steal a live hold"
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_dead_holder_hold_is_cleared(self, clean_conch):
        """A hold whose holder PID is dead is cleared immediately (fast-fail)."""
        _write_marker(999999999, held=True)  # dead pid
        conch = Conch(agent_name="cora")
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["pid"] == os.getpid()
        conch.release()

    def test_idle_expired_hold_is_takeable(self, clean_conch):
        """A live-but-stale (idle-expired) hold can be taken."""
        proc = multiprocessing.Process(target=_idle_child, daemon=True)
        proc.start()
        try:
            # Live other pid, but the hold was stamped long ago.
            _write_marker(proc.pid, held=True, acquired="2000-01-01T00:00:00")
            with patch("voice_mode.conch._get_hold_expiry", return_value=60.0):
                conch = Conch(agent_name="cora")
                assert conch.try_acquire() is True
            conch.release()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_active_call_flock_blocks_even_without_hold(self, clean_conch):
        """An in-flight call (flock held, held=False) still blocks others."""
        holder = Conch(agent_name="holderA")
        assert holder.try_acquire() is True  # holds the flock
        other = Conch(agent_name="other")
        # Different instance, same process — but the flock is exclusive per fd.
        assert other.try_acquire() is False
        holder.release()

    def test_write_hold_marks_held_without_flock(self, clean_conch):
        """write_hold() (used by pause_conversation) writes a held marker."""
        Conch.write_hold("pause_conversation", session_id="sp",
                         project_path="/pp")
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        assert data["agent"] == "pause_conversation"
        assert data["session_id"] == "sp"
        assert data["pid"] == os.getpid()


class TestConchHoldTTL:
    """VM-1649: short, refreshed, per-call hold TTL stamped into the payload.

    The wedge bug had two facets and these tests would have caught both:
      (a) the default idle-expiry was far too long (300s);
      (b) a per-call override that only lived in the holder's process was a
          cross-process no-op — other agents read the global default, so the
          override never governed whether the hold was stale. The fix stamps an
          absolute ``expires`` into the lock file and has the cross-process
          staleness checks honour it ahead of the global default.
    """

    def _seconds_until(self, iso_str):
        return (datetime.fromisoformat(iso_str) - datetime.now()).total_seconds()

    def test_hold_stamps_absolute_expires(self, clean_conch):
        """release(hold=True) stamps expires ≈ now + the global TTL (not None)."""
        with patch("voice_mode.conch._get_hold_expiry", return_value=10.0):
            conch = Conch(agent_name="cora")
            assert conch.try_acquire() is True
            conch.release(hold=True)
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        assert data["expires"] is not None, "a hold must stamp an absolute expiry"
        assert 8.0 < self._seconds_until(data["expires"]) <= 10.0

    def test_per_call_timeout_stamped_into_payload(self, clean_conch):
        """A per-call hold_timeout overrides the global default in the payload.

        With a long global default, a holder that asked for a 2s TTL must stamp
        ~2s — proof the override reaches the on-disk payload other agents read.
        """
        with patch("voice_mode.conch._get_hold_expiry", return_value=300.0):
            conch = Conch(agent_name="cora", hold_timeout=2.0)
            assert conch.try_acquire() is True
            conch.release(hold=True)
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert 1.0 < self._seconds_until(data["expires"]) <= 2.0, (
            "per-call hold_timeout must govern the stamped expiry, not the "
            "global default"
        )

    def test_active_lock_has_no_expires(self, clean_conch):
        """An active (flock-held) lock carries no expiry — only holds do."""
        conch = Conch(agent_name="cora", hold_timeout=2.0)
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is False
        assert data["expires"] is None
        conch.release()

    def test_short_override_lapses_despite_long_global(self, clean_conch):
        """THE cross-process regression: a holder's short expires governs.

        Another live process holds, but its stamped expires is already in the
        past. Even with a LONG global default (300s — what the would-be acquirer
        reads), the hold must be takeable. Before the fix the acquirer honoured
        only the global default, so this would (wrongly) stay blocked: the
        per-call override was a cross-process no-op.
        """
        proc = multiprocessing.Process(target=_idle_child, daemon=True)
        proc.start()
        try:
            past = (datetime.now() - timedelta(seconds=1)).isoformat()
            _write_marker(proc.pid, held=True, expires=past)
            with patch("voice_mode.conch._get_hold_expiry", return_value=300.0):
                conch = Conch(agent_name="cora")
                assert conch.try_acquire() is True, (
                    "a hold past its stamped expires must be takeable even when "
                    "the global default is long"
                )
            conch.release()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_long_override_respected_despite_short_global(self, clean_conch):
        """A holder's far-future expires blocks acquisition despite a short global.

        The hold was stamped long ago (so the global-default fallback would call
        it stale), but its absolute expires is in the future. The acquirer must
        honour the stamped expires and stay blocked — proof expires is consulted
        ahead of acquired + global default.
        """
        proc = multiprocessing.Process(target=_idle_child, daemon=True)
        proc.start()
        try:
            future = (datetime.now() + timedelta(seconds=60)).isoformat()
            _write_marker(proc.pid, held=True,
                          acquired="2000-01-01T00:00:00", expires=future)
            with patch("voice_mode.conch._get_hold_expiry", return_value=1.0):
                conch = Conch(agent_name="cora")
                assert conch.try_acquire() is False, (
                    "a hold with a future stamped expires must be respected even "
                    "when the acquired timestamp looks stale to the global window"
                )
                assert Conch.LOCK_FILE.exists(), "must not steal a live hold"
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_idle_hold_lapses_after_short_default(self, clean_conch):
        """An idle hold older than the (now short) default lapses — no wedge.

        This is the headline bug: with the old 300s default an idle holder sat
        on the floor for minutes. With the 10s default a hold stamped 15s ago
        (no per-call expires) is takeable; one stamped 3s ago is not.
        """
        proc = multiprocessing.Process(target=_idle_child, daemon=True)
        proc.start()
        try:
            with patch("voice_mode.conch._get_hold_expiry", return_value=10.0):
                stale = (datetime.now() - timedelta(seconds=15)).isoformat()
                _write_marker(proc.pid, held=True, acquired=stale)
                takeable = Conch(agent_name="cora")
                assert takeable.try_acquire() is True
                takeable.release()

                fresh = (datetime.now() - timedelta(seconds=3)).isoformat()
                _write_marker(proc.pid, held=True, acquired=fresh)
                blocked = Conch(agent_name="cora")
                assert blocked.try_acquire() is False
                assert Conch.LOCK_FILE.exists()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_write_hold_stamps_expires(self, clean_conch):
        """write_hold (pause_conversation) also stamps an absolute expiry."""
        with patch("voice_mode.conch._get_hold_expiry", return_value=10.0):
            Conch.write_hold("pause_conversation", hold_timeout=4.0)
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["expires"] is not None
        assert 3.0 < self._seconds_until(data["expires"]) <= 4.0

    def test_hold_timeout_disabled_stamps_no_expires(self, clean_conch):
        """TTL <= 0 disables idle-expiry: a hold stamps expires=None."""
        with patch("voice_mode.conch._get_hold_expiry", return_value=0.0):
            conch = Conch(agent_name="cora")
            assert conch.try_acquire() is True
            conch.release(hold=True)
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        assert data["expires"] is None
