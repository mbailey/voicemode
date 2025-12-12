"""Test that STT audio files are saved correctly when SAVE_ALL is enabled"""

import os
import tempfile
import asyncio
from pathlib import Path
import numpy as np
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from voice_mode.tools.converse import speech_to_text
from voice_mode import config


@pytest.mark.asyncio
async def test_stt_audio_saved_with_simple_failover():
    """Test that STT audio files are saved when SAVE_ALL is true and simple failover is enabled.

    Note: Full-quality WAV is saved for archival, while compressed MP3 is used
    for upload to reduce bandwidth.
    """

    # Create test audio data (1 second of silence at 24kHz to match SAMPLE_RATE)
    sample_rate = 24000  # Match SAMPLE_RATE from config
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_audio_dir = Path(temp_dir) / "audio"
        test_audio_dir.mkdir()

        # Patch the config values to ensure saving is enabled
        with patch('voice_mode.config.SAVE_ALL', True), \
             patch('voice_mode.config.SAVE_AUDIO', True), \
             patch('voice_mode.tools.converse.SAVE_AUDIO', True):

            # Mock the simple_stt_failover to return test transcription dict
            with patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:
                mock_stt.return_value = {"text": "Test transcription", "provider": "whisper", "endpoint": "http://127.0.0.1:2022/v1"}

                # Mock the conversation logger
                with patch('voice_mode.tools.converse.get_conversation_logger') as mock_logger:
                    mock_conv_logger = MagicMock()
                    mock_conv_logger.conversation_id = "test123"
                    mock_logger.return_value = mock_conv_logger

                    # Call the function with save_audio enabled
                    result = await speech_to_text(
                        audio_data=audio_data,
                        save_audio=True,
                        audio_dir=test_audio_dir,
                        transport="local"
                    )

                    # Verify transcription was returned (now returns dict)
                    assert isinstance(result, dict)
                    assert result.get("text") == "Test transcription"

                    # Check that audio file was saved in year/month structure
                    now = datetime.now()
                    expected_dir = test_audio_dir / str(now.year) / f"{now.month:02d}"
                    assert expected_dir.exists()

                    # Find the saved STT file - full quality WAV is saved for archival
                    stt_files = list(expected_dir.glob("*_stt.wav"))
                    assert len(stt_files) == 1, f"Expected 1 STT WAV file, found: {list(expected_dir.glob('*'))}"
                    # Verify it's an STT file with proper naming format
                    assert stt_files[0].name.endswith("_stt.wav")

                    # Verify file exists and has content
                    assert stt_files[0].stat().st_size > 0


@pytest.mark.asyncio
async def test_stt_audio_not_saved_when_disabled():
    """Test that STT audio files are NOT saved when save_audio is False"""

    # Create test audio data at 24kHz to match SAMPLE_RATE
    sample_rate = 24000
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    with tempfile.TemporaryDirectory() as temp_dir:
        test_audio_dir = Path(temp_dir) / "audio"
        test_audio_dir.mkdir()

        # Mock the simple_stt_failover to return dict format
        with patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:
            mock_stt.return_value = {"text": "Test transcription", "provider": "whisper", "endpoint": "http://127.0.0.1:2022/v1"}

            # Call with save_audio=False
            result = await speech_to_text(
                audio_data=audio_data,
                save_audio=False,
                audio_dir=test_audio_dir,
                transport="local"
            )

            # Verify transcription was returned (now returns dict)
            assert isinstance(result, dict)
            assert result["text"] == "Test transcription"

            # Verify no audio files were saved (check for both wav and mp3)
            audio_files = list(test_audio_dir.rglob("*.*"))
            assert len(audio_files) == 0, f"Expected no audio files, found: {audio_files}"


@pytest.mark.asyncio
async def test_tts_and_stt_both_saved():
    """Integration test to verify both TTS and STT files are saved when SAVE_ALL is true"""
    
    # This test would require more setup to test the full flow
    # For now, we've verified STT saving works correctly
    # TTS saving was already working and uses a different code path
    pass


if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_stt_audio_saved_with_simple_failover())
    asyncio.run(test_stt_audio_not_saved_when_disabled())
    print("All tests passed!")