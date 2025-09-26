"""Integration tests for minimum duration feature in converse tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import numpy as np

# Mock dependencies before import
import sys
sys.modules['webrtcvad'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()
sys.modules['livekit'] = MagicMock()


@pytest.mark.asyncio
class TestMinDurationIntegration:
    """Test minimum duration functionality in converse tool."""
    
    async def test_converse_validates_min_duration(self):
        """Test that converse validates min_listen_duration parameter."""
        from voice_mode.tools.converse import converse
        
        # Get the actual function from the MCP tool wrapper
        converse_func = converse.fn
        
        # Mock required dependencies
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            # Mock FFmpeg availability by patching the module attribute
            import voice_mode.config
            voice_mode.config.FFMPEG_AVAILABLE = True
            
            # Test negative min_listen_duration
            result = await converse_func(
                message="Test",
                wait_for_response=True,
                min_listen_duration=-1.0
            )
            assert "min_listen_duration cannot be negative" in result
            
            # Test min > max duration
            with patch('voice_mode.tools.converse.logger') as mock_logger:
                with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                    mock_tts.return_value = (True, {}, {})
                    with patch('voice_mode.tools.converse.record_audio_with_silence_detection') as mock_record:
                        mock_record.return_value = (np.array([1, 2, 3]), True)  # Returns tuple (audio, speech_detected)
                        with patch('voice_mode.tools.converse.speech_to_text', new_callable=AsyncMock) as mock_stt:
                            mock_stt.return_value = {"text": "Test response", "provider": "whisper"}
                            
                            result = await converse_func(
                                message="Test",
                                wait_for_response=True,
                                listen_duration=5.0,
                                min_listen_duration=10.0
                            )
                            
                            # Should log warning and adjust min_listen_duration
                            mock_logger.warning.assert_called()
                            warning_msg = mock_logger.warning.call_args[0][0]
                            assert "min_listen_duration" in warning_msg
                            assert "greater than listen_duration" in warning_msg
    
    async def test_converse_passes_min_duration_to_recording(self):
        """Test that converse passes min_listen_duration to recording function."""
        from voice_mode.tools.converse import converse
        
        # Get the actual function from the MCP tool wrapper
        converse_func = converse.fn
        
        # Mock all dependencies
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            # Mock FFmpeg availability by patching the module attribute
            import voice_mode.config
            voice_mode.config.FFMPEG_AVAILABLE = True
            
            with patch('voice_mode.tools.converse.text_to_speech_with_failover', new_callable=AsyncMock) as mock_tts:
                mock_tts.return_value = (True, {'generation': 0.5, 'playback': 1.0}, {})
                with patch('voice_mode.tools.converse.record_audio_with_silence_detection') as mock_record:
                    mock_record.return_value = (np.array([1, 2, 3]), True)  # Returns tuple (audio, speech_detected)
                    with patch('voice_mode.tools.converse.speech_to_text', new_callable=AsyncMock) as mock_stt:
                        mock_stt.return_value = {"text": "Test response", "provider": "whisper"}
                        
                        # Test with specific min_listen_duration
                        result = await converse_func(
                            message="Test question",
                            wait_for_response=True,
                            listen_duration=30.0,
                            min_listen_duration=2.5
                        )
                        
                        # Verify record_audio_with_silence_detection was called with correct parameters
                        mock_record.assert_called_once()
                        args = mock_record.call_args[0]
                        assert args[0] == 30.0  # max_duration
                        assert args[1] == False  # disable_silence_detection
                        assert args[2] == 2.5    # min_duration
                        
                        assert "Test response" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])