"""VM-1967 — the conch grant->claim deadlock: repro (pre-fix) + fix (fix-001).

Reported symptom (evidence/conch-snapshot-20260715-1724.md, captured live by
super.voicemode):

- ``conch.grant`` named the queue-head session; ``voicemode conch status``
  reported ``Holder: none`` (the status line "lying" — Mike's words).
- The granted session's process was ALIVE, so this was NOT a dead-holder
  case that self-heals via PID-liveness pruning.
- Sessions queued in ``wait`` mode behind the granted-but-unclaimed head
  blocked indefinitely; the grant carried ``expires: null`` (no TTL), so
  nothing self-healed.

Root cause (confirmed at the code level; full RCA is rca-001's, see
``evidence/rca-001-2026-07-15.md``): ``converse()``'s WAIT-mode poll loop
(voice_mode/tools/converse.py, "WAIT mode — block until granted") only
deregistered the waiter on its own *normal* timeout exit
(``if not conch._acquired: ConchQueue.deregister(...)``). If the coroutine was
instead cancelled (MCP client disconnect / ESC / tool-call cancellation) while
parked in ``await asyncio.sleep(CONCH_CHECK_INTERVAL)`` inside that loop,
control jumped straight to the function's ``except asyncio.CancelledError``
handler (which deliberately swallows the cancellation — VM-1026) and then the
``finally`` block, which only released/deregistered ``if conch._acquired`` —
false there, since the floor was never actually claimed. The waiter's queue
entry (and, once granted, the grant itself) was left behind. Because
``ConchQueue._is_live`` keys liveness on the OS **pid** — the long-lived MCP
server process, not the specific cancelled coroutine/task — a "dead"
(cancelled) waiter still read as alive forever, so nothing ever pruned it: the
grant was permanently stuck, every subsequent ``wait``-mode waiter was gated
behind it (``Conch._queue_grant_blocks``), and ``Conch.is_active()`` /
``conch status`` reported "free" throughout, because the *holder* lock was
never taken either.

**fix-001** closes this two ways (``evidence/rca-001-2026-07-15.md``, "What
fix-001 needs to address"):

1. **Deregister on every exit path** — ``converse()``'s outer ``finally``
   (which already runs unconditionally) now also deregisters this call's own
   WAIT-mode queue entry whenever the floor was never actually claimed,
   closing the cancellation gap directly (this file's
   ``TestConchDeadlockFixedByDeregisterOnCancel``).
2. **Grant claim TTL safety net** (``ConchQueue._grant_wedged`` /
   ``_current_grant``, ``tests/test_conch_queue.py::TestGrantTTLSafetyNet``)
   — defense in depth: even if some *other* cleanup path is missed in the
   future, a WAIT-mode grant nobody claims within ``CONCH_GRANT_TTL`` now
   self-heals instead of wedging forever.

This test drives the REAL code paths (registration, cancellation, grant
promotion, blocked acquire) end-to-end — no mocking of the fix itself — to
demonstrate the deadlock no longer reproduces, not just an inferred theory.
"""

import asyncio

import pytest
from unittest.mock import patch

from voice_mode.conch import Conch
from voice_mode.conch_ops import status_payload
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


