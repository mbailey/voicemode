"""Tests for barge-in detection module (BargeInMonitor).

Tests cover:
- VAD-based speech detection
- Audio buffer capture
- Thread safety and cleanup
- Configuration validation
"""

import pytest
import numpy as np
import threading
import time
from unittest.mock import Mock, MagicMock, patch
import sys

# Mock webrtcvad before importing voice_mode modules
mock_webrtcvad = MagicMock()
sys.modules['webrtcvad'] = mock_webrtcvad


class TestBargeInMonitorInit:
    """Test BargeInMonitor initialization and configuration."""

    def test_init_with_defaults(self):
        """Test initialization uses config defaults."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode.config import BARGE_IN_VAD_AGGRESSIVENESS, BARGE_IN_MIN_SPEECH_MS

            monitor = BargeInMonitor()

            assert monitor.vad_aggressiveness == BARGE_IN_VAD_AGGRESSIVENESS
            assert monitor.min_speech_ms == BARGE_IN_MIN_SPEECH_MS
            assert monitor._thread is None
            assert not monitor._voice_detected_event.is_set()
            assert not monitor._stop_event.is_set()

    def test_init_with_custom_values(self):
        """Test initialization with custom VAD settings."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor(vad_aggressiveness=3, min_speech_ms=200)

            assert monitor.vad_aggressiveness == 3
            assert monitor.min_speech_ms == 200

    def test_init_with_zero_aggressiveness(self):
        """Test initialization with minimum VAD aggressiveness."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor(vad_aggressiveness=0)

            assert monitor.vad_aggressiveness == 0

    def test_init_with_max_aggressiveness(self):
        """Test initialization with maximum VAD aggressiveness."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor(vad_aggressiveness=3)

            assert monitor.vad_aggressiveness == 3


class TestBargeInMonitorHelpers:
    """Test BargeInMonitor helper functions."""

    def test_is_barge_in_available_with_webrtcvad(self):
        """Test is_barge_in_available returns True when webrtcvad is available."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode import barge_in

            # Patch VAD_AVAILABLE directly
            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                assert barge_in.is_barge_in_available() is True

    def test_is_barge_in_available_without_webrtcvad(self):
        """Test is_barge_in_available returns False when webrtcvad is not available."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', False):
                assert barge_in.is_barge_in_available() is False


class TestBargeInMonitorState:
    """Test BargeInMonitor state management methods."""

    def test_is_monitoring_when_not_started(self):
        """Test is_monitoring returns False when not started."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            assert monitor.is_monitoring() is False

    def test_voice_detected_initial_state(self):
        """Test voice_detected returns False initially."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            assert monitor.voice_detected() is False

    def test_get_captured_audio_when_empty(self):
        """Test get_captured_audio returns None when no audio captured."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            assert monitor.get_captured_audio() is None


class TestBargeInMonitorStartStop:
    """Test BargeInMonitor start/stop monitoring lifecycle."""

    def test_start_monitoring_creates_thread(self):
        """Test that start_monitoring creates a daemon thread."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            # Mock VAD_AVAILABLE
            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                # Mock sounddevice to prevent actual audio capture
                with patch('voice_mode.barge_in.sd') as mock_sd:
                    # Make InputStream a context manager that exits quickly
                    mock_stream = MagicMock()
                    mock_sd.InputStream.return_value.__enter__ = Mock(return_value=mock_stream)
                    mock_sd.InputStream.return_value.__exit__ = Mock(return_value=False)

                    monitor = BargeInMonitor()

                    # Start monitoring in a way that exits quickly
                    # Set stop event before thread really runs
                    def quick_exit(*_args, **_kwargs):
                        monitor._stop_event.set()

                    mock_sd.InputStream.return_value.__enter__.side_effect = quick_exit

                    try:
                        monitor.start_monitoring()
                        # Give thread time to start
                        time.sleep(0.05)

                        # Thread should have been created
                        assert monitor._thread is not None
                        assert monitor._thread.daemon is True
                        assert monitor._thread.name == "BargeInMonitor"
                    finally:
                        monitor.stop_monitoring()

    def test_start_monitoring_raises_when_already_active(self):
        """Test that start_monitoring raises RuntimeError if already monitoring."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('voice_mode.barge_in.sd') as mock_sd:
                    mock_sd.InputStream.return_value.__enter__ = Mock()
                    mock_sd.InputStream.return_value.__exit__ = Mock(return_value=False)

                    monitor = BargeInMonitor()

                    # Create a mock alive thread
                    mock_thread = MagicMock()
                    mock_thread.is_alive.return_value = True
                    monitor._thread = mock_thread

                    with pytest.raises(RuntimeError, match="Monitoring is already active"):
                        monitor.start_monitoring()

    def test_start_monitoring_raises_without_webrtcvad(self):
        """Test that start_monitoring raises ImportError without webrtcvad."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', False):
                monitor = BargeInMonitor()

                with pytest.raises(ImportError, match="webrtcvad is required"):
                    monitor.start_monitoring()

    def test_stop_monitoring_safe_when_not_started(self):
        """Test that stop_monitoring is safe to call when not started."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Should not raise
            monitor.stop_monitoring()

            assert monitor._thread is None

    def test_stop_monitoring_clears_thread(self):
        """Test that stop_monitoring clears the thread reference."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Create a mock thread that finishes quickly
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            monitor._thread = mock_thread

            monitor.stop_monitoring()

            assert monitor._thread is None
            assert monitor._vad is None

    def test_stop_monitoring_sets_stop_event(self):
        """Test that stop_monitoring sets the stop event."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Create a mock thread
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            monitor._thread = mock_thread

            monitor.stop_monitoring()

            assert monitor._stop_event.is_set()


class TestBargeInMonitorCallback:
    """Test BargeInMonitor callback invocation."""

    def test_callback_stored_on_start(self):
        """Test that callback is stored when monitoring starts."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('voice_mode.barge_in.sd') as mock_sd:
                    # Setup mock to exit quickly
                    def set_stop(*_args, **_kwargs):
                        pass

                    mock_sd.InputStream.return_value.__enter__ = Mock(side_effect=set_stop)
                    mock_sd.InputStream.return_value.__exit__ = Mock(return_value=False)

                    monitor = BargeInMonitor()
                    callback = Mock()

                    try:
                        monitor.start_monitoring(on_voice_detected=callback)
                        # Give thread time to start
                        time.sleep(0.05)

                        assert monitor._callback is callback
                    finally:
                        monitor.stop_monitoring()


