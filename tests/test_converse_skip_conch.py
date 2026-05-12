"""Tests for converse's skip_conch parameter (VM-1264).

skip_conch=True must bypass the conch coordination entirely:
- Don't try to acquire the lock.
- Don't return the "User is currently speaking with X" status message
  when another agent holds the conch.
- Don't release / delete a lock file owned by another process.

We patch ``Conch.try_acquire`` because faithfully simulating a foreign
holder requires holding an actual ``fcntl.flock`` from another process --
overkill for a unit test of the bypass branch.
"""

from unittest.mock import patch

import pytest

from voice_mode.conch import Conch


@pytest.fixture
def clean_conch():
    """Ensure no conch file exists before/after each test."""
    conch_file = Conch.LOCK_FILE
    if conch_file.exists():
        conch_file.unlink()
    yield
    if conch_file.exists():
        conch_file.unlink()


class TestConverseSkipConch:
    """skip_conch=True must bypass coordination without harming other holders."""

    @pytest.mark.asyncio
    async def test_default_returns_blocked_when_other_holder(self, clean_conch):
        """Baseline: without skip_conch, an unavailable conch returns the blocked string."""
        from voice_mode.tools.converse import converse

        # Simulate "another agent owns the conch" by making try_acquire always fail.
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(
                 Conch, "get_holder",
                 return_value={"pid": 99999, "agent": "other_agent"},
             ):
            result = await getattr(converse, "fn", converse)(
                message="Hello",
                wait_for_response=False,
            )

        assert "User is currently speaking" in result, (
            f"Without skip_conch, blocked conch must surface as status string. Got: {result!r}"
        )

    @pytest.mark.asyncio
    async def test_skip_conch_bypasses_blocked_status(self, clean_conch):
        """skip_conch=True must NOT return the 'User is currently speaking' string,
        even if try_acquire would have failed."""
        from voice_mode.tools.converse import converse

        called = {"try_acquire": 0}

        def fake_try_acquire(self, agent_name=None):
            called["try_acquire"] += 1
            return False  # If anything tries to acquire, it would block.

        with patch.object(Conch, "try_acquire", new=fake_try_acquire), \
             patch(
                 "voice_mode.tools.converse.text_to_speech_with_failover",
                 return_value=(False, {}, {"provider": "test"}),
             ):
            result = await getattr(converse, "fn", converse)(
                message="Hello",
                wait_for_response=False,
                skip_conch=True,
            )

        assert "User is currently speaking" not in result, (
            f"skip_conch=True should bypass coordination. Got: {result!r}"
        )
        assert called["try_acquire"] == 0, (
            "skip_conch=True must not call try_acquire at all "
            f"(called {called['try_acquire']} times)"
        )

    @pytest.mark.asyncio
    async def test_skip_conch_does_not_release_unowned_lock(self, clean_conch):
        """skip_conch=True must NOT delete a lock file it doesn't own.

        The release() path already guards on conch._acquired; this test pins
        that invariant against the skip_conch branch specifically.
        """
        import json
        from datetime import datetime
        from voice_mode.tools.converse import converse

        # Plant a lock file that looks like it belongs to another agent.
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        planted = {
            "pid": 99999,
            "agent": "other_agent",
            "acquired": datetime.now().isoformat(),
            "expires": None,
        }
        Conch.LOCK_FILE.write_text(json.dumps(planted))

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch(
                 "voice_mode.tools.converse.text_to_speech_with_failover",
                 return_value=(False, {}, {"provider": "test"}),
             ):
            await getattr(converse, "fn", converse)(
                message="Hello",
                wait_for_response=False,
                skip_conch=True,
            )

        assert Conch.LOCK_FILE.exists(), (
            "skip_conch=True must not unlink another agent's lock file"
        )
        survivor = json.loads(Conch.LOCK_FILE.read_text())
        assert survivor == planted, (
            f"Other agent's lock file mutated: {survivor!r} != {planted!r}"
        )

    @pytest.mark.asyncio
    async def test_skip_conch_accepts_string_true(self, clean_conch):
        """String 'true' must coerce to bool True, matching sibling flags."""
        from voice_mode.tools.converse import converse

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch(
                 "voice_mode.tools.converse.text_to_speech_with_failover",
                 return_value=(False, {}, {"provider": "test"}),
             ):
            result = await getattr(converse, "fn", converse)(
                message="Hello",
                wait_for_response=False,
                skip_conch="true",
            )

        assert "User is currently speaking" not in result
