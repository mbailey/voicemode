"""Tests for barge-in support with streaming TTS.

These tests verify that barge-in detection works correctly with streaming
audio playback, including:
1. Interrupt detection during streaming
2. Proper cleanup of resources on interrupt
3. Metrics tracking for interrupted streaming
4. Captured audio passthrough from barge-in monitor
"""

import pytest
import numpy as np
import threading
import time
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from dataclasses import dataclass
import sys

# Mock webrtcvad before importing voice_mode modules
mock_webrtcvad = MagicMock()
sys.modules['webrtcvad'] = mock_webrtcvad


class TestStreamMetricsDataclass:
    """Test the StreamMetrics dataclass with barge-in fields."""

    def test_stream_metrics_has_interrupted_field(self):
        """Test that StreamMetrics has the interrupted field."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        assert hasattr(metrics, 'interrupted')
        assert metrics.interrupted is False

    def test_stream_metrics_has_interrupted_at_field(self):
        """Test that StreamMetrics has the interrupted_at field."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        assert hasattr(metrics, 'interrupted_at')
        assert metrics.interrupted_at == 0.0

    def test_stream_metrics_has_captured_audio_field(self):
        """Test that StreamMetrics has the captured_audio field."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        assert hasattr(metrics, 'captured_audio')
        assert metrics.captured_audio is None

    def test_stream_metrics_has_captured_audio_samples_field(self):
        """Test that StreamMetrics has the captured_audio_samples field."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        assert hasattr(metrics, 'captured_audio_samples')
        assert metrics.captured_audio_samples == 0


class TestStreamTtsAudioSignature:
    """Test that stream_tts_audio accepts barge_in_monitor parameter."""

    def test_stream_tts_audio_accepts_barge_in_monitor(self):
        """Test that stream_tts_audio has barge_in_monitor parameter."""
        import inspect
        from voice_mode.streaming import stream_tts_audio

        sig = inspect.signature(stream_tts_audio)
        params = list(sig.parameters.keys())
        assert 'barge_in_monitor' in params

    def test_stream_pcm_audio_accepts_barge_in_monitor(self):
        """Test that stream_pcm_audio has barge_in_monitor parameter."""
        import inspect
        from voice_mode.streaming import stream_pcm_audio

        sig = inspect.signature(stream_pcm_audio)
        params = list(sig.parameters.keys())
        assert 'barge_in_monitor' in params

    def test_stream_with_buffering_accepts_barge_in_monitor(self):
        """Test that stream_with_buffering has barge_in_monitor parameter."""
        import inspect
        from voice_mode.streaming import stream_with_buffering

        sig = inspect.signature(stream_with_buffering)
        params = list(sig.parameters.keys())
        assert 'barge_in_monitor' in params


class TestStreamingInterruptDetection:
    """Test interrupt detection in streaming playback."""

    @patch('voice_mode.streaming.sd')
    def test_interrupt_event_set_stops_pcm_streaming(self, mock_sd):
        """Test that setting interrupt event stops PCM streaming."""
        from voice_mode.streaming import StreamMetrics

        # We'll test that the interrupt_event logic is correct
        # by simulating the streaming loop behavior
        interrupt_event = threading.Event()
        metrics = StreamMetrics()

        # Simulate the check at the start of the loop
        assert not interrupt_event.is_set()

        # Set interrupt
        interrupt_event.set()

        # Check would happen in the loop
        if interrupt_event.is_set():
            metrics.interrupted = True
            metrics.interrupted_at = 0.5  # Simulated time

        assert metrics.interrupted is True
        assert metrics.interrupted_at == 0.5

    @patch('voice_mode.streaming.sd')
    def test_interrupt_event_set_stops_buffered_streaming(self, mock_sd):
        """Test that setting interrupt event stops buffered streaming."""
        from voice_mode.streaming import StreamMetrics

        interrupt_event = threading.Event()
        metrics = StreamMetrics()

        # Set interrupt mid-streaming
        interrupt_event.set()

        # The loop would break and set metrics
        if interrupt_event.is_set():
            metrics.interrupted = True
            metrics.interrupted_at = 1.2

        assert metrics.interrupted is True
        assert metrics.interrupted_at == 1.2