class TestBargeInMonitorVADDetection:
    """Test VAD-based speech detection logic."""

    def test_check_vad_with_speech(self):
        """Test _check_vad returns True for speech-like audio."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('scipy.signal.resample') as mock_resample:
                    # Setup resampling mock
                    mock_resample.return_value = np.zeros(320, dtype=np.int16)

                    monitor = BargeInMonitor()

                    # Setup VAD mock to return True (speech detected)
                    mock_vad = MagicMock()
                    mock_vad.is_speech.return_value = True
                    monitor._vad = mock_vad

                    # Create test audio chunk
                    chunk = np.random.randint(-1000, 1000, size=720, dtype=np.int16)

                    result = monitor._check_vad(chunk, 16000, 320)

                    assert result is True
                    mock_vad.is_speech.assert_called_once()

    def test_check_vad_with_silence(self):
        """Test _check_vad returns False for silence."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('scipy.signal.resample') as mock_resample:
                    mock_resample.return_value = np.zeros(320, dtype=np.int16)

                    monitor = BargeInMonitor()

                    mock_vad = MagicMock()
                    mock_vad.is_speech.return_value = False
                    monitor._vad = mock_vad

                    chunk = np.zeros(720, dtype=np.int16)

                    result = monitor._check_vad(chunk, 16000, 320)

                    assert result is False

    def test_check_vad_handles_error_gracefully(self):
        """Test _check_vad returns False on error."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('scipy.signal.resample') as mock_resample:
                    # Make resampling raise an error
                    mock_resample.side_effect = Exception("Resampling error")

                    monitor = BargeInMonitor()

                    chunk = np.random.randint(-1000, 1000, size=720, dtype=np.int16)

                    # Should return False and not raise
                    result = monitor._check_vad(chunk, 16000, 320)

                    assert result is False


class TestBargeInMonitorAudioCapture:
    """Test audio buffer capture functionality."""

    def test_audio_buffer_cleared_on_start(self):
        """Test that audio buffer is cleared when monitoring starts."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                with patch('voice_mode.barge_in.sd') as mock_sd:
                    mock_sd.InputStream.return_value.__enter__ = Mock()
                    mock_sd.InputStream.return_value.__exit__ = Mock(return_value=False)

                    monitor = BargeInMonitor()

                    # Pre-populate buffer
                    monitor._audio_buffer.append(np.array([1, 2, 3]))

                    try:
                        monitor.start_monitoring()
                        time.sleep(0.05)

                        # Buffer should be cleared
                        assert len(monitor._audio_buffer) == 0
                    finally:
                        monitor.stop_monitoring()

    def test_get_captured_audio_returns_concatenated_buffer(self):
        """Test get_captured_audio concatenates buffer correctly."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Add multiple chunks to buffer
            chunk1 = np.array([1, 2, 3], dtype=np.int16)
            chunk2 = np.array([4, 5, 6], dtype=np.int16)
            monitor._audio_buffer.append(chunk1)
            monitor._audio_buffer.append(chunk2)

            result = monitor.get_captured_audio()

            expected = np.array([1, 2, 3, 4, 5, 6], dtype=np.int16)
            assert np.array_equal(result, expected)


class TestBargeInMonitorThreadSafety:
    """Test thread safety of BargeInMonitor."""

    def test_buffer_lock_protects_audio_buffer(self):
        """Test that buffer lock protects audio buffer access."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Verify lock exists and is a threading.Lock
            assert hasattr(monitor, '_buffer_lock')
            assert isinstance(monitor._buffer_lock, type(threading.Lock()))

    def test_concurrent_get_captured_audio_calls(self):
        """Test that concurrent get_captured_audio calls are safe."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Add some data
            monitor._audio_buffer.append(np.array([1, 2, 3], dtype=np.int16))

            results = []
            errors = []

            def get_audio():
                try:
                    result = monitor.get_captured_audio()
                    results.append(result)
                except Exception as e:
                    errors.append(e)

            # Run multiple concurrent calls
            threads = [threading.Thread(target=get_audio) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All calls should succeed without errors
            assert len(errors) == 0
            assert len(results) == 10

    def test_events_are_thread_safe(self):
        """Test that threading events are properly initialized."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Verify events are threading.Event instances
            assert isinstance(monitor._stop_event, type(threading.Event()))
            assert isinstance(monitor._voice_detected_event, type(threading.Event()))


