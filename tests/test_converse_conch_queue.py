"""Tests for converse()'s conch-queue integration (VM-1619).

When the conch is busy, ``converse`` no longer blind-polls. It is a first-class
participant in the VM-1613 waiter queue:

- ``wait_for_conch`` falsy (default): return IMMEDIATELY with a status, NEVER
  queue (Mike's hard constraint — never silently block an opt-out caller).
- ``wait_for_conch`` truthy: ``ConchQueue.register`` then block until granted
  (FIFO via the grant hint), bounded by timeout; deregister cleanly on
  timeout.

VM-2078 removed ``conch_mode``/callback mode entirely: there is no longer a
register-and-return path, and every registration blocks and polls.

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py, which re-pins ``Conch.LOCK_FILE`` into a per-test fake home;
``ConchQueue`` derives all its paths from ``Conch.LOCK_FILE.parent``, so the
whole queue lives in that isolated home automatically.

The positive WAIT test uses a REAL in-process conch holder (an ``fcntl``
flock conflicts even between two fds in the same process), so ``try_acquire``
is exercised for real — only ``text_to_speech_with_failover`` is mocked, since
faithfully producing audio is irrelevant to the queue logic.
"""

import asyncio

import pytest
from unittest.mock import patch

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue


def _converse():
    """The undecorated converse coroutine (FastMCP wraps it as ``.fn``)."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


def _sessions():
    """Session ids currently in the live queue, in order."""
    return [e.session_id for e in ConchQueue.list()]


def _entry(session_id):
    """The live queue entry for ``session_id`` (or None)."""
    for e in ConchQueue.list():
        if e.session_id == session_id:
            return e
    return None


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


FAKE_HOLDER = {"pid": 999999, "agent": "other_agent", "session_id": "holder-x"}


# --------------------------------------------------------------------------- #
# wait_for_conch falsy — immediate return, NEVER queue (back-compat + Mike's rule)
# --------------------------------------------------------------------------- #

class TestFalsyGateNeverQueues:
    @pytest.mark.asyncio
    async def test_busy_falsy_returns_immediately_no_registration(self, clean_conch):
        """Busy + wait_for_conch=False → immediate status, and NO queue entry."""
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=False,
                session_id="sess-a",
            )

        assert "other_agent" in result
        assert "NOT queued" in result
        # The opt-out caller must not be left registered anywhere.
        assert _sessions() == [], f"falsy gate must not register a waiter; got {_sessions()}"

    @pytest.mark.asyncio
    async def test_falsy_message_tells_caller_how_to_queue(self, clean_conch):
        """The immediate status tells the agent how to join the queue."""
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                session_id="sess-a",
            )
        assert "wait_for_conch=true" in result
        # VM-2078: no more callback mode to advertise -- no register-and-return
        # path exists any more.
        assert "conch_mode" not in result
        assert "callback" not in result.lower()


# --------------------------------------------------------------------------- #
# WAIT — timeout deregisters cleanly; FIFO grant gates acquisition
# --------------------------------------------------------------------------- #

class TestWaitMode:
    @pytest.mark.asyncio
    async def test_wait_timeout_deregisters_cleanly(self, clean_conch, monkeypatch):
        """A blocked wait that never gets granted times out AND leaves no
        wedged entry."""
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=0.03,   # number ⇒ wait, timeout 0.03s
                session_id="sess-a",
            )

        assert "Timed out" in result
        assert "background" in result.lower(), \
            "timeout message should point at backgrounding the call instead"
        assert _sessions() == [], f"timeout must deregister the waiter; got {_sessions()}"

    @pytest.mark.asyncio
    async def test_wait_does_not_steal_when_grant_names_another(self, clean_conch, monkeypatch):
        """FIFO / no thundering-herd: a non-granted waiter cannot jump the head.

        sess-ahead is the head and holds the grant (written when the holder
        released). sess-a (registered later) must NOT acquire even though the
        floor is free — the grant gates it — and must time out + deregister,
        leaving sess-ahead untouched at the front of the line.
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        # sess-ahead joins first, then a real holder grabs + releases the floor,
        # which promotes the head (sess-ahead) as the designated next acquirer.
        ConchQueue.register("sess-ahead", agent="ahead")
        holder = Conch(agent_name="holder")
        assert holder.try_acquire()
        holder.release()  # grant_next() → grants sess-ahead (the head)
        assert ConchQueue.granted_to() == "sess-ahead"

        result = await _converse()(
            message="Hello",
            wait_for_response=False,
            wait_for_conch=0.03,
            session_id="sess-a",
        )

        assert "Timed out" in result
        assert _sessions() == ["sess-ahead"], (
            f"head must keep its place and the non-granted waiter must deregister; got {_sessions()}"
        )

    @pytest.mark.asyncio
    async def test_wait_acquires_exactly_when_granted(self, clean_conch, monkeypatch):
        """The call blocks while busy, then acquires the instant it is granted.

        Real in-process holder + real try_acquire (not mocked). Releasing the
        holder mid-wait promotes sess-a (the only waiter) and the wait loop
        acquires — consuming the grant and deregistering us.
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        holder = Conch(agent_name="holder")
        assert holder.try_acquire()  # floor is genuinely busy

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=(False, {}, {"provider": "test"}),
        ):
            task = asyncio.create_task(_converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=5,
                session_id="sess-a",
            ))
            # Let converse register and enter the wait loop.
            await asyncio.sleep(0.05)
            assert "sess-a" in _sessions(), "the waiter should be registered while blocked"

            holder.release()  # promote sess-a + free the floor
            result = await asyncio.wait_for(task, timeout=5)

        assert "Timed out" not in result
        assert "NOT spoken" not in result
        # Acquiring consumes the grant and deregisters us — no ghost entry.
        assert _sessions() == [], f"acquire must deregister the waiter; got {_sessions()}"
