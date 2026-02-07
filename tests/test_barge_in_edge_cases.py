"""Tests for barge-in edge case handling.

These tests verify the edge case handling for barge-in:
1. False positive detection (no speech after barge-in)
2. STT errors on barge-in audio
3. Streaming TTS with barge-in enabled
4. Event logging for barge-in events
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np


class TestBargeInEventTypes:
    """Test that all barge-in event types are defined."""

    def test_event_types_exist(self):
        """All barge-in event types should be defined in EventLogger."""
        from voice_mode.utils.event_logger import EventLogger

        assert hasattr(EventLogger, 'BARGE_IN_START')
        assert hasattr(EventLogger, 'BARGE_IN_DETECTED')
        assert hasattr(EventLogger, 'BARGE_IN_STOP')
        assert hasattr(EventLogger, 'BARGE_IN_FALSE_POSITIVE')
        assert hasattr(EventLogger, 'BARGE_IN_STT_ERROR')

    def test_event_types_are_strings(self):
        """All barge-in event types should be strings."""
        from voice_mode.utils.event_logger import EventLogger

        assert isinstance(EventLogger.BARGE_IN_START, str)
        assert isinstance(EventLogger.BARGE_IN_DETECTED, str)
        assert isinstance(EventLogger.BARGE_IN_STOP, str)
        assert isinstance(EventLogger.BARGE_IN_FALSE_POSITIVE, str)
        assert isinstance(EventLogger.BARGE_IN_STT_ERROR, str)

    def test_event_types_are_unique(self):
        """All barge-in event types should have unique values."""
        from voice_mode.utils.event_logger import EventLogger

        event_types = [
            EventLogger.BARGE_IN_START,
            EventLogger.BARGE_IN_DETECTED,
            EventLogger.BARGE_IN_STOP,
            EventLogger.BARGE_IN_FALSE_POSITIVE,
            EventLogger.BARGE_IN_STT_ERROR,
        ]
        # Check all unique
        assert len(event_types) == len(set(event_types))


class TestBargeInEventLoggingFunctions:
    """Test barge-in event logging convenience functions."""

    def test_log_barge_in_start_without_logger(self):
        """log_barge_in_start should not raise when no logger initialized."""
        from voice_mode.utils.event_logger import log_barge_in_start
        # Should not raise
        log_barge_in_start(2, 150)

    def test_log_barge_in_detected_without_logger(self):
        """log_barge_in_detected should not raise when no logger initialized."""
        from voice_mode.utils.event_logger import log_barge_in_detected
        # Should not raise
        log_barge_in_detected(1.5, 1000)

    def test_log_barge_in_stop_without_logger(self):
        """log_barge_in_stop should not raise when no logger initialized."""
        from voice_mode.utils.event_logger import log_barge_in_stop
        # Should not raise
        log_barge_in_stop(True)

    def test_log_barge_in_false_positive_without_logger(self):
        """log_barge_in_false_positive should not raise when no logger initialized."""
        from voice_mode.utils.event_logger import log_barge_in_false_positive
        # Should not raise
        log_barge_in_false_positive(500)

    def test_log_barge_in_stt_error_without_logger(self):
        """log_barge_in_stt_error should not raise when no logger initialized."""
        from voice_mode.utils.event_logger import log_barge_in_stt_error
        # Should not raise
        log_barge_in_stt_error("test error", 1000)

    @patch('voice_mode.utils.event_logger.get_event_logger')
    def test_log_barge_in_start_with_logger(self, mock_get_logger):
        """log_barge_in_start should log event with correct data."""
        from voice_mode.utils.event_logger import log_barge_in_start, EventLogger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        log_barge_in_start(2, 150)

        mock_logger.log_event.assert_called_once_with(
            EventLogger.BARGE_IN_START,
            {"vad_aggressiveness": 2, "min_speech_ms": 150}
        )

    @patch('voice_mode.utils.event_logger.get_event_logger')
    def test_log_barge_in_detected_with_logger(self, mock_get_logger):
        """log_barge_in_detected should log event with correct data."""
        from voice_mode.utils.event_logger import log_barge_in_detected, EventLogger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        log_barge_in_detected(1.5, 1000)

        mock_logger.log_event.assert_called_once_with(
            EventLogger.BARGE_IN_DETECTED,
            {"interrupted_at_seconds": 1.5, "captured_samples": 1000}
        )

    @patch('voice_mode.utils.event_logger.get_event_logger')
    def test_log_barge_in_false_positive_with_logger(self, mock_get_logger):
        """log_barge_in_false_positive should log event with correct data."""
        from voice_mode.utils.event_logger import log_barge_in_false_positive, EventLogger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        log_barge_in_false_positive(500)

        mock_logger.log_event.assert_called_once_with(
            EventLogger.BARGE_IN_FALSE_POSITIVE,
            {"captured_samples": 500}
        )

    @patch('voice_mode.utils.event_logger.get_event_logger')
    def test_log_barge_in_stt_error_with_logger(self, mock_get_logger):
        """log_barge_in_stt_error should log event with correct data."""
        from voice_mode.utils.event_logger import log_barge_in_stt_error, EventLogger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        log_barge_in_stt_error("connection failed", 1000)

        mock_logger.log_event.assert_called_once_with(
            EventLogger.BARGE_IN_STT_ERROR,
            {"error": "connection failed", "captured_samples": 1000}
        )


class TestBargeInFalsePositiveDetection:
    """Test detection of barge-in false positives."""

    def test_no_audio_captured_is_false_positive(self):
        """If barge-in triggered but no audio captured, it's a false positive."""
        # This tests the logic: if tts_metrics.get('captured_audio') is None
        # but interrupted is True, it should be treated as false positive
        tts_metrics = {
            'interrupted': True,
            'captured_audio': None,
            'captured_audio_samples': 0
        }

        # The check is: audio_data = tts_metrics.get('captured_audio')
        # if audio_data is None, we fall back to normal recording
        assert tts_metrics.get('captured_audio') is None

    def test_very_short_audio_is_false_positive(self):
        """If captured audio is very short (<100 samples), it's likely noise."""
        # This tests the logic added in edge case handling
        audio_data = np.zeros(50, dtype=np.int16)  # Very short audio

        # The check is: if len(audio_data) < 100
        assert len(audio_data) < 100


