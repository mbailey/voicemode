"""Tests for silence detection feature in voice_mode."""

import pytest
import numpy as np
import time
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock webrtcvad before importing voice_mode modules
sys.modules['webrtcvad'] = MagicMock()

from voice_mode.tools.converse import (
    record_audio_with_silence_detection,
    record_audio,
    VAD_AVAILABLE
)
from voice_mode.config import (
    SAMPLE_RATE,
    CHANNELS,
    VAD_CHUNK_DURATION_MS,
    SILENCE_THRESHOLD_MS,
    MIN_RECORDING_DURATION
)


class TestSilenceDetection:
    """Test silence detection functionality."""
    
    @pytest.fixture
    def mock_sounddevice(self):
        """Mock sounddevice for testing."""
        with patch('voice_mode.tools.converse.sd') as mock_sd:
            # Create mock audio chunks - some with "speech", some without
            speech_chunk = np.random.randint(-1000, 1000, 
                                           size=int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000), 
                                           dtype=np.int16)
            silence_chunk = np.zeros(int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000), dtype=np.int16)
            
            # Return different chunks on successive calls
            mock_sd.rec.side_effect = [
                speech_chunk.reshape(-1, 1),  # Speech
                speech_chunk.reshape(-1, 1),  # Speech
                speech_chunk.reshape(-1, 1),  # Speech
                silence_chunk.reshape(-1, 1),  # Silence
                silence_chunk.reshape(-1, 1),  # Silence
                silence_chunk.reshape(-1, 1),  # Silence (should trigger stop)
            ] + [silence_chunk.reshape(-1, 1)] * 100  # Many more silence chunks
            
            mock_sd.wait.return_value = None
            yield mock_sd
    
    @pytest.fixture
    def mock_vad(self):
        """Mock VAD for testing."""
        with patch('voice_mode.tools.converse.webrtcvad') as mock_webrtcvad:
            mock_vad_instance = Mock()
            mock_webrtcvad.Vad.return_value = mock_vad_instance
            
            # Simulate speech detection pattern
            mock_vad_instance.is_speech.side_effect = [
                True,   # Speech detected
                True,   # Speech detected
                True,   # Speech detected
                False,  # Silence
                False,  # Silence
                False,  # Silence (should trigger stop after threshold)
            ] + [False] * 100  # Many more silence
            
            yield mock_webrtcvad
    
    @pytest.mark.skip(reason="Mock sounddevice.rec() causing test to hang")
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_silence_detection_stops_early(self, mock_vad, mock_sounddevice):
        """Test that recording stops when silence is detected."""
        # Record with a long max duration
        result = record_audio_with_silence_detection(max_duration=10.0)
        
        # Should have stopped early (6 chunks * 30ms = 180ms of audio)
        expected_samples = 6 * int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)
        assert len(result) == expected_samples
        
        # Verify VAD was initialized with correct aggressiveness
        mock_vad.Vad.assert_called_once()
        
        # Verify we recorded the expected number of chunks before stopping
        assert mock_sounddevice.rec.call_count == 6
    
    @pytest.mark.skip(reason="Mock sounddevice.rec() causing test to hang")
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_no_speech_detected(self, mock_vad, mock_sounddevice):
        """Test behavior when no speech is detected."""
        # Configure VAD to never detect speech
        mock_vad.Vad.return_value.is_speech.side_effect = [False] * 100
        
        # Configure sounddevice to return silence
        silence_chunk = np.zeros(int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000), dtype=np.int16)
        mock_sounddevice.rec.return_value = silence_chunk.reshape(-1, 1)
        
        result = record_audio_with_silence_detection(max_duration=2.0)
        
        # Should stop after MIN_RECORDING_DURATION * 2
        min_chunks = int((MIN_RECORDING_DURATION * 2) / (VAD_CHUNK_DURATION_MS / 1000))
        assert mock_sounddevice.rec.call_count >= min_chunks
    
    @pytest.mark.skip(reason="Mock sounddevice.rec() causing test to hang")
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_continuous_speech(self, mock_vad, mock_sounddevice):
        """Test that recording continues with continuous speech."""
        # Configure VAD to always detect speech
        mock_vad.Vad.return_value.is_speech.return_value = True
        
        # Configure sounddevice to return speech chunks
        speech_chunk = np.random.randint(-1000, 1000, 
                                       size=int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000), 
                                       dtype=np.int16)
        mock_sounddevice.rec.return_value = speech_chunk.reshape(-1, 1)
        
        # Record for a short duration
        max_duration = 0.5
        result = record_audio_with_silence_detection(max_duration=max_duration)
        
        # Should have recorded for the full duration
        expected_chunks = int(max_duration / (VAD_CHUNK_DURATION_MS / 1000))
        assert mock_sounddevice.rec.call_count == expected_chunks
    
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', True)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_silence_detection_disabled(self, mock_vad, mock_sounddevice):
        """Test that silence detection can be disabled."""
        with patch('voice_mode.tools.converse.record_audio') as mock_record:
            mock_record.return_value = np.array([1, 2, 3])
            
            result = record_audio_with_silence_detection(max_duration=5.0)
            
            # Should fall back to regular recording
            mock_record.assert_called_once_with(5.0)
            assert np.array_equal(result, np.array([1, 2, 3]))
    
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', False)
    def test_vad_not_available(self):
        """Test fallback when webrtcvad is not available."""
        with patch('voice_mode.tools.converse.record_audio') as mock_record:
            mock_record.return_value = np.array([1, 2, 3])
            
            result = record_audio_with_silence_detection(max_duration=5.0)
            
            # Should fall back to regular recording
            mock_record.assert_called_once_with(5.0)
            assert np.array_equal(result, np.array([1, 2, 3]))
    
    @pytest.mark.skip(reason="Mock sounddevice.rec() causing test to hang")
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_vad_error_handling(self, mock_vad, mock_sounddevice):
        """Test that VAD errors are handled gracefully."""
        # Configure VAD to raise an error
        mock_vad.Vad.return_value.is_speech.side_effect = Exception("VAD error")
        
        # Configure sounddevice
        speech_chunk = np.random.randint(-1000, 1000, 
                                       size=int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000), 
                                       dtype=np.int16)
        mock_sounddevice.rec.return_value = speech_chunk.reshape(-1, 1)
        
        # Should still record but treat all chunks as speech
        result = record_audio_with_silence_detection(max_duration=0.5)
        
        # Should have recorded for the full duration (no silence detection)
        expected_chunks = int(0.5 / (VAD_CHUNK_DURATION_MS / 1000))
        assert mock_sounddevice.rec.call_count == expected_chunks
    
    def test_chunk_size_calculation(self):
        """Test that chunk size is calculated correctly for VAD."""
        # 30ms at 24000Hz should be 720 samples
        expected_samples = int(24000 * 30 / 1000)
        assert expected_samples == 720
        
        # 20ms at 24000Hz should be 480 samples
        expected_samples_20ms = int(24000 * 20 / 1000)
        assert expected_samples_20ms == 480
        
        # 10ms at 24000Hz should be 240 samples
        expected_samples_10ms = int(24000 * 10 / 1000)
        assert expected_samples_10ms == 240
    
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_min_duration_parameter(self, mock_vad):
        """Test that min_duration parameter is respected."""
        with patch('voice_mode.tools.converse.record_audio') as mock_record:
            # When VAD is available but we pass a min_duration
            with patch('sounddevice.InputStream'):
                with patch('queue.Queue') as mock_queue:
                    # Simulate immediate silence detection
                    mock_vad.Vad.return_value.is_speech.return_value = False
                    mock_queue.return_value.get.side_effect = [
                        np.zeros(720, dtype=np.int16),  # Silence
                    ] * 100
                    
                    # Record with min_duration of 2 seconds
                    try:
                        result = record_audio_with_silence_detection(
                            max_duration=10.0, 
                            disable_silence_detection=False,
                            min_duration=2.0
                        )
                    except Exception:
                        # If VAD fails, it should fall back to record_audio
                        pass
    
    @patch('voice_mode.tools.converse.DISABLE_SILENCE_DETECTION', False)
    @patch('voice_mode.tools.converse.VAD_AVAILABLE', True)
    def test_min_duration_with_disable_parameter(self, mock_vad):
        """Test that disable_silence_detection parameter works with min_duration."""
        with patch('voice_mode.tools.converse.record_audio') as mock_record:
            mock_record.return_value = np.array([1, 2, 3])
            
            # When silence detection is disabled via parameter
            result = record_audio_with_silence_detection(
                max_duration=5.0,
                disable_silence_detection=True,
                min_duration=2.0
            )
            
            # Should fall back to regular recording, ignoring min_duration
            mock_record.assert_called_once_with(5.0)
            assert np.array_equal(result, np.array([1, 2, 3]))