class TestConchDeadlockFixedByDeregisterOnCancel:
    @pytest.mark.asyncio
    async def test_cancelled_wait_is_cleaned_up_and_never_wedges_the_queue(
        self, clean_conch, monkeypatch
    ):
        """Reproduction steps (mirrors the field snapshot), now asserting the
        FIXED (post fix-001) behaviour at every step:

        1. A real holder takes the floor (so the first waiter must queue).
        2. sess-a joins in ``conch_mode="wait"`` and blocks in the poll loop.
        3. The MCP client cancels the call mid-wait (ESC / disconnect) — the
           coroutine is cancelled while parked in ``asyncio.sleep`` inside the
           WAIT loop, exactly as a real client cancellation would land.
        4. converse() swallows the cancellation (VM-1026 contract) and
           returns normally. FIXED: the outer ``finally`` now deregisters
           sess-a's queue entry on this path too — the queue is empty again.
        5. The real holder releases. FIXED: with no live waiters left,
           nothing is (falsely) promoted — the grant stays clear.
        6. The conch is genuinely free: no holder, no outstanding grant.
           ``status_payload()["free"]`` — the VM-1967 status-line fix —
           confirms this unambiguously (not just "no holder lock").
        7. A brand-new waiter, sess-b, joins in wait mode and acquires the
           floor immediately — no ghost grant blocks it.
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

        # FIXED (step 4): a cancelled WAIT-mode waiter that never claimed the
        # floor is deregistered on every exit path now, including
        # cancellation -- no orphaned entry survives.
        assert _sessions() == [], (
            "REGRESSION: a cancelled WAIT-mode waiter must be pruned from "
            f"the queue by the outer finally, but it is still registered: {_sessions()}"
        )

        # Step 5: the real holder releases. There is no live waiter left to
        # promote (the orphan is gone), so grant_next() finds nothing.
        holder.release()
        assert ConchQueue.granted_to() is None, (
            "REGRESSION: nothing should be promoted -- the only registrant "
            "was cleaned up on cancellation"
        )

        # Step 6: the conch is genuinely free -- no holder, no outstanding
        # grant. This is the exact scenario the field report's misleading
        # "Holder: none — the conch is free" was ambiguous about; the new
        # `free` field makes it unambiguous.
        assert Conch.is_active() is False
        assert Conch.get_holder() is None
        assert status_payload()["free"] is True

        # Step 7: a fresh waiter (sess-b) joins and acquires immediately --
        # no ghost grant from sess-a gates it (that was the deadlock).
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

        assert "Timed out" not in result_b, (
            f"REGRESSION: sess-b should acquire immediately on a genuinely "
            f"free conch, not time out: {result_b!r}"
        )

    @pytest.mark.asyncio
    async def test_repeated_cancel_from_same_session_never_accumulates_orphans(
        self, clean_conch, monkeypatch
    ):
        """RCA follow-up (rca-001, 'Orphan re-registration risk'): the same
        long-lived pid/session issuing repeated cancelled WAIT calls must
        never accumulate wedged state -- each cancellation cleans up after
        itself, so the queue is empty after every single one, not just the
        first.
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        holder = Conch(agent_name="holder")
        assert holder.try_acquire()

        for _ in range(3):
            with patch(
                "voice_mode.tools.converse.text_to_speech_with_failover",
                return_value=(False, {}, {"provider": "test"}),
            ):
                task = asyncio.create_task(_converse()(
                    message="Hello",
                    wait_for_response=False,
                    wait_for_conch=30,
                    conch_mode="wait",
                    session_id="repeat-offender",
                ))
                await asyncio.sleep(0.03)
                task.cancel()
                await asyncio.wait_for(task, timeout=5)

            assert _sessions() == [], (
                "REGRESSION: a repeated cancel from the same session left an "
                f"orphaned entry behind: {_sessions()}"
            )

        holder.release()
        assert ConchQueue.granted_to() is None


class TestConchDeadlockSafetyNetStatusFix:
    def test_wedged_grant_now_carries_a_ttl_and_self_heals(self, clean_conch, monkeypatch):
        """Direct queue-layer check of evidence item #4 ("Grant has
        'expires': null -> no TTL"): fix-001 stamps a ``granted_at`` on every
        grant and self-heals a WAIT-mode grant nobody claims within
        ``CONCH_GRANT_TTL`` (see ``tests/test_conch_queue.py::
        TestGrantTTLSafetyNet`` for the full matrix; this is the end-to-end
        confirmation against VM-1967's exact field shape).
        """
        from datetime import datetime, timedelta

        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 5.0)

        ConchQueue.register("sess-a", agent="converse", mode="wait")
        holder = Conch(agent_name="holder")
        assert holder.try_acquire()
        holder.release()  # grant_next() promotes sess-a

        assert ConchQueue.granted_to() == "sess-a"
        gf = ConchQueue._grant_file()
        import json
        grant_payload = json.loads(gf.read_text())
        assert grant_payload.get("granted_at") is not None, (
            "the grant must carry a granted_at timestamp for the TTL "
            "safety net to judge its age"
        )

        # Backdate the grant past the TTL, as if sess-a simply never claimed
        # it (its process could be alive the whole time -- pid-liveness
        # alone, per the field evidence, can never prove this dead).
        grant_payload["granted_at"] = (
            datetime.now() - timedelta(seconds=6)
        ).isoformat()
        ConchQueue._atomic_write_json(gf, grant_payload)

        # A single read (any other waiter's poll, or a status check)
        # self-heals: no waiters remain, so the grant clears to genuinely
        # free -- no manual `conch bump`/`give`/`release` required.
        assert ConchQueue.granted_to() is None
        assert status_payload()["free"] is True

    def test_status_line_no_longer_lies_about_an_unclaimed_grant(self, clean_conch):
        """Mike's exact field complaint: 'the status line seems to be
        lying' -- `Holder: none` while a grant is outstanding must no
        longer be reported as `free`.
        """
        ConchQueue.register("stuck-head", agent="stuck-agent", mode="wait")
        ConchQueue.grant_next()  # promotes stuck-head, never claimed

        assert Conch.get_holder() is None  # the holder LOCK genuinely is free

        snap = status_payload()
        assert snap["holder"] is None
        assert snap["free"] is False, (
            "REGRESSION: a grant is outstanding and unclaimed -- reporting "
            "free is the exact bug Mike reported"
        )
        granted_entry = next(q for q in snap["queue"] if q["granted"])
        assert granted_entry["session_id"] == "stuck-head"
