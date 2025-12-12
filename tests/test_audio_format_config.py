#!/usr/bin/env python
"""
Test audio format configuration functionality.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Set required environment variables before imports
os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'test-key')


class TestAudioFormatConfiguration:
    """Test audio format configuration and validation"""
    
    def test_default_audio_format(self):
        """Test that default audio format is pcm"""
        # Import after setting env vars
        from voice_mode.config import AUDIO_FORMAT, TTS_AUDIO_FORMAT, STT_AUDIO_FORMAT
        
        assert AUDIO_FORMAT == "pcm"
        assert TTS_AUDIO_FORMAT == "pcm"  # Default changed to PCM for optimal streaming
        assert STT_AUDIO_FORMAT == "mp3"  # PCM not supported by OpenAI Whisper, defaults to mp3
    
    @patch.dict(os.environ, {
        'VOICEMODE_AUDIO_FORMAT': 'mp3',
        'VOICEMODE_TTS_AUDIO_FORMAT': 'flac',
        'VOICEMODE_STT_AUDIO_FORMAT': 'wav'
    })
    def test_custom_audio_formats(self):
        """Test custom audio format configuration"""
        # Need to reload the module to pick up new env vars
        import importlib
        import voice_mode.config
        importlib.reload(voice_mode.config)
        
        from voice_mode.config import AUDIO_FORMAT, TTS_AUDIO_FORMAT, STT_AUDIO_FORMAT
        
        assert AUDIO_FORMAT == "mp3"
        assert TTS_AUDIO_FORMAT == "flac"
        assert STT_AUDIO_FORMAT == "wav"
    
    def test_validate_audio_format(self):
        """Test audio format validation for providers"""
        from voice_mode.config import validate_audio_format
        
        # OpenAI supports opus
        assert validate_audio_format("opus", "openai", "tts") == "opus"
        
        # Kokoro now supports opus
        assert validate_audio_format("opus", "kokoro", "tts") == "opus"
        
        # Whisper supports wav
        assert validate_audio_format("wav", "whisper-local", "stt") == "wav"
        
        # Kokoro now supports pcm
        assert validate_audio_format("pcm", "kokoro", "tts") == "pcm"
        
        # Invalid format (aac) for Kokoro should fallback
        assert validate_audio_format("aac", "kokoro", "tts") in ["mp3", "opus", "flac", "wav", "pcm"]
    
    def test_get_provider_supported_formats(self):
        """Test getting supported formats for providers"""
        from voice_mode.config import get_provider_supported_formats
        
        # OpenAI TTS formats
        openai_tts = get_provider_supported_formats("openai", "tts")
        assert "opus" in openai_tts
        assert "mp3" in openai_tts
        assert "wav" in openai_tts
        
        # Kokoro TTS formats
        kokoro_tts = get_provider_supported_formats("kokoro", "tts")
        assert "mp3" in kokoro_tts
        assert "wav" in kokoro_tts
        
        # Whisper STT formats
        whisper_stt = get_provider_supported_formats("whisper-local", "stt")
        assert "wav" in whisper_stt
        assert "mp3" in whisper_stt
    
    def test_get_audio_loader_for_format(self):
        """Test getting correct audio loader for formats"""
        from voice_mode.config import get_audio_loader_for_format
        from pydub import AudioSegment
        
        # Test known formats
        assert get_audio_loader_for_format("mp3") == AudioSegment.from_mp3
        assert get_audio_loader_for_format("wav") == AudioSegment.from_wav
        assert get_audio_loader_for_format("opus") == AudioSegment.from_ogg
        # FLAC might use from_flac or from_file depending on pydub version
        flac_loader = get_audio_loader_for_format("flac")
        assert flac_loader in [AudioSegment.from_file, getattr(AudioSegment, 'from_flac', AudioSegment.from_file)]
        
        # Test generic formats
        assert get_audio_loader_for_format("aac") == AudioSegment.from_file
        assert get_audio_loader_for_format("m4a") == AudioSegment.from_file
        
        # Test unknown format
        assert get_audio_loader_for_format("unknown") is None
    
    def test_get_format_export_params(self):
        """Test getting export parameters for formats"""
        from voice_mode.config import get_format_export_params, MP3_BITRATE, OPUS_BITRATE
        
        # MP3 params
        mp3_params = get_format_export_params("mp3")
        assert mp3_params["format"] == "mp3"
        assert mp3_params["bitrate"] == MP3_BITRATE
        
        # Opus params
        opus_params = get_format_export_params("opus")
        assert opus_params["format"] == "opus"
        assert opus_params["parameters"] == ["-b:a", str(OPUS_BITRATE)]
        
        # WAV params (no bitrate)
        wav_params = get_format_export_params("wav")
        assert wav_params["format"] == "wav"
        assert "bitrate" not in wav_params
        
        # FLAC params (lossless)
        flac_params = get_format_export_params("flac")
        assert flac_params["format"] == "flac"
        assert "bitrate" not in flac_params
    
    @patch.dict(os.environ, {'VOICEMODE_AUDIO_FORMAT': 'invalid_format'})
    def test_invalid_format_fallback(self):
        """Test that invalid formats fall back to pcm"""
        # Need to reload the module to pick up new env vars
        import importlib
        import voice_mode.config
        importlib.reload(voice_mode.config)
        
        from voice_mode.config import AUDIO_FORMAT
        
        # Should fallback to pcm
        assert AUDIO_FORMAT == "pcm"
    
    def test_format_specific_bitrate_settings(self):
        """Test format-specific quality settings"""
        from voice_mode.config import OPUS_BITRATE, MP3_BITRATE, AAC_BITRATE
        
        # Default values
        assert OPUS_BITRATE == 32000  # 32kbps for voice
        assert MP3_BITRATE == "32k"  # 32kbps optimal for speech (per Whisper research)
        assert AAC_BITRATE == "64k"
    
    @patch.dict(os.environ, {
        'VOICEMODE_OPUS_BITRATE': '48000',
        'VOICEMODE_MP3_BITRATE': '128k'
    })
    def test_custom_bitrate_settings(self):
        """Test custom bitrate configuration"""
        # Need to reload the module to pick up new env vars
        import importlib
        import voice_mode.config
        importlib.reload(voice_mode.config)
        
        from voice_mode.config import OPUS_BITRATE, MP3_BITRATE
        
        assert OPUS_BITRATE == 48000
        assert MP3_BITRATE == "128k"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
