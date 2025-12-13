"""Test that STT compression is skipped for local endpoints."""

import tempfile
import asyncio
from pathlib import Path
import numpy as np
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from voice_mode.tools.converse import speech_to_text
from voice_mode import config


@pytest.mark.asyncio
async def test_stt_skips_compression_for_local_endpoint():
    """Test that STT skips compression when primary endpoint is local (auto mode)."""

    # Create test audio data (1 second of silence at 24kHz to match SAMPLE_RATE)
    sample_rate = 24000
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    # Track what format was used
    format_used = None

    def capture_format(audio_data, output_format):
        nonlocal format_used
        format_used = output_format
        # Return minimal valid audio bytes
        import io
        from pydub import AudioSegment
        audio = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        buffer = io.BytesIO()
        if output_format == "wav":
            audio.export(buffer, format="wav")
        else:
            audio.export(buffer, format="mp3", bitrate="32k")
        return buffer.getvalue()

    # Mock local endpoint as primary with auto mode (default)
    with patch('voice_mode.config.STT_BASE_URLS', ['http://127.0.0.1:2022/v1']), \
         patch('voice_mode.config.STT_COMPRESS', 'auto'), \
         patch('voice_mode.tools.converse.prepare_audio_for_stt', side_effect=capture_format), \
         patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:

        mock_stt.return_value = {"text": "Test", "provider": "whisper", "endpoint": "http://127.0.0.1:2022/v1"}

        await speech_to_text(
            audio_data=audio_data,
            save_audio=False,
            audio_dir=None,
            transport="local"
        )

        # Verify WAV format was used (no compression)
        assert format_used == "wav", f"Expected 'wav' for local endpoint in auto mode, got '{format_used}'"


@pytest.mark.asyncio
async def test_stt_compresses_for_remote_endpoint():
    """Test that STT compresses when primary endpoint is remote (auto mode)."""

    sample_rate = 24000
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    format_used = None

    def capture_format(audio_data, output_format):
        nonlocal format_used
        format_used = output_format
        import io
        from pydub import AudioSegment
        audio = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        buffer = io.BytesIO()
        if output_format == "wav":
            audio.export(buffer, format="wav")
        else:
            audio.export(buffer, format="mp3", bitrate="32k")
        return buffer.getvalue()

    # Mock remote endpoint as primary with auto mode
    with patch('voice_mode.config.STT_BASE_URLS', ['https://api.openai.com/v1']), \
         patch('voice_mode.config.STT_COMPRESS', 'auto'), \
         patch('voice_mode.tools.converse.STT_AUDIO_FORMAT', 'mp3'), \
         patch('voice_mode.tools.converse.prepare_audio_for_stt', side_effect=capture_format), \
         patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:

        mock_stt.return_value = {"text": "Test", "provider": "openai", "endpoint": "https://api.openai.com/v1"}

        await speech_to_text(
            audio_data=audio_data,
            save_audio=False,
            audio_dir=None,
            transport="local"
        )

        # Verify MP3 format was used (compression enabled)
        assert format_used == "mp3", f"Expected 'mp3' for remote endpoint in auto mode, got '{format_used}'"


@pytest.mark.asyncio
async def test_stt_always_mode_compresses_local():
    """Test that STT_COMPRESS=always compresses even for local endpoints."""

    sample_rate = 24000
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    format_used = None

    def capture_format(audio_data, output_format):
        nonlocal format_used
        format_used = output_format
        import io
        from pydub import AudioSegment
        audio = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        buffer = io.BytesIO()
        if output_format == "wav":
            audio.export(buffer, format="wav")
        else:
            audio.export(buffer, format="mp3", bitrate="32k")
        return buffer.getvalue()

    # Mock local endpoint BUT with always mode
    with patch('voice_mode.config.STT_BASE_URLS', ['http://127.0.0.1:2022/v1']), \
         patch('voice_mode.config.STT_COMPRESS', 'always'), \
         patch('voice_mode.tools.converse.STT_AUDIO_FORMAT', 'mp3'), \
         patch('voice_mode.tools.converse.prepare_audio_for_stt', side_effect=capture_format), \
         patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:

        mock_stt.return_value = {"text": "Test", "provider": "whisper", "endpoint": "http://127.0.0.1:2022/v1"}

        await speech_to_text(
            audio_data=audio_data,
            save_audio=False,
            audio_dir=None,
            transport="local"
        )

        # Verify MP3 format was used despite local endpoint (always mode)
        assert format_used == "mp3", f"Expected 'mp3' with always mode, got '{format_used}'"


@pytest.mark.asyncio
async def test_stt_never_mode_skips_compression_for_remote():
    """Test that STT_COMPRESS=never skips compression even for remote endpoints."""

    sample_rate = 24000
    audio_data = np.zeros(sample_rate, dtype=np.int16)

    format_used = None

    def capture_format(audio_data, output_format):
        nonlocal format_used
        format_used = output_format
        import io
        from pydub import AudioSegment
        audio = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        buffer = io.BytesIO()
        if output_format == "wav":
            audio.export(buffer, format="wav")
        else:
            audio.export(buffer, format="mp3", bitrate="32k")
        return buffer.getvalue()

    # Mock remote endpoint BUT with never mode
    with patch('voice_mode.config.STT_BASE_URLS', ['https://api.openai.com/v1']), \
         patch('voice_mode.config.STT_COMPRESS', 'never'), \
         patch('voice_mode.tools.converse.prepare_audio_for_stt', side_effect=capture_format), \
         patch('voice_mode.simple_failover.simple_stt_failover', new_callable=AsyncMock) as mock_stt:

        mock_stt.return_value = {"text": "Test", "provider": "openai", "endpoint": "https://api.openai.com/v1"}

        await speech_to_text(
            audio_data=audio_data,
            save_audio=False,
            audio_dir=None,
            transport="local"
        )

        # Verify WAV format was used despite remote endpoint (never mode)
        assert format_used == "wav", f"Expected 'wav' with never mode, got '{format_used}'"


@pytest.mark.asyncio
async def test_is_local_provider_detection():
    """Test that is_local_provider correctly identifies local endpoints."""
    from voice_mode.provider_discovery import is_local_provider

    # Local endpoints
    assert is_local_provider("http://127.0.0.1:2022/v1") == True
    assert is_local_provider("http://localhost:2022/v1") == True
    assert is_local_provider("http://127.0.0.1:8880/v1") == True  # Kokoro
    assert is_local_provider("http://localhost:8880/v1") == True

    # Remote endpoints
    assert is_local_provider("https://api.openai.com/v1") == False
    assert is_local_provider("https://custom.cloud.service/v1") == False


if __name__ == "__main__":
    asyncio.run(test_stt_skips_compression_for_local_endpoint())
    asyncio.run(test_stt_compresses_for_remote_endpoint())
    asyncio.run(test_stt_always_mode_compresses_local())
    asyncio.run(test_stt_never_mode_skips_compression_for_remote())
    asyncio.run(test_is_local_provider_detection())
    print("All tests passed!")