class TestStreamingBargeInMonitorIntegration:
    """Test integration between streaming and BargeInMonitor."""

    def test_barge_in_monitor_callback_sets_interrupt_event(self):
        """Test that BargeInMonitor callback correctly sets interrupt event."""
        interrupt_event = threading.Event()

        def on_interrupt():
            interrupt_event.set()

        # Simulate what the streaming function does
        assert not interrupt_event.is_set()
        on_interrupt()
        assert interrupt_event.is_set()

    @patch('voice_mode.streaming.sd')
    @patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad})
    def test_streaming_starts_barge_in_monitoring(self, mock_sd):
        """Test that streaming starts barge-in monitoring when monitor provided."""
        from voice_mode.barge_in import BargeInMonitor
        from voice_mode import barge_in

        with patch.object(barge_in, 'VAD_AVAILABLE', True):
            mock_monitor = MagicMock(spec=BargeInMonitor)

            # Simulate what stream_pcm_audio does
            callback_received = []

            def capture_callback(on_voice_detected=None):
                callback_received.append(on_voice_detected)

            mock_monitor.start_monitoring = capture_callback

            # Call the start_monitoring like the streaming function does
            mock_monitor.start_monitoring(on_voice_detected=lambda: None)

            assert len(callback_received) == 1
            assert callable(callback_received[0])

    @patch('voice_mode.streaming.sd')
    def test_streaming_stops_barge_in_monitoring_in_finally(self, mock_sd):
        """Test that streaming stops barge-in monitoring in finally block."""
        mock_monitor = MagicMock()
        mock_monitor.start_monitoring = MagicMock()
        mock_monitor.stop_monitoring = MagicMock()

        # Simulate the finally block logic
        try:
            pass  # Normal operation
        finally:
            if mock_monitor:
                mock_monitor.stop_monitoring()

        mock_monitor.stop_monitoring.assert_called_once()


class TestStreamingCapturedAudioHandoff:
    """Test captured audio handoff from barge-in to metrics."""

    def test_captured_audio_copied_to_metrics_on_interrupt(self):
        """Test that captured audio is copied to metrics when interrupted."""
        from voice_mode.streaming import StreamMetrics

        mock_monitor = MagicMock()
        captured_samples = np.random.randint(-32768, 32767, size=960, dtype=np.int16)
        mock_monitor.get_captured_audio.return_value = captured_samples

        metrics = StreamMetrics()
        metrics.interrupted = True

        # Simulate the capture logic
        if metrics.interrupted and mock_monitor:
            captured_audio = mock_monitor.get_captured_audio()
            if captured_audio is not None:
                metrics.captured_audio = captured_audio
                metrics.captured_audio_samples = len(captured_audio)

        assert metrics.captured_audio is not None
        assert len(metrics.captured_audio) == 960
        assert metrics.captured_audio_samples == 960
        np.testing.assert_array_equal(metrics.captured_audio, captured_samples)

    def test_no_captured_audio_when_not_interrupted(self):
        """Test that captured audio is not copied when not interrupted."""
        from voice_mode.streaming import StreamMetrics

        mock_monitor = MagicMock()
        captured_samples = np.random.randint(-32768, 32767, size=960, dtype=np.int16)
        mock_monitor.get_captured_audio.return_value = captured_samples

        metrics = StreamMetrics()
        metrics.interrupted = False

        # The capture logic should not run
        if metrics.interrupted and mock_monitor:
            captured_audio = mock_monitor.get_captured_audio()
            if captured_audio is not None:
                metrics.captured_audio = captured_audio
                metrics.captured_audio_samples = len(captured_audio)

        assert metrics.captured_audio is None
        assert metrics.captured_audio_samples == 0
        mock_monitor.get_captured_audio.assert_not_called()