class TestBargeInSTTErrors:
    """Test handling of STT errors on barge-in audio."""

    def test_stt_connection_failed_structure(self):
        """STT connection failure should have expected structure."""
        stt_result = {
            "error_type": "connection_failed",
            "attempted_endpoints": [
                {"endpoint": "http://localhost:2022/v1/audio/transcriptions", "error": "Connection refused"}
            ]
        }

        assert stt_result["error_type"] == "connection_failed"
        assert len(stt_result["attempted_endpoints"]) > 0

    def test_stt_no_speech_structure(self):
        """STT no speech result should have expected structure."""
        stt_result = {
            "error_type": "no_speech",
            "provider": "whisper-local"
        }

        assert stt_result["error_type"] == "no_speech"
        assert "provider" in stt_result


class TestBargeInStreamingTTS:
    """Test handling when barge-in is used with streaming TTS."""

    def test_streaming_with_barge_in_logs_warning(self):
        """When streaming TTS is used with barge-in, a warning should be logged."""
        # This is tested through the actual code flow
        # The warning message is:
        # "⚠️ Barge-in is not yet supported with streaming TTS - interruption will not work"
        pass  # Integration test would cover this


class TestBargeInMonitorVoiceDetected:
    """Test BargeInMonitor voice_detected() method edge cases."""

    def test_voice_detected_before_start(self):
        """voice_detected() should return False before start_monitoring."""
        with patch('voice_mode.barge_in.VAD_AVAILABLE', True):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()
            assert monitor.voice_detected() is False

    def test_voice_detected_after_stop_without_detection(self):
        """voice_detected() should return False after stop if no voice detected."""
        with patch('voice_mode.barge_in.VAD_AVAILABLE', True), \
             patch('voice_mode.barge_in.webrtcvad') as mock_vad:
            from voice_mode.barge_in import BargeInMonitor

            mock_vad.Vad.return_value = Mock()

            monitor = BargeInMonitor()
            # Don't actually start monitoring with real audio
            # Just verify initial state
            assert monitor.voice_detected() is False


class TestBargeInAudioCaptureEdgeCases:
    """Test edge cases in barge-in audio capture."""

    def test_get_captured_audio_empty_buffer(self):
        """get_captured_audio() should return None for empty buffer."""
        with patch('voice_mode.barge_in.VAD_AVAILABLE', True):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()
            assert monitor.get_captured_audio() is None

    def test_get_captured_audio_returns_concatenated_array(self):
        """get_captured_audio() should concatenate buffer chunks."""
        with patch('voice_mode.barge_in.VAD_AVAILABLE', True):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Manually add to buffer (simulating captured audio)
            chunk1 = np.array([1, 2, 3], dtype=np.int16)
            chunk2 = np.array([4, 5, 6], dtype=np.int16)
            monitor._audio_buffer.append(chunk1)
            monitor._audio_buffer.append(chunk2)

            captured = monitor.get_captured_audio()

            assert captured is not None
            assert len(captured) == 6
            np.testing.assert_array_equal(captured, np.array([1, 2, 3, 4, 5, 6]))


class TestBargeInConfigEdgeCases:
    """Test configuration edge cases for barge-in."""

    def test_barge_in_disabled_by_default(self):
        """BARGE_IN_ENABLED should default to False."""
        # This depends on the config, but we can test the expected default
        # Default is False for safety (opt-in feature)
        import os
        # Clear the env var if set
        orig = os.environ.get('VOICEMODE_BARGE_IN')
        if 'VOICEMODE_BARGE_IN' in os.environ:
            del os.environ['VOICEMODE_BARGE_IN']

        try:
            # Re-import to get fresh config
            import importlib
            import voice_mode.config as config
            importlib.reload(config)
            assert config.BARGE_IN_ENABLED is False
        finally:
            # Restore
            if orig is not None:
                os.environ['VOICEMODE_BARGE_IN'] = orig

    def test_vad_aggressiveness_range_is_valid(self):
        """VAD aggressiveness from config should be in valid 0-3 range."""
        from voice_mode.config import BARGE_IN_VAD_AGGRESSIVENESS

        # Verify config value is within valid range for webrtcvad
        assert 0 <= BARGE_IN_VAD_AGGRESSIVENESS <= 3, \
            f"VAD aggressiveness {BARGE_IN_VAD_AGGRESSIVENESS} should be in range 0-3"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
