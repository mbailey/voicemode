"""VM-2045 — silent ``hold_conch=true`` is an unbreakable lock.

Originally written (repro-001) to REPRODUCE the defect against the
pre-fix code; now (fix-001) verifies it is FIXED. Kept in one file, same
scenarios, so the before/after is traceable in history — only the
assertions at the bottom of each test flipped.

Reported symptom (README.md, "What actually happened", captured live
2026-07-24): Mike told ``gc.adcb`` "wait for me." The GC implemented "wait" as
repeated, silent ``converse(hold_conch=true)`` calls — no speech, just the
lock re-stamped, held for ~11 minutes. During that window:

1. Mike pinged Cora's session; Cora's ``converse`` was refused twice with no
   indication of who held the channel or why.
2. From Mike's seat, his own assistant simply did not answer.

Root cause (rca-001, confirmed at the code level, see
``voice_mode/tools/converse.py`` and ``voice_mode/conch.py``):

- ``converse()``'s outer ``finally`` called ``conch.release(hold=hold_conch)``
  **unconditionally** whenever the caller passed ``hold_conch=true`` — there
  was no check that ``tts_success`` (or any other signal) was ever True, i.e.
  that anything was actually spoken this turn.
- ``Conch.release(hold=True)`` re-stamped ``self._acquire_time = datetime.now()``
  and rewrote the payload's ``expires`` to *now + TTL* every single call — an
  unconditional refresh, regardless of whether the turn spoke.
- ``CONCH_HOLD_EXPIRY`` (default 10s, VM-1649) bounds an *abandoned* hold
  (nobody calls back in time), but a caller who kept calling
  ``converse(hold_conch=true)`` — even with every TTS attempt failing / with
  nothing spoken — refreshed the TTL forever. "Held the floor" and "used the
  floor" were not distinguished anywhere in the lock state.

Fix (fix-001): ``Conch.release`` gained a ``spoke: bool = True`` parameter.
``converse()`` now tracks ``spoke_this_turn`` — whether THIS call actually
produced speech (or otherwise legitimately used the floor: any TTS success,
any survey/turns progress past "not_reached"/"tts_failed") — and passes it
through as ``conch.release(hold=hold_conch, spoke=spoke_this_turn)``. A
hold is now only re-stamped/extended when ``hold and spoke``; a
``hold_conch=true`` call that spoke nothing falls through to a full release
instead, so a silent holder can no longer keep the floor at all, let alone
indefinitely.

This test drives the REAL code paths (``converse()`` end-to-end, the real
``Conch`` flock/hold machinery) — only ``text_to_speech_with_failover`` is
mocked, exactly as ``tests/test_vm1967_conch_deadlock_repro.py`` and
``tests/test_converse_conch_queue.py`` do.
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
SPOKEN_TTS = (True, {"ttfa": 0.01, "generation": 0.01, "playback": 0.01}, {"provider": "test"})


class TestSilentHoldConchIsNoLongerAnUnboundedLock:
    @pytest.mark.asyncio
    async def test_repeated_silent_hold_conch_never_establishes_a_lasting_hold(
        self, clean_conch, monkeypatch
    ):
        """Mirrors the field incident: agent A "waits" by calling
        ``converse(hold_conch=true)`` repeatedly, every TTS attempt failing
        (nothing audible ever happens), each call spaced just inside the
        hold's idle-expiry window. Pre-fix this reproduced an unbounded lock
        (the hold was still live 4x its own TTL window later, having never
        once produced speech). Post-fix: since nothing was ever spoken, each
        call falls through to a FULL release instead of re-stamping the
        hold — there is nothing left to expire because nothing was ever
        reserved past its own single (silent, immediately-released) turn.
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
                # FIXED: a silent hold_conch=true call never establishes a
                # hold in the first place -- the conch is fully released
                # (unlinked) at the end of every one of these calls.
                assert not Conch.LOCK_FILE.exists(), (
                    "FIX REGRESSION: a call that spoke nothing left the "
                    "conch file behind -- it should have been fully released"
                )
                await asyncio.sleep(hold_ttl * 0.5)

        # FIXED: 8 * (hold_ttl * 0.5) = 4x a single TTL window elapsed, and
        # at no point -- including right now -- is the conch held by anyone.
        # The silent caller never once produced audible speech, so it never
        # once retained the floor.
        assert mock_tts.call_count == 8, "every turn should have attempted (and failed) TTS"
        holder = Conch.get_holder()
        assert holder is None, (
            "FIX REGRESSION: a hold_conch=true caller that never once spoke "
            "should not be able to hold the floor at all, but it is"
        )
        assert not Conch.LOCK_FILE.exists(), "FIX REGRESSION: the file should not exist"

    @pytest.mark.asyncio
    async def test_a_genuinely_spoken_hold_still_persists_between_turns(
        self, clean_conch, monkeypatch
    ):
        """Positive control (no overcorrection): a caller that DOES speak
        with ``hold_conch=true`` still gets the normal turn-taking hold
        behaviour, unchanged -- the fix only withholds the re-stamp when
        nothing was spoken, it must not break the legitimate case.
        """
        hold_ttl = 5.0

        with patch("voice_mode.conch._get_hold_expiry", return_value=hold_ttl), patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=SPOKEN_TTS,
        ):
            result = await _converse()(
                message="hang on, one more thing",
                wait_for_response=False,
                hold_conch=True,
                session_id="legit-holder",
            )

        assert "Unexpected error" not in result
        holder = Conch.get_holder()
        assert holder is not None, (
            "a hold_conch=true call that DID speak should still reserve the "
            "floor between turns, exactly as before this fix"
        )
        assert Conch._held_by_other() is False  # same pid: not "other", but still held
        data = __import__("json").loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True

    @pytest.mark.asyncio
    async def test_silent_holder_no_longer_starves_a_second_agent(
        self, clean_conch, monkeypatch
    ):
        """Mirrors Mike's exact experience -- and verifies it can no longer
        happen: while ``gc.adcb`` "waits" via silent ``hold_conch=true``
        calls, Cora's ``converse()`` immediately afterwards is NOT refused,
        because the silent caller never actually reserved the floor. Pre-fix
        this refusal was real (the whole point of repro-001); post-fix the
        silent holder has nothing to block anyone with.
        """
        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=SILENT_TTS,
        ):
            # gc.adcb "waits" -- repeatedly, exactly like the field incident
            # -- but never once produces audible speech.
            for _ in range(3):
                await _converse()(
                    message="wait for me",
                    wait_for_response=False,
                    hold_conch=True,
                    session_id="gc-adcb",
                )

        # FIXED: nothing left behind for Cora to be blocked by.
        assert not Conch.LOCK_FILE.exists()

        # Cora's assistant tries to speak to Mike right after -- and, unlike
        # the field incident, is NOT refused: the channel was never actually
        # held, so this is an ordinary, unblocked converse() call.
        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=SPOKEN_TTS,
        ):
            response = await _converse()(
                message="Hey Mike, following up on the token deadline",
                wait_for_response=False,
                session_id="cora",
            )

        assert "NOT spoken" not in response, (
            f"FIX REGRESSION: Cora's converse should NOT be refused -- the "
            f"silent holder never actually reserved the floor: {response!r}"
        )
        assert "NOT queued" not in response
