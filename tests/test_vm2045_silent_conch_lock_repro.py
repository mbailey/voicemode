"""VM-2045 — silent ``hold_conch=true`` is an unbreakable lock: repro (repro-001).

Reported symptom (README.md, "What actually happened", captured live
2026-07-24): Mike told ``gc.adcb`` "wait for me." The GC implemented "wait" as
repeated, silent ``converse(hold_conch=true)`` calls — no speech, just the
lock re-stamped, held for ~11 minutes. During that window:

1. Mike pinged Cora's session; Cora's ``converse`` was refused twice with no
   indication of who held the channel or why.
2. From Mike's seat, his own assistant simply did not answer.

Root cause (confirmed at the code level, see ``voice_mode/tools/converse.py``
and ``voice_mode/conch.py``):

- ``converse()``'s outer ``finally`` calls ``conch.release(hold=hold_conch)``
  **unconditionally** whenever the caller passed ``hold_conch=true``
  (``voice_mode/tools/converse.py``, "Release the conch to signal voice
  conversation has ended") — there is no check that ``tts_success`` was ever
  True, i.e. that anything was actually spoken this turn.
- ``Conch.release(hold=True)`` (``voice_mode/conch.py``) re-stamps
  ``self._acquire_time = datetime.now()`` and rewrites the payload's
  ``expires`` to *now + TTL* every single call — an unconditional refresh.
- ``CONCH_HOLD_EXPIRY`` (default 10s, VM-1649) bounds an *abandoned* hold
  (nobody calls back in time), but a caller who keeps calling
  ``converse(hold_conch=true)`` — even with every TTS attempt failing / with
  nothing spoken — refreshes the TTL forever. "Held the floor" and "used the
  floor" are not distinguished anywhere in the lock state.

This test drives the REAL code paths (``converse()`` end-to-end, the real
``Conch`` flock/hold machinery) — only ``text_to_speech_with_failover`` is
mocked, exactly as ``tests/test_vm1967_conch_deadlock_repro.py`` and
``tests/test_converse_conch_queue.py`` do — to demonstrate the unbounded
silent hold as a live defect, not just an inferred theory. It is EXPECTED to
pass against the current (pre-fix) code; rca-001 / fix-001 are responsible for
making the *un-bounded* half of these assertions false.
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


SILENT_TTS = (False, {}, {"provider": "test"})  # tts_success=False: nothing spoken


class TestSilentHoldConchIsAnUnboundedLock:
    @pytest.mark.asyncio
    async def test_repeated_silent_hold_conch_never_expires_even_though_nothing_was_spoken(
        self, clean_conch, monkeypatch
    ):
        """Mirrors the field incident: agent A "waits" by calling
        ``converse(hold_conch=true)`` repeatedly, every TTS attempt failing
        (nothing audible ever happens), each call spaced just inside the
        hold's idle-expiry window (so a *correctly bounded* hold would have
        long since lapsed). Reproduces: the hold is still live and un-expired
        after total elapsed time far exceeds a single TTL window, proving the
        lock is unbounded as long as the holder keeps calling — silence is no
        obstacle.
        """
        # Small TTL so the test runs fast, but exercised many times over.
        hold_ttl = 0.1

        with patch("voice_mode.conch._get_hold_expiry", return_value=hold_ttl), patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=SILENT_TTS,
        ) as mock_tts:
            for _ in range(8):
                result = await _converse()(
                    message="still waiting",
                    wait_for_response=False,
                    hold_conch=True,
                    session_id="gc-adcb",
                )
                # Every single turn genuinely failed to speak.
                assert "Unexpected error" not in result
                await asyncio.sleep(hold_ttl * 0.5)

        # REPRO: 8 * (hold_ttl * 0.5) = 4x a single TTL window has elapsed,
        # yet the hold is still reported live — held indefinitely by silent
        # re-stamping, never once having produced audible speech.
        assert mock_tts.call_count == 8, "every turn should have attempted (and failed) TTS"
        holder = Conch.get_holder()
        assert holder is not None, (
            "REPRO: a hold_conch=true caller that never once spoke should not "
            "still be holding the floor after 4x its idle-expiry window, but it is"
        )
        assert holder["agent"] != "unknown" or holder.get("session_id") == "gc-adcb"
        assert Conch._held_by_other() is False  # same pid: not "other", but still held
        data = __import__("json").loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True, "REPRO: the file still marks an active hold"

    @pytest.mark.asyncio
    async def test_silent_holder_starves_a_second_agent_who_gets_no_indication_of_why(
        self, clean_conch, monkeypatch
    ):
        """Mirrors Mike's exact experience: while gc.adcb silently holds the
        floor, Cora's converse() is refused. Reproduces both halves of the
        symptom: (1) the refusal is real and happens even though the holder
        has spoken zero words, and (2) a caller who does not opt into
        ``wait_for_conch`` gets back only a synchronous refusal — from the
        user's seat, "the assistant simply did not answer" unless it goes on
        to read the refusal text out loud itself, which nothing forces it to
        do.

        ``gc.adcb`` and Cora's assistant are, in reality, two different agent
        OS processes; ``Conch._held_by_other`` deliberately treats "same pid"
        as "not another holder" (a process reclaiming its own hold), so a
        faithful repro of a genuinely different agent must give the held
        marker a different, live-looking pid — exactly what a real second
        process would produce. That is the only part of the scenario this
        test fakes; the refusal path itself runs for real.
        """
        import json

        import psutil as psutil_module

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=SILENT_TTS,
        ):
            # gc.adcb "waits" — first (only) call, holds the floor via
            # hold_conch=true despite never producing audible speech.
            await _converse()(
                message="wait for me",
                wait_for_response=False,
                hold_conch=True,
                session_id="gc-adcb",
            )

        # Re-stamp the held marker with a different (live-looking) pid, so it
        # reads as a genuinely separate agent process — matching the real
        # incident, not an artifact of both calls sharing this test's pid.
        FAKE_HOLDER_PID = 999999
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        data["pid"] = FAKE_HOLDER_PID
        Conch.LOCK_FILE.write_text(json.dumps(data, indent=2))

        with patch.object(psutil_module, "pid_exists", return_value=True):
            # Cora's assistant tries to speak to Mike right after. It does
            # NOT opt into waiting (default wait_for_conch=False, matching a
            # normal turn), exactly like the real incident.
            refusal = await _converse()(
                message="Hey Mike, following up on the token deadline",
                wait_for_response=False,
                session_id="cora",
            )

        assert "NOT spoken" in refusal, (
            f"REPRO: Cora's converse should be silently refused, "
            f"not delivered: {refusal!r}"
        )
        assert "NOT queued" in refusal
        assert "gc-adcb" not in refusal or "unknown" in refusal, (
            "documents VM-2024's overlapping gap: the refusal names the "
            "holder AGENT string (payload has no agent name here, only a "
            "session_id), not who to actually go find"
        )

        # The refusal happened even though the holder never once spoke —
        # the lock is entirely disconnected from actual voice activity.
        # (still under the fake-pid-liveness patch: outside it the fake pid
        # legitimately reads as dead, which is a test artifact, not part of
        # the defect being reproduced.)
        with patch.object(psutil_module, "pid_exists", return_value=True):
            holder = Conch.get_holder()
        assert holder is not None
        assert holder.get("pid") == FAKE_HOLDER_PID
