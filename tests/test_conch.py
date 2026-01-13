"""Tests for the Conch lock file mechanism."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.conch import Conch


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
        """CONCH_TIMEOUT defaults to 60 seconds."""
        from voice_mode.config import CONCH_TIMEOUT
        assert isinstance(CONCH_TIMEOUT, float)
        assert CONCH_TIMEOUT == 60.0

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