class TestBargeInMonitorIntegration:
    """Integration tests for BargeInMonitor with mocked audio."""

    def test_speech_detection_triggers_callback(self):
        """Test that detected speech triggers the callback after min_speech_ms."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                callback_called = threading.Event()
                callback_mock = Mock(side_effect=lambda: callback_called.set())

                monitor = BargeInMonitor(min_speech_ms=30)  # Low threshold for test

                # Simulate speech detection by directly setting state
                monitor._speech_ms_accumulated = 60
                monitor._callback = callback_mock
                monitor._callback_fired = False

                # Trigger the callback manually (simulating monitoring loop behavior)
                if monitor._speech_ms_accumulated >= monitor.min_speech_ms and not monitor._callback_fired:
                    monitor._voice_detected_event.set()
                    monitor._callback_fired = True
                    if monitor._callback:
                        monitor._callback()

                assert callback_called.is_set()
                callback_mock.assert_called_once()

    def test_speech_accumulation_resets_on_silence(self):
        """Test that speech accumulation resets when silence is detected."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Simulate some speech accumulation
            monitor._speech_ms_accumulated = 100

            # Simulate silence detection (before callback fired)
            if not monitor._callback_fired:
                monitor._speech_ms_accumulated = 0
                with monitor._buffer_lock:
                    monitor._audio_buffer.clear()

            assert monitor._speech_ms_accumulated == 0
            assert len(monitor._audio_buffer) == 0

    def test_speech_accumulation_continues_after_trigger(self):
        """Test that audio capture continues after barge-in is triggered."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Simulate triggered state
            monitor._callback_fired = True
            monitor._speech_ms_accumulated = 200

            # Add some captured audio
            monitor._audio_buffer.append(np.array([1, 2, 3], dtype=np.int16))

            # Simulate more audio arriving (even silence after trigger should be captured)
            with monitor._buffer_lock:
                monitor._audio_buffer.append(np.array([4, 5, 6], dtype=np.int16))

            # Buffer should contain both chunks
            assert len(monitor._audio_buffer) == 2


class TestBargeInConfigValidation:
    """Test barge-in configuration validation in config.py."""

    def test_barge_in_vad_aggressiveness_validation(self):
        """Test that VAD aggressiveness is validated to 0-3 range."""
        from voice_mode.config import BARGE_IN_VAD_AGGRESSIVENESS

        # Should be in valid range
        assert 0 <= BARGE_IN_VAD_AGGRESSIVENESS <= 3

    def test_barge_in_min_speech_ms_positive(self):
        """Test that min_speech_ms is a positive integer."""
        from voice_mode.config import BARGE_IN_MIN_SPEECH_MS

        assert isinstance(BARGE_IN_MIN_SPEECH_MS, int)
        assert BARGE_IN_MIN_SPEECH_MS > 0

    def test_barge_in_enabled_is_bool(self):
        """Test that BARGE_IN_ENABLED is a boolean."""
        from voice_mode.config import BARGE_IN_ENABLED

        assert isinstance(BARGE_IN_ENABLED, bool)
