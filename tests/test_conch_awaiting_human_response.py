"""Test suite for the `awaiting_human_response` Conch state
(feat(conch): add awaiting_human_response priority-override state).

Covers the new `Conch.mark_awaiting_human_response`/
`awaiting_human_response_active`/`resolve_awaiting_human_response`
classmethods, the module-level `_process_start_time`/`_is_same_process`
helpers, the new branches in `_held_by_other()`/`_check_and_clear_stale_lock()`,
and the `skip_conch` hard-no-op guard in `converse.py`.

Runs on native Windows Python as well as Linux/macOS: `voice_mode/conch.py`
uses `psutil.pid_exists`/`psutil.Process.create_time()` and
`voice_mode.file_lock.lock_exclusive`/`unlock` rather than `fcntl`/`os.kill`,
so nothing here requires WSL. Fabricated "alive other process" scenarios
use a real subprocess pid rather than a hardcoded pid=1, since a fixed pid
number is not guaranteed to exist across platforms.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from voice_mode.conch import (
    Conch,
    _hold_is_expired,
    _response_deadline_passed,
    _process_start_time,
    _is_same_process,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERSE_PY = REPO_ROOT / "voice_mode" / "tools" / "converse.py"


# ---------------------------------------------------------------------------
# Shared harness: isolate Conch.LOCK_FILE to a scratch temp dir per test.
# ---------------------------------------------------------------------------
class ConchIsolationMixin:
    def setUp(self):
        self._orig_lock_file = Conch.LOCK_FILE
        self._tmpdir = tempfile.mkdtemp(prefix="conch-ahr-test-")
        Conch.LOCK_FILE = Path(self._tmpdir) / "conch"

    def tearDown(self):
        Conch.LOCK_FILE = self._orig_lock_file
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _read_raw(self) -> dict:
        return json.loads(Conch.LOCK_FILE.read_text())

    def _write_raw(self, data: dict) -> None:
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        Conch.LOCK_FILE.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# 1. Normal flock/hold behavior unaffected -- regression vs. today's
#    two-state (held True/False) behavior.
# ---------------------------------------------------------------------------
class TestNormalBehaviorRegression(ConchIsolationMixin, unittest.TestCase):
    def test_acquire_and_release_basic(self):
        c = Conch(agent_name="tester")
        self.assertTrue(c.try_acquire())
        payload = self._read_raw()
        self.assertEqual(payload["held"], False)
        self.assertIsNone(payload.get("awaiting_human_response"))
        c.release()
        self.assertFalse(Conch.LOCK_FILE.exists())

    def test_hold_then_same_process_reclaims(self):
        c = Conch(agent_name="tester")
        self.assertTrue(c.try_acquire())
        c.release(hold=True)
        payload = self._read_raw()
        self.assertTrue(payload["held"])
        self.assertIsNone(payload.get("awaiting_human_response"))
        c2 = Conch(agent_name="tester")
        self.assertTrue(c2.try_acquire())
        c2.release()

    def test_hold_marker_blocks_other_pid_until_idle_expiry(self):
        # A real, genuinely-alive subprocess pid -- portable across
        # Windows/Linux (unlike the original suite's pid=1 fabrication,
        # which relied on Unix-only kill(1,0) PermissionError semantics
        # that psutil.pid_exists no longer exhibits).
        holder_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            time.sleep(0.2)
            self._write_raw({
                "pid": holder_proc.pid,
                "agent": "other",
                "session_id": None,
                "project_path": None,
                "voice": None,
                "acquired": datetime.now().isoformat(),
                "held": True,
                "expires": None,
            })
            self.assertTrue(Conch._held_by_other())
            c = Conch(agent_name="tester")
            self.assertFalse(c.try_acquire())

            # Now age it past the fallback 10s idle-expiry window.
            self._write_raw({
                "pid": holder_proc.pid,
                "agent": "other",
                "session_id": None,
                "project_path": None,
                "voice": None,
                "acquired": (datetime.now() - timedelta(seconds=11)).isoformat(),
                "held": True,
                "expires": None,
            })
            self.assertFalse(Conch._held_by_other())
            c2 = Conch(agent_name="tester")
            self.assertTrue(c2.try_acquire())  # stale hold cleared, reacquire succeeds
            c2.release()
        finally:
            holder_proc.kill()
            holder_proc.wait(timeout=5)

    def test_real_cross_process_active_lock_blocks_second_acquirer(self):
        """Genuine cross-process regression check using the real
        lock_exclusive/unlock (not fabricated JSON): a subprocess holds an
        ACTIVE lock (held=False, real kernel/file lock taken) for a short
        window; the parent process must be refused, unaffected by this
        patch."""
        holder_script = textwrap.dedent(f"""
            import sys, time
            from pathlib import Path
            import voice_mode.conch as conch_mod
            conch_mod.Conch.LOCK_FILE = Path({str(Conch.LOCK_FILE)!r})
            c = conch_mod.Conch(agent_name="holder-proc")
            assert c.try_acquire()
            time.sleep(1.2)
            c.release()
        """)
        proc = subprocess.Popen([sys.executable, "-c", holder_script])
        try:
            time.sleep(0.4)  # let the child actually acquire first
            c = Conch(agent_name="parent")
            self.assertFalse(c.try_acquire())
        finally:
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# 2. The new awaiting_human_response state itself.
# ---------------------------------------------------------------------------
class TestAwaitingHumanResponseState(ConchIsolationMixin, unittest.TestCase):
    def test_mark_creates_expected_fresh_payload(self):
        before = datetime.now()
        Conch.mark_awaiting_human_response(deadline_seconds=5)
        payload = self._read_raw()
        self.assertEqual(payload["pid"], os.getpid())
        self.assertTrue(payload["held"])
        self.assertTrue(payload["awaiting_human_response"])
        self.assertIn("response_deadline", payload)
        deadline = datetime.fromisoformat(payload["response_deadline"])
        self.assertTrue(before + timedelta(seconds=4) < deadline < before + timedelta(seconds=6))
        self.assertEqual(payload["expires"], payload["response_deadline"])

    def test_mark_preserves_existing_holder_payload_fields(self):
        c = Conch(agent_name="cora", session_id="sess-1", project_path="/proj", voice="nova")
        self.assertTrue(c.try_acquire())
        original_pid = self._read_raw()["pid"]

        Conch.mark_awaiting_human_response(deadline_seconds=30)
        payload = self._read_raw()
        self.assertEqual(payload["agent"], "cora")
        self.assertEqual(payload["session_id"], "sess-1")
        self.assertEqual(payload["project_path"], "/proj")
        self.assertEqual(payload["voice"], "nova")
        self.assertEqual(payload["pid"], original_pid)
        self.assertTrue(payload["held"])
        self.assertTrue(payload["awaiting_human_response"])

    def test_mark_with_no_prior_file_creates_minimal_marker(self):
        self.assertFalse(Conch.LOCK_FILE.exists())
        Conch.mark_awaiting_human_response(deadline_seconds=10)
        payload = self._read_raw()
        self.assertEqual(payload["agent"], "unknown")
        self.assertTrue(payload["awaiting_human_response"])

    def test_mark_again_while_already_awaiting_extends_deadline_without_corruption(self):
        """Calling mark_awaiting_human_response() a second time while
        already in the awaiting state (e.g. a fresh question arrives before
        the first one's deadline) must extend the deadline cleanly --
        preserving pid/pid_start_time/agent identity, not duplicating or
        corrupting the payload."""
        c = Conch(agent_name="cora", session_id="sess-1")
        self.assertTrue(c.try_acquire())
        Conch.mark_awaiting_human_response(deadline_seconds=5)
        first = self._read_raw()

        Conch.mark_awaiting_human_response(deadline_seconds=60)
        second = self._read_raw()

        self.assertEqual(second["pid"], first["pid"])
        self.assertEqual(second["pid_start_time"], first["pid_start_time"])
        self.assertEqual(second["agent"], "cora")
        self.assertEqual(second["session_id"], "sess-1")
        self.assertTrue(second["awaiting_human_response"])
        second_deadline = datetime.fromisoformat(second["response_deadline"])
        first_deadline = datetime.fromisoformat(first["response_deadline"])
        self.assertGreater(second_deadline, first_deadline)
        self.assertEqual(second["expires"], second["response_deadline"])

    def test_mark_derives_pid_start_time_from_the_preserved_pid_not_the_caller(self):
        other_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            time.sleep(0.2)
            other_pid = other_proc.pid
            other_real_start = _process_start_time(other_pid)
            if other_real_start is None:
                self.skipTest("_process_start_time unavailable on this platform (non-Linux /proc)")
            self._write_raw({
                "pid": other_pid,
                "agent": "other-real-holder",
                "session_id": None,
                "project_path": None,
                "voice": None,
                "acquired": datetime.now().isoformat(),
                "held": True,
                "expires": None,
            })
            Conch.mark_awaiting_human_response(deadline_seconds=60)
            payload = self._read_raw()
            self.assertEqual(payload["pid"], other_pid, "the original pid must be preserved")
            self.assertEqual(
                payload["pid_start_time"], other_real_start,
                "must stamp the PRESERVED pid's own start-time, not the caller's",
            )
            self.assertNotEqual(payload["pid_start_time"], _process_start_time(os.getpid()))
        finally:
            other_proc.kill()
            other_proc.wait(timeout=5)

    def test_response_deadline_passed_missing_or_malformed_is_false(self):
        self.assertFalse(_response_deadline_passed({}))
        self.assertFalse(_response_deadline_passed({"response_deadline": None}))
        self.assertFalse(_response_deadline_passed({"response_deadline": "not-a-date"}))

    def _mark_awaiting_as_other_process(self, deadline_seconds: float, fake_pid: int = 999_996) -> None:
        now = datetime.now()
        deadline_iso = (now + timedelta(seconds=deadline_seconds)).isoformat()
        self._write_raw({
            "pid": fake_pid,
            "agent": "other-agent",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": now.isoformat(),
            "held": True,
            "expires": deadline_iso,
            "awaiting_human_response": True,
            "response_deadline": deadline_iso,
        })

    def test_new_state_blocks_second_acquirer_other_process(self):
        self._mark_awaiting_as_other_process(deadline_seconds=60)
        self.assertTrue(Conch._held_by_other())
        c2 = Conch(agent_name="someone-else")
        self.assertFalse(c2.try_acquire())

    def test_same_process_can_resume_after_marking_awaiting_response(self):
        Conch.mark_awaiting_human_response(deadline_seconds=60)  # stamps OUR OWN pid
        self.assertFalse(Conch._held_by_other(), "own pid must be exempt from own awaiting_human_response")
        c = Conch(agent_name="same-process-resuming")
        self.assertTrue(c.try_acquire())
        c.release()

    def test_new_state_blocks_unconditionally_even_for_a_dead_pid(self):
        self._write_raw({
            "pid": 999_999_999,  # not a real pid
            "agent": "dead-holder",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": True,
            "expires": (datetime.now() + timedelta(seconds=60)).isoformat(),
            "awaiting_human_response": True,
            "response_deadline": (datetime.now() + timedelta(seconds=60)).isoformat(),
        })
        self.assertTrue(Conch._held_by_other())
        c = Conch(agent_name="someone-else")
        self.assertFalse(c.try_acquire())

    def test_check_and_clear_stale_lock_does_not_unlink_during_active_window(self):
        self._write_raw({
            "pid": 999_999_999,
            "agent": "dead-holder",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": True,
            "expires": (datetime.now() + timedelta(seconds=60)).isoformat(),
            "awaiting_human_response": True,
            "response_deadline": (datetime.now() + timedelta(seconds=60)).isoformat(),
        })
        c = Conch(agent_name="someone-else")
        c._check_and_clear_stale_lock()
        self.assertTrue(Conch.LOCK_FILE.exists(), "marker was unlinked before its own response_deadline passed")

    def test_block_expires_after_response_deadline(self):
        self._mark_awaiting_as_other_process(deadline_seconds=0.3)
        self.assertTrue(Conch._held_by_other())
        c = Conch(agent_name="someone-else")
        self.assertFalse(c.try_acquire())

        time.sleep(0.45)
        self.assertFalse(Conch._held_by_other())
        c2 = Conch(agent_name="someone-else")
        self.assertTrue(c2.try_acquire())
        c2.release()

    def test_old_two_state_shape_never_triggers_new_branches(self):
        self._write_raw({
            "pid": os.getpid(),
            "agent": "me",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": False,
            "expires": None,
        })
        data = json.loads(Conch.LOCK_FILE.read_text())
        self.assertFalse(bool(data.get("awaiting_human_response")))
        self.assertFalse(_response_deadline_passed(data))
        self.assertFalse(Conch._held_by_other())


# ---------------------------------------------------------------------------
# 3. converse.py's skip_conch guard -- extracted and exec'd, since the full
#    4500+-line module can't be imported standalone in this stripped test
#    environment (sounddevice, fastmcp, etc. would need to be mocked).
# ---------------------------------------------------------------------------
def _extract_skip_conch_guard_source() -> str:
    src = CONVERSE_PY.read_text(encoding="utf-8")
    start_marker = "        if CONCH_ENABLED and skip_conch:\n"
    end_marker = "\n        # Try to acquire conch atomically"
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    snippet = src[start:end]
    return textwrap.dedent(snippet)


class TestConverseSkipConchGuard(ConchIsolationMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.snippet = _extract_skip_conch_guard_source()
        self.assertIn("awaiting_human_response_active", self.snippet)
        self.assertIn("skip_conch = False", self.snippet)

    def _run_guard(self, *, conch_enabled: bool, skip_conch: bool) -> bool:
        namespace = {
            "CONCH_ENABLED": conch_enabled,
            "skip_conch": skip_conch,
            "Conch": Conch,
        }
        exec(compile(self.snippet, "<skip_conch_guard>", "exec"), namespace)
        return namespace["skip_conch"]

    def _mark_awaiting_as_other_process(self, deadline_seconds: float, fake_pid: int = 999999) -> None:
        now = datetime.now()
        deadline_iso = (now + timedelta(seconds=deadline_seconds)).isoformat()
        self._write_raw({
            "pid": fake_pid,
            "agent": "other-agent",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": now.isoformat(),
            "held": True,
            "expires": deadline_iso,
            "awaiting_human_response": True,
            "response_deadline": deadline_iso,
        })

    def test_skip_conch_hard_no_op_while_awaiting_human_response_active(self):
        self._mark_awaiting_as_other_process(deadline_seconds=60)
        result = self._run_guard(conch_enabled=True, skip_conch=True)
        self.assertFalse(result, "skip_conch=True must be downgraded to False while active")

    def test_skip_conch_behaves_normally_once_deadline_passed(self):
        self._mark_awaiting_as_other_process(deadline_seconds=0.2)
        time.sleep(0.3)
        result = self._run_guard(conch_enabled=True, skip_conch=True)
        self.assertTrue(result, "skip_conch=True must NOT be overridden once the deadline has passed")

    def test_skip_conch_behaves_normally_with_no_holder_at_all(self):
        self.assertFalse(Conch.LOCK_FILE.exists())
        result = self._run_guard(conch_enabled=True, skip_conch=True)
        self.assertTrue(result)

    def test_skip_conch_behaves_normally_when_holder_not_awaiting_response(self):
        c = Conch(agent_name="normal-holder")
        self.assertTrue(c.try_acquire())
        result = self._run_guard(conch_enabled=True, skip_conch=True)
        self.assertTrue(result, "an ordinary active/held holder must not force skip_conch off")

    def test_guard_is_noop_when_conch_disabled_entirely(self):
        self._mark_awaiting_as_other_process(deadline_seconds=60)
        result = self._run_guard(conch_enabled=False, skip_conch=True)
        self.assertTrue(result, "CONCH_ENABLED=False must bypass the whole mechanism, unchanged")

    def test_guard_is_noop_when_caller_did_not_request_skip(self):
        self._mark_awaiting_as_other_process(deadline_seconds=60)
        result = self._run_guard(conch_enabled=True, skip_conch=False)
        self.assertFalse(result)

    def test_guard_still_treats_own_pid_as_not_blocking(self):
        Conch.mark_awaiting_human_response(deadline_seconds=60)  # stamps OUR OWN pid
        result = self._run_guard(conch_enabled=True, skip_conch=True)
        self.assertTrue(result, "the original holder's own process must not be blocked by its own state")

    def test_guard_unaffected_by_short_conch_lock_expiry(self):
        """Regression test for the (now-fixed) upstream CRITICAL finding:
        an earlier draft used Conch.get_holder(), which goes stale as soon
        as CONCH_LOCK_EXPIRY elapses OR the holder pid dies -- independent
        of response_deadline. The shipped guard (awaiting_human_response_active())
        must stay correct regardless of CONCH_LOCK_EXPIRY or pid liveness."""
        import types
        had_voice_mode_config = "voice_mode.config" in sys.modules
        orig_config = sys.modules.get("voice_mode.config")
        fake_config = types.ModuleType("voice_mode.config")
        fake_config.CONCH_LOCK_EXPIRY = 0.2  # much shorter than our response_deadline below
        fake_config.CONCH_HOLD_EXPIRY = 10.0
        sys.modules["voice_mode.config"] = fake_config
        try:
            # A dead pid too, not just a live-but-expired one.
            self._mark_awaiting_as_other_process(deadline_seconds=5.0, fake_pid=999998)
            self.assertIsNone(Conch.get_holder(), "sanity: get_holder() DOES go stale on a dead pid")
            result = self._run_guard(conch_enabled=True, skip_conch=True)
            self.assertFalse(
                result,
                "the fixed guard must still block skip_conch even though get_holder() itself is stale",
            )
        finally:
            if had_voice_mode_config:
                sys.modules["voice_mode.config"] = orig_config
            else:
                sys.modules.pop("voice_mode.config", None)


# ---------------------------------------------------------------------------
# 4. Independent-audit findings: pid-reuse protection for the same-process
#    exemption, and a precondition guard on resolve_awaiting_human_response().
# ---------------------------------------------------------------------------
class TestProcessStartTimeHelper(unittest.TestCase):
    def test_returns_none_for_a_nonexistent_pid(self):
        self.assertIsNone(_process_start_time(999_999_999))

    def test_is_stable_across_repeated_calls_for_the_same_process(self):
        first = _process_start_time(os.getpid())
        second = _process_start_time(os.getpid())
        self.assertEqual(first, second)

    def test_returns_a_parseable_float_string_for_the_current_real_process(self):
        """_process_start_time is now psutil.Process.create_time()-backed
        (a float epoch-seconds value), portable across platforms -- unlike
        the earlier Linux-only /proc/<pid>/stat tick-count implementation,
        it should never legitimately return None for the current, real,
        live process on any supported platform."""
        result = _process_start_time(os.getpid())
        self.assertIsNotNone(result)
        float(result)  # must be parseable; raises ValueError if not


class TestPidReuseProtection(ConchIsolationMixin, unittest.TestCase):
    def test_matching_pid_but_wrong_start_time_is_not_treated_as_self(self):
        real_start = _process_start_time(os.getpid())
        if real_start is None:
            self.skipTest("_process_start_time unavailable on this platform (non-Linux /proc)")
        self._write_raw({
            "pid": os.getpid(),
            "pid_start_time": "not-our-real-start-time",
            "agent": "someone-else-with-our-recycled-pid",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": True,
            "expires": (datetime.now() + timedelta(seconds=60)).isoformat(),
            "awaiting_human_response": True,
            "response_deadline": (datetime.now() + timedelta(seconds=60)).isoformat(),
        })
        self.assertTrue(
            Conch._held_by_other(),
            "a pid match with a mismatched start-time must NOT grant the same-process exemption",
        )
        c = Conch(agent_name="someone-else")
        self.assertFalse(c.try_acquire())

    def test_matching_pid_and_correct_start_time_is_treated_as_self(self):
        real_start = _process_start_time(os.getpid())
        if real_start is None:
            self.skipTest("_process_start_time unavailable on this platform (non-Linux /proc)")
        self._write_raw({
            "pid": os.getpid(),
            "pid_start_time": real_start,
            "agent": "me",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": True,
            "expires": (datetime.now() + timedelta(seconds=60)).isoformat(),
            "awaiting_human_response": True,
            "response_deadline": (datetime.now() + timedelta(seconds=60)).isoformat(),
        })
        self.assertFalse(Conch._held_by_other(), "genuinely matching pid+start_time must be exempt")
        self.assertIsNone(Conch.awaiting_human_response_active())

    def test_missing_pid_start_time_in_payload_fails_closed(self):
        # An older-shaped marker (pre-fix, no pid_start_time field at all)
        # with our own real pid -- must fail CLOSED regardless of platform,
        # since _is_same_process() requires BOTH own_start and the stamped
        # pid_start_time to be non-None and equal.
        self._write_raw({
            "pid": os.getpid(),
            "agent": "me-but-old-shape",
            "session_id": None,
            "project_path": None,
            "voice": None,
            "acquired": datetime.now().isoformat(),
            "held": True,
            "expires": (datetime.now() + timedelta(seconds=60)).isoformat(),
            "awaiting_human_response": True,
            "response_deadline": (datetime.now() + timedelta(seconds=60)).isoformat(),
        })
        self.assertTrue(
            Conch._held_by_other(),
            "a payload with no pid_start_time at all must fail closed (not exempted)",
        )

    def test_is_same_process_helper_directly(self):
        real_start = _process_start_time(os.getpid())
        self.assertFalse(_is_same_process({"pid": os.getpid(), "pid_start_time": "wrong"}))
        self.assertFalse(_is_same_process({"pid": 999_999_999, "pid_start_time": real_start}))
        self.assertFalse(_is_same_process({"pid": os.getpid()}))  # no pid_start_time at all
        self.assertFalse(_is_same_process({}))
        if real_start is not None:
            self.assertTrue(_is_same_process({"pid": os.getpid(), "pid_start_time": real_start}))


class TestResolveAwaitingHumanResponseGuard(ConchIsolationMixin, unittest.TestCase):
    def test_does_not_unlink_an_unrelated_active_holder(self):
        c = Conch(agent_name="normal-active-holder")
        self.assertTrue(c.try_acquire())
        self.assertTrue(Conch.LOCK_FILE.exists())
        result = Conch.resolve_awaiting_human_response()
        self.assertFalse(result, "must refuse to touch a lock file that isn't in the awaiting state")
        self.assertTrue(Conch.LOCK_FILE.exists(), "the unrelated active holder's file must survive untouched")
        c.release()

    def test_does_not_unlink_a_normal_hold(self):
        c = Conch(agent_name="normal-hold")
        self.assertTrue(c.try_acquire())
        c.release(hold=True)
        self.assertTrue(Conch.LOCK_FILE.exists())
        result = Conch.resolve_awaiting_human_response()
        self.assertFalse(result)
        self.assertTrue(Conch.LOCK_FILE.exists())

    def test_unlinks_a_genuine_awaiting_human_response_marker(self):
        Conch.mark_awaiting_human_response(deadline_seconds=60)
        self.assertTrue(Conch.LOCK_FILE.exists())
        result = Conch.resolve_awaiting_human_response()
        self.assertTrue(result)
        self.assertFalse(Conch.LOCK_FILE.exists())

    def test_missing_file_returns_false_not_an_error(self):
        self.assertFalse(Conch.LOCK_FILE.exists())
        result = Conch.resolve_awaiting_human_response()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