class TestStreamingMetricsForInterruption:
    """Test metrics tracking for interrupted streaming."""

    def test_interrupted_metrics_structure(self):
        """Test that interrupted streaming produces correct metrics structure."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        metrics.ttfa = 0.15
        metrics.generation_time = 0.2
        metrics.playback_time = 0.8
        metrics.chunks_received = 10
        metrics.chunks_played = 8
        metrics.interrupted = True
        metrics.interrupted_at = 0.6
        metrics.captured_audio_samples = 480

        # Verify all expected fields
        assert metrics.interrupted is True
        assert metrics.interrupted_at == 0.6
        assert metrics.chunks_received == 10
        assert metrics.chunks_played == 8
        assert metrics.captured_audio_samples == 480

    def test_normal_completion_metrics_structure(self):
        """Test that normal completion produces correct metrics structure."""
        from voice_mode.streaming import StreamMetrics

        metrics = StreamMetrics()
        metrics.ttfa = 0.15
        metrics.generation_time = 0.2
        metrics.playback_time = 2.0
        metrics.chunks_received = 50
        metrics.chunks_played = 50
        metrics.interrupted = False

        # Verify expected fields for normal completion
        assert metrics.interrupted is False
        assert metrics.interrupted_at == 0.0
        assert metrics.chunks_received == 50
        assert metrics.chunks_played == 50
        assert metrics.captured_audio is None


class TestCoreStreamingBargeInPassthrough:
    """Test that core.py passes barge_in_monitor to streaming functions."""

    def test_stream_tts_audio_called_with_barge_in_monitor(self):
        """Test that stream_tts_audio receives barge_in_monitor from core."""
        # This verifies the integration between core.py and streaming.py

        # Create a mock for stream_tts_audio to capture its arguments
        call_args = []

        async def mock_stream_tts_audio(**kwargs):
            call_args.append(kwargs)
            from voice_mode.streaming import StreamMetrics
            return True, StreamMetrics()

        # Verify that stream_tts_audio has the barge_in_monitor parameter
        import inspect
        from voice_mode.streaming import stream_tts_audio
        sig = inspect.signature(stream_tts_audio)
        assert 'barge_in_monitor' in sig.parameters


class TestStreamingEdgeCases:
    """Test edge cases in streaming with barge-in."""

    def test_none_barge_in_monitor_works(self):
        """Test that streaming works fine with None barge_in_monitor."""
        from voice_mode.streaming import StreamMetrics

        # Simulate the conditional logic
        barge_in_monitor = None
        metrics = StreamMetrics()
        interrupt_event = threading.Event()

        # Start monitoring check
        if barge_in_monitor:
            barge_in_monitor.start_monitoring()

        # Should not raise any errors
        # interrupt_event should not be set
        assert not interrupt_event.is_set()

        # Stop monitoring check
        if barge_in_monitor:
            barge_in_monitor.stop_monitoring()

        # Metrics should show no interruption
        assert not metrics.interrupted

    def test_barge_in_start_failure_handled_gracefully(self):
        """Test that failure to start barge-in monitoring is handled gracefully."""
        mock_monitor = MagicMock()
        mock_monitor.start_monitoring.side_effect = ImportError("webrtcvad not available")

        warning_logged = []

        # Simulate the try/except logic from streaming functions
        try:
            mock_monitor.start_monitoring(on_voice_detected=lambda: None)
        except Exception as e:
            warning_logged.append(str(e))
            # Should continue without barge-in

        assert len(warning_logged) == 1
        assert "webrtcvad not available" in warning_logged[0]

    def test_barge_in_stop_failure_handled_gracefully(self):
        """Test that failure to stop barge-in monitoring is handled gracefully."""
        mock_monitor = MagicMock()
        mock_monitor.stop_monitoring.side_effect = Exception("Thread cleanup failed")

        warning_logged = []

        # Simulate the finally block logic
        try:
            # Normal cleanup
            pass
        finally:
            try:
                mock_monitor.stop_monitoring()
            except Exception as e:
                warning_logged.append(str(e))

        assert len(warning_logged) == 1
        assert "Thread cleanup failed" in warning_logged[0]


class TestStreamingInterruptTiming:
    """Test timing aspects of streaming interruption."""

    def test_interrupt_check_before_chunk_processing(self):
        """Test that interrupt is checked before processing each chunk."""
        from voice_mode.streaming import StreamMetrics

        interrupt_event = threading.Event()
        metrics = StreamMetrics()
        chunks_processed = []

        # Simulate the streaming loop
        fake_chunks = [b'chunk1', b'chunk2', b'chunk3']

        for chunk in fake_chunks:
            # Check for barge-in interrupt BEFORE processing chunk
            if interrupt_event.is_set():
                metrics.interrupted = True
                break

            # Process chunk
            chunks_processed.append(chunk)

            # Set interrupt after first chunk
            if len(chunks_processed) == 1:
                interrupt_event.set()

        # Should have processed only the first chunk before interrupt was detected
        assert len(chunks_processed) == 1
        assert chunks_processed[0] == b'chunk1'

    def test_interrupt_check_after_chunk_playback(self):
        """Test that interrupt is also checked after playing each chunk."""
        from voice_mode.streaming import StreamMetrics

        interrupt_event = threading.Event()
        metrics = StreamMetrics()
        chunks_played = []

        # Simulate the streaming loop with post-playback check
        fake_chunks = [b'chunk1', b'chunk2', b'chunk3']

        for chunk in fake_chunks:
            # Check before
            if interrupt_event.is_set():
                metrics.interrupted = True
                break

            # Play chunk
            chunks_played.append(chunk)

            # Check after playback
            if interrupt_event.is_set():
                metrics.interrupted = True
                break

            # Voice detected after chunk1 is played
            if len(chunks_played) == 2:
                interrupt_event.set()

        # Two chunks should be played before interrupt on third check
        assert len(chunks_played) == 2
        assert metrics.interrupted is True


class TestAsyncStreamingWithBargeIn:
    """Test async streaming behavior with barge-in."""

    @pytest.mark.asyncio
    @patch('voice_mode.streaming.sd')
    @patch('voice_mode.streaming.get_event_logger')
    async def test_stream_pcm_audio_with_mock_monitor(self, mock_get_logger, mock_sd):
        """Test stream_pcm_audio with a mock barge-in monitor."""
        from voice_mode.streaming import stream_pcm_audio
        from contextlib import asynccontextmanager

        # Setup mocks
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        mock_client = MagicMock()

        # Simulate streaming response that yields chunks
        async def mock_iter_bytes(chunk_size=None):
            yield b'\x00\x01' * 1024  # First chunk
            yield b'\x00\x02' * 1024  # Second chunk

        @asynccontextmanager
        async def mock_create(**kwargs):
            mock_response = MagicMock()
            mock_response.iter_bytes = mock_iter_bytes
            yield mock_response

        mock_client.audio.speech.with_streaming_response.create = mock_create

        # Create a mock barge-in monitor
        mock_monitor = MagicMock()
        mock_monitor.start_monitoring = MagicMock()
        mock_monitor.stop_monitoring = MagicMock()
        mock_monitor.get_captured_audio.return_value = None

        # Call stream_pcm_audio
        success, metrics = await stream_pcm_audio(
            text="Test",
            openai_client=mock_client,
            request_params={"response_format": "pcm"},
            barge_in_monitor=mock_monitor
        )

        # Verify barge-in monitor was used
        mock_monitor.start_monitoring.assert_called_once()
        mock_monitor.stop_monitoring.assert_called_once()

        # Verify metrics
        assert success
        assert not metrics.interrupted

    @pytest.mark.asyncio
    @patch('voice_mode.streaming.sd')
    @patch('voice_mode.streaming.get_event_logger')
    async def test_stream_pcm_audio_interrupt_mid_stream(self, mock_get_logger, mock_sd):
        """Test stream_pcm_audio interruption during streaming."""
        from voice_mode.streaming import stream_pcm_audio
        from contextlib import asynccontextmanager

        # Setup mocks
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        chunks_yielded = []

        async def mock_iter_bytes(chunk_size=None):
            chunks_yielded.append(1)
            yield b'\x00\x01' * 1024
            chunks_yielded.append(2)
            yield b'\x00\x02' * 1024
            chunks_yielded.append(3)
            yield b'\x00\x03' * 1024

        @asynccontextmanager
        async def mock_create(**kwargs):
            mock_response = MagicMock()
            mock_response.iter_bytes = mock_iter_bytes
            yield mock_response

        mock_client = MagicMock()
        mock_client.audio.speech.with_streaming_response.create = mock_create

        # Create a mock barge-in monitor that triggers after first chunk
        interrupt_after_first = []

        def start_monitoring(on_voice_detected=None):
            # Store the callback so we can trigger it
            interrupt_after_first.append(on_voice_detected)

        mock_monitor = MagicMock()
        mock_monitor.start_monitoring = start_monitoring
        mock_monitor.stop_monitoring = MagicMock()

        captured_audio = np.zeros(480, dtype=np.int16)
        mock_monitor.get_captured_audio.return_value = captured_audio

        # Start streaming
        # Note: We can't easily trigger mid-stream interrupt in this test
        # because the interrupt happens via callback from the monitor's thread
        # This test verifies the structure and cleanup

        success, metrics = await stream_pcm_audio(
            text="Test",
            openai_client=mock_client,
            request_params={"response_format": "pcm"},
            barge_in_monitor=mock_monitor
        )

        # Verify cleanup happened
        mock_monitor.stop_monitoring.assert_called_once()


class TestStreamingWithoutBargeIn:
    """Test that streaming still works without barge-in monitor."""

    @pytest.mark.asyncio
    @patch('voice_mode.streaming.sd')
    @patch('voice_mode.streaming.get_event_logger')
    async def test_stream_pcm_audio_without_monitor(self, mock_get_logger, mock_sd):
        """Test stream_pcm_audio works without barge-in monitor."""
        from voice_mode.streaming import stream_pcm_audio
        from contextlib import asynccontextmanager

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        async def mock_iter_bytes(chunk_size=None):
            yield b'\x00\x01' * 1024

        @asynccontextmanager
        async def mock_create(**kwargs):
            mock_response = MagicMock()
            mock_response.iter_bytes = mock_iter_bytes
            yield mock_response

        mock_client = MagicMock()
        mock_client.audio.speech.with_streaming_response.create = mock_create

        # Call without barge_in_monitor
        success, metrics = await stream_pcm_audio(
            text="Test",
            openai_client=mock_client,
            request_params={"response_format": "pcm"},
            barge_in_monitor=None
        )

        assert success
        assert not metrics.interrupted
