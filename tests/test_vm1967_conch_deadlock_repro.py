"""VM-1967 repro-001 — reproduce the conch deadlock (granted session never
claims the floor; waiters queue indefinitely).

Reported symptom (evidence/conch-snapshot-20260715-1724.md, captured live by
super.voicemode):

- ``conch.grant`` named the queue-head session; ``voicemode conch status``
  reported ``Holder: none`` (the status line "lying" — Mike's words).
- The granted session's process was ALIVE, so this was NOT a dead-holder
  case that self-heals via PID-liveness pruning.
- Sessions queued in ``wait`` mode behind the granted-but-unclaimed head
  blocked indefinitely; the grant carried ``expires: null`` (no TTL), so
  nothing self-healed.

Root-cause hypothesis this repro isolates (confirmed here at the code level;
full RCA is rca-001's job): ``converse()``'s WAIT-mode poll loop
(voice_mode/tools/converse.py, "WAIT mode — block until granted") only
deregisters the waiter on its own *normal* timeout exit
(``if not conch._acquired: ConchQueue.deregister(...)``). If the coroutine is
cancelled instead (MCP client disconnect / ESC / tool-call cancellation) while
parked in ``await asyncio.sleep(CONCH_CHECK_INTERVAL)`` inside that loop,
control jumps straight to the function's ``except asyncio.CancelledError``
handler (which deliberately swallows the cancellation — VM-1026) and then the
``finally`` block, which only releases/deregisters ``if conch._acquired`` —
false here, since the floor was never actually claimed. The waiter's queue
entry (and, if a grant already named it, the grant itself) is left behind.
Because ``ConchQueue._is_live`` keys liveness on the OS **pid** — the
long-lived MCP server process, not the specific cancelled coroutine/task — a
"dead" (cancelled) waiter still reads as alive forever, so nothing ever prunes
it: the grant is permanently stuck, every subsequent ``wait``-mode waiter is
gated behind it (``Conch._queue_grant_blocks``), and ``Conch.is_active()`` /
``conch status`` report "free" throughout, because the *holder* lock was
never taken either.

This test drives the REAL code paths (registration, cancellation, grant
promotion, blocked acquire) end-to-end — no mocking of the bug itself — to
demonstrate the deadlock is reproducible on demand, not just an inferred
theory from the field snapshot.
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


class TestConchDeadlockRepro:
    @pytest.mark.asyncio
    async def test_cancelled_wait_leaves_a_permanently_wedged_grant(
        self, clean_conch, monkeypatch
    ):
        """Reproduction steps (mirrors the field snapshot):

        1. A real holder takes the floor (so the first waiter must queue).
        2. sess-a joins in ``conch_mode="wait"`` and blocks in the poll loop.
        3. The MCP client cancels the call mid-wait (ESC / disconnect) — the
           coroutine is cancelled while parked in ``asyncio.sleep`` inside the
           WAIT loop, exactly as a real client cancellation would land.
        4. converse() swallows the cancellation (VM-1026 contract) and
           returns normally, but *never claimed the floor* — assert the
           queue entry survives (the leak: nothing deregistered it).
        5. The real holder releases -> ``grant_next()`` promotes sess-a (the
           head) exactly as it would on a live system. Assert the grant now
           names sess-a.
        6. sess-a's PID is alive (it's this very test process), so the grant
           can NEVER self-clear via PID-liveness pruning, even though the
           coroutine that would have claimed it is long gone.
        7. A brand-new waiter, sess-b, joins in wait mode. Assert it is
           blocked (times out) despite the conch being genuinely unheld —
           reproducing "waiters queue indefinitely" AND the misleading
           status ("Holder: none — free" while structurally deadlocked).
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        holder = Conch(agent_name="holder")
        assert holder.try_acquire()  # floor genuinely busy -> sess-a must queue

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=(False, {}, {"provider": "test"}),
        ):
            task = asyncio.create_task(_converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=30,  # long timeout: cancellation must pre-empt it
                conch_mode="wait",
                session_id="sess-a",
            ))

            # Let converse() register and enter the WAIT poll loop.
            await asyncio.sleep(0.05)
            assert _sessions() == ["sess-a"], "sess-a should be a registered waiter"

            # Step 3: client cancels the in-flight tool call mid-wait.
            task.cancel()
            result = await asyncio.wait_for(task, timeout=5)

        # converse() swallows CancelledError (VM-1026) rather than raising.
        assert result == "Cancelled by user."

        # THE LEAK (step 4): a cancelled WAITer that never claimed the floor
        # is left registered — nothing on the cancellation path deregisters it.
        assert _sessions() == ["sess-a"], (
            "BUG: a cancelled WAIT-mode waiter must be pruned from the queue, "
            f"but it is still registered: {_sessions()}"
        )

        # Step 5: the real holder releases -> promotes the head (sess-a),
        # exactly reproducing "conch.grant names the queue-head session".
        holder.release()
        assert ConchQueue.granted_to() == "sess-a", (
            "grant_next() should promote the (still-registered) sess-a on release"
        )

        # Step 6: the conch is now nominally free -- no holder lock exists --
        # yet the grant stands on an abandoned session. This is the exact
        # "Holder: none — the conch is free" misleading-status signature.
        assert Conch.is_active() is False, "no one actually holds the floor"
        assert Conch.get_holder() is None

        # Step 7: a fresh waiter (sess-b) joins and must queue indefinitely --
        # every acquire attempt is gated by the stuck grant naming sess-a,
        # which can never self-clear because sess-a's PID (this process) is
        # alive. Use a short bounded timeout to prove it blocks for its whole
        # window rather than assert a true infinite hang.
        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=(False, {}, {"provider": "test"}),
        ):
            result_b = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=0.05,
                conch_mode="wait",
                session_id="sess-b",
            )

        assert "Timed out" in result_b, (
            "sess-b must be blocked by the wedged grant despite no live holder"
        )
        # The wedge persists after sess-b gives up: sess-a is still the
        # grantee and nothing has healed the queue -- this is the deadlock
        # that, on a live system, requires manual `conch bump`/`give`/
        # `release` to clear (per the field evidence).
        assert ConchQueue.granted_to() == "sess-a"
        assert "sess-a" in _sessions()

    @pytest.mark.asyncio
    async def test_wedged_grant_has_no_ttl_and_never_self_heals(self, clean_conch):
        """The grant hint carries no expiry, so a missed claim never self-heals.

        Direct queue-layer reproduction of evidence item #4 ("Grant has
        'expires': null -> no TTL"): even a live-but-unresponsive grantee's
        grant is stamped without any expiry field, confirming the queue has
        no self-healing safety net for a missed grant->claim handoff.
        """
        ConchQueue.register("sess-a", agent="converse", mode="wait")
        holder = Conch(agent_name="holder")
        assert holder.try_acquire()
        holder.release()  # grant_next() promotes sess-a

        assert ConchQueue.granted_to() == "sess-a"

        gf = ConchQueue._grant_file()
        import json
        grant_payload = json.loads(gf.read_text())
        assert "expires" not in grant_payload, (
            "conch.grant carries no expiry/TTL field -- a missed claim "
            "cannot self-heal, matching the field evidence"
        )
