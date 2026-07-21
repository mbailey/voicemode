"""Tests for VM-2015's cancellable-recording stop flag.

`record_audio_with_silence_detection` runs on the default ThreadPoolExecutor
via `run_in_executor` (converse.py's `listen_and_transcribe`). Cancelling the
*awaiting coroutine* (e.g. ESC during converse) abandons the *future* but not
the *thread* -- `sd.rec`/the VAD loop would otherwise keep running for the
full `max_duration`, which is what stalled server teardown behind an
uncancellable executor-thread join (see the VM-2015 RCA). The VAD loop is
already chunked on `audio_queue.get(timeout=0.1)`, so a `threading.Event`
checked once per chunk lets a cancelled caller stop the thread in ~100ms
instead of up to `max_duration` seconds.
"""

import queue
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Mock webrtcvad before importing voice_mode modules (same pattern as the
# other VAD test modules in this suite).
sys.modules.setdefault('webrtcvad', MagicMock())

from voice_mode.tools.converse import record_audio_with_silence_detection
from voice_mode.config import SAMPLE_RATE, VAD_CHUNK_DURATION_MS


def _chunk():
    return np.random.randint(
        -1000, 1000,
        size=int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000),
        dtype=np.int16,
    ).reshape(-1, 1)


class _ForeverQueue:
    """Fake queue.Queue that always has a chunk ready -- never raises
    queue.Empty, so the AUDIO_STALL_TIMEOUT backstop never fires and the
    only thing that can end the loop (besides max_duration) is the
    stop_event under test."""

    def get(self, timeout=None):
        return _chunk()


class TestStopEventUpfront:
    """stop_event already set before the call -- the very first loop
    condition check must break out before doing any recording work."""

    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_returns_immediately_when_already_cancelled(self):
        with patch('voice_mode.tools.converse.webrtcvad') as mock_webrtcvad, \
             patch('voice_mode.tools.converse.sd') as mock_sd, \
             patch('queue.Queue', return_value=_ForeverQueue()):
            mock_webrtcvad.Vad.return_value.is_speech.return_value = True
            mock_sd.InputStream.return_value.__enter__.return_value = MagicMock()

            stop_event = threading.Event()
            stop_event.set()

            start = time.monotonic()
            audio, speech_detected = record_audio_with_silence_detection(
                max_duration=30.0, stop_event=stop_event,
            )
            elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"took {elapsed:.2f}s to return with stop_event already set -- "
            "expected an immediate break, not a run to max_duration"
        )
        # No chunks were ever recorded.
        assert len(audio) == 0

    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_stop_event_none_is_a_no_op(self):
        """Default (stop_event=None) must not affect existing behaviour --
        the loop still exits via a normal path (here: a single chunk,
        then queue.Empty)."""
        class _OneChunkThenEmpty:
            def __init__(self):
                self._served = False

            def get(self, timeout=None):
                if not self._served:
                    self._served = True
                    return _chunk()
                raise queue.Empty()

        with patch('voice_mode.tools.converse.webrtcvad') as mock_webrtcvad, \
             patch('voice_mode.tools.converse.sd') as mock_sd, \
             patch('queue.Queue', return_value=_OneChunkThenEmpty()):
            mock_webrtcvad.Vad.return_value.is_speech.return_value = True
            mock_sd.InputStream.return_value.__enter__.return_value = MagicMock()

            audio, speech_detected = record_audio_with_silence_detection(
                max_duration=30.0, stop_event=None,
            )

        # One chunk's worth of audio was captured before the AUDIO_STALL_TIMEOUT
        # backstop or max_duration eventually ends the (unfed) loop -- the
        # important thing is it didn't raise for lack of a stop_event.
        assert len(audio) >= int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)
        assert speech_detected is True


