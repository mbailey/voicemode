"""Integration tests for minimum duration feature in converse tool."""

import pytest
from unittest.mock import AsyncMock, patch
import numpy as np

# VM-2072: this file used to replace sys.modules['sounddevice'] and
# sys.modules['webrtcvad'] with MagicMocks HERE, at module level -- which pytest
# executes at COLLECTION time, i.e. before the first test of the whole session
# and for the rest of it.  Measured on 2026-08-19: every test in the suite then
# imported a Mock instead of sounddevice, five of the audio guard's own drills
# silently stopped testing anything, and the guard's repair path errored at the
# teardown of all 2116 tests.  One line, whole-session blast radius, invisible
# from any narrow selection.
#
# Neither mock was needed: sounddevice and webrtcvad-wheels are both hard
# runtime dependencies of this package (pyproject.toml), so they are installed
# wherever these tests run.  Real audio calls are unreachable anyway -- the
# audio guard (tests/audio_guard/) blocks the device for every test run, which
# is a stronger guarantee than a mock in one file, and it does not lie to the
# other 2115 tests.
#
# If you need a stand-in for a module here, patch the SEAM the code under test
# uses (e.g. patch('voice_mode.tools.converse.sd.rec')) rather than replacing a
# module for everybody.


@pytest.mark.asyncio
class TestMinDurationIntegration:
    """Test minimum duration functionality in converse tool."""
    
    async def test_converse_validates_min_duration(self):
        """Test that converse validates listen_duration_min parameter."""
        from voice_mode.tools.converse import converse
        
        # Get the actual function from the MCP tool wrapper
        # FastMCP 2.x: tool has .fn attribute; 3.x: tool IS the function
        converse_func = getattr(converse, 'fn', converse)
        
        # Mock required dependencies
        with patch('voice_mode.tools.converse.startup_initialization', new_callable=AsyncMock):
            # Mock FFmpeg availability by patching the module attribute
            import voice_mode.config
            voice_mode.config.FFMPEG_AVAILABLE = True
            
            # Test negative listen_duration_min
            result = await converse_func(
                message="Test",
                wait_for_response=True,
                listen_duration_min=-1.0
            )
            assert "listen_duration_min cannot be negative" in result
            
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
                                listen_duration_max=5.0,
                                listen_duration_min=10.0
                            )
                            
                            # Should log warning and adjust listen_duration_min
                            mock_logger.warning.assert_called()
                            warning_msg = mock_logger.warning.call_args[0][0]
                            assert "listen_duration_min" in warning_msg
                            assert "greater than listen_duration" in warning_msg
    
    async def test_converse_passes_min_duration_to_recording(self):
        """Test that converse passes listen_duration_min to recording function."""
        from voice_mode.tools.converse import converse
        
        # Get the actual function from the MCP tool wrapper
        # FastMCP 2.x: tool has .fn attribute; 3.x: tool IS the function
        converse_func = getattr(converse, 'fn', converse)
        
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
                        
                        # Test with specific listen_duration_min
                        result = await converse_func(
                            message="Test question",
                            wait_for_response=True,
                            listen_duration_max=30.0,
                            listen_duration_min=2.5
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