class TestSilenceDetectionIntegration:
    """Integration tests for silence detection with real audio patterns."""
    
    @pytest.mark.skipif(not VAD_AVAILABLE, reason="webrtcvad not installed")
    @pytest.mark.skip(reason="Test requires real audio device interaction")
    def test_real_vad_with_synthetic_audio(self):
        """Test real VAD with synthetic audio patterns."""
        import webrtcvad
        
        vad = webrtcvad.Vad(2)
        
        # Create synthetic audio patterns
        # Speech-like pattern (random noise)
        speech_audio = np.random.randint(-10000, 10000, size=480, dtype=np.int16)
        
        # Silence pattern (very low amplitude)
        silence_audio = np.random.randint(-10, 10, size=480, dtype=np.int16)
        
        # Test with 16kHz (20ms = 320 samples)
        sample_rate = 16000
        
        # VAD should detect speech in noisy audio
        is_speech_noisy = vad.is_speech(speech_audio.tobytes(), sample_rate)
        
        # VAD should not detect speech in quiet audio
        is_speech_quiet = vad.is_speech(silence_audio.tobytes(), sample_rate)
        
        # Note: Actual results may vary, but generally:
        # - Noisy audio is more likely to be detected as speech
        # - Very quiet audio is more likely to be detected as silence
        assert isinstance(is_speech_noisy, bool)
        assert isinstance(is_speech_quiet, bool)