class TestCancelledRecordingIsDiscarded:
    """VM-2015 fix-001 review focus B: the stop flag makes the recording
    thread return EARLY, i.e. with a PARTIAL buffer. That partial audio must
    never reach STT -- trading a wedged connection for a phantom
    half-sentence transcript is not a fix.

    The guarantee comes from `listen_and_transcribe` re-raising out of the
    `await`: the executor future's (partial) result is never bound, so every
    line below it -- RECORDING_END, chimes, speech_to_text -- is skipped.
    These tests pin that contract at the seam so a later refactor that
    "helpfully" returns the partial buffer instead of propagating gets caught.
    """

    @pytest.mark.asyncio
    async def test_partial_audio_never_reaches_stt_on_cancel(self):
        import asyncio

        from voice_mode.control_channel import get_control_state
        from voice_mode.tools.converse import listen_and_transcribe

        recorder_entered = threading.Event()
        saw_stop_event = threading.Event()

        def _record(max_duration, disable_silence_detection, min_duration,
                    vad_aggressiveness, stop_event=None):
            recorder_entered.set()
            # Block like the real VAD loop, until the caller's cancellation
            # sets the flag -- then hand back a PARTIAL buffer, exactly what
            # the real recorder does when it breaks early.
            assert stop_event is not None, "listen_and_transcribe must pass a stop_event"
            stop_event.wait(timeout=5.0)
            if stop_event.is_set():
                saw_stop_event.set()
            return (np.zeros(2400, dtype=np.int16), True)

        async def _noop_feedback(*_a, **_k):
            return None

        stt_spy = MagicMock(side_effect=AssertionError(
            "STT must never run on a cancelled recording (partial audio)"
        ))

        get_control_state().reset()
        try:
            with patch('voice_mode.tools.converse.play_audio_feedback', new=_noop_feedback), \
                 patch('voice_mode.tools.converse.record_audio_with_silence_detection', new=_record), \
                 patch('voice_mode.tools.converse.speech_to_text', new=stt_spy):
                task = asyncio.ensure_future(listen_and_transcribe(
                    control_state=get_control_state(),
                    listen_duration_max=30.0,
                    listen_duration_min=0.5,
                    disable_silence_detection=False,
                    vad_aggressiveness=None,
                    chime_enabled=False,
                    chime_leading_silence=None,
                    chime_trailing_silence=None,
                    transport="local",
                    event_logger=None,
                ))

                # Wait until the recording thread is actually running, then
                # cancel the awaiting coroutine (the ESC).
                for _ in range(50):
                    if recorder_entered.is_set():
                        break
                    await asyncio.sleep(0.05)
                assert recorder_entered.is_set(), "recorder never started"

                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

                # The cancellation reached the thread (fast return, no
                # orphan stalling teardown) ...
                assert saw_stop_event.wait(timeout=5.0), (
                    "stop_event was not set on cancellation -- the recording "
                    "thread would run on to max_duration (the VM-2015 wedge)"
                )
                # ... and its partial buffer went nowhere near STT.
                stt_spy.assert_not_called()
        finally:
            get_control_state().reset()


class TestStopEventMidRecording:
    """A stop_event set from another thread mid-recording (as the real
    listen_and_transcribe caller does from its `except CancelledError`) must
    end the loop promptly -- well before max_duration -- not on the next
    silence/stall timeout."""

    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_thread_stops_promptly_on_external_cancel(self):
        with patch('voice_mode.tools.converse.webrtcvad') as mock_webrtcvad, \
             patch('voice_mode.tools.converse.sd') as mock_sd, \
             patch('queue.Queue', return_value=_ForeverQueue()):
            # Always "speech" -- silence_duration_ms never accumulates, so
            # the VAD's own early-stop can't be what ends this loop; only
            # stop_event or max_duration can.
            mock_webrtcvad.Vad.return_value.is_speech.return_value = True
            mock_sd.InputStream.return_value.__enter__.return_value = MagicMock()

            stop_event = threading.Event()
            result = {}

            def _run():
                start = time.monotonic()
                audio, speech_detected = record_audio_with_silence_detection(
                    max_duration=30.0, stop_event=stop_event,
                )
                result["elapsed"] = time.monotonic() - start
                result["audio"] = audio

            thread = threading.Thread(target=_run)
            thread.start()
            time.sleep(0.25)
            stop_event.set()
            thread.join(timeout=5.0)

        assert not thread.is_alive(), "recording thread did not stop after stop_event.set()"
        assert result["elapsed"] < 2.0, (
            f"recording thread took {result['elapsed']:.2f}s to stop after "
            "cancellation -- expected ~100ms (one chunk-poll interval), not "
            "a run to max_duration=30s"
        )
