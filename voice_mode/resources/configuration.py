"""MCP resources for voice mode configuration."""

import json
import os
from typing import Dict, Any
from pathlib import Path

from ..server import mcp
from ..config import (
    logger,
    # Core settings
    BASE_DIR, DEBUG, SAVE_ALL, SAVE_AUDIO, SAVE_TRANSCRIPTIONS,
    AUDIO_FEEDBACK_ENABLED, PREFER_LOCAL, ALWAYS_TRY_LOCAL, AUTO_START_KOKORO,
    # Service settings
    OPENAI_API_KEY, TTS_BASE_URLS, STT_BASE_URLS, TTS_VOICES, TTS_MODELS,
    # Whisper settings
    WHISPER_MODEL, WHISPER_PORT, WHISPER_LANGUAGE, WHISPER_MODEL_PATH,
    # Kokoro settings
    KOKORO_PORT, KOKORO_MODELS_DIR, KOKORO_CACHE_DIR, KOKORO_DEFAULT_VOICE,
    # Audio settings
    AUDIO_FORMAT, TTS_AUDIO_FORMAT, STT_AUDIO_FORMAT,
    SAMPLE_RATE, CHANNELS,
    # Silence detection
    DISABLE_SILENCE_DETECTION, VAD_AGGRESSIVENESS, SILENCE_THRESHOLD_MS,
    MIN_RECORDING_DURATION, INITIAL_SILENCE_GRACE_PERIOD, DEFAULT_LISTEN_DURATION,
    # Streaming
    STREAMING_ENABLED, STREAM_CHUNK_SIZE, STREAM_BUFFER_MS, STREAM_MAX_BUFFER,
    # Event logging
    EVENT_LOG_ENABLED, EVENT_LOG_DIR, EVENT_LOG_ROTATION
)


def mask_sensitive(value: Any, key: str) -> Any:
    """Mask sensitive values like API keys."""
    if key.lower().endswith('_key') or key.lower().endswith('_secret'):
        if value and isinstance(value, str):
            return f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
    return value


@mcp.resource("voice://config/all")
async def all_configuration() -> str:
    """
    Complete voice mode configuration in JSON format.
    
    Shows all current configuration settings including:
    - Core settings (directories, saving options)
    - Provider settings (TTS/STT endpoints and preferences)
    - Audio settings (formats, quality)
    - Service-specific settings (Whisper, Kokoro)
    - Silence detection parameters
    - Streaming configuration
    - Event logging settings
    
    Sensitive values like API keys are masked for security.
    """
    config = {
        "core": {
            "base_dir": str(BASE_DIR),
            "debug": DEBUG,
            "save_all": SAVE_ALL,
            "save_audio": SAVE_AUDIO,
            "save_transcriptions": SAVE_TRANSCRIPTIONS,
            "audio_feedback": AUDIO_FEEDBACK_ENABLED
        },
        "providers": {
            "prefer_local": PREFER_LOCAL,
            "always_try_local": ALWAYS_TRY_LOCAL,
            "auto_start_kokoro": AUTO_START_KOKORO,
            "tts_endpoints": TTS_BASE_URLS,
            "stt_endpoints": STT_BASE_URLS,
            "tts_voices": TTS_VOICES,
            "tts_models": TTS_MODELS,
            "openai_api_key": mask_sensitive(OPENAI_API_KEY, "openai_api_key")
        },
        "audio": {
            "format": AUDIO_FORMAT,
            "tts_format": TTS_AUDIO_FORMAT,
            "stt_format": STT_AUDIO_FORMAT,
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS
        },
        "silence_detection": {
            "disabled": DISABLE_SILENCE_DETECTION,
            "vad_aggressiveness": VAD_AGGRESSIVENESS,
            "silence_threshold_ms": SILENCE_THRESHOLD_MS,
            "min_recording_duration": MIN_RECORDING_DURATION,
            "initial_silence_grace": INITIAL_SILENCE_GRACE_PERIOD,
            "default_listen_duration": DEFAULT_LISTEN_DURATION
        },
        "streaming": {
            "enabled": STREAMING_ENABLED,
            "chunk_size": STREAM_CHUNK_SIZE,
            "buffer_ms": STREAM_BUFFER_MS,
            "max_buffer_seconds": STREAM_MAX_BUFFER
        },
        "event_logging": {
            "enabled": EVENT_LOG_ENABLED,
            "directory": EVENT_LOG_DIR,
            "rotation": EVENT_LOG_ROTATION
        },
        "whisper": {
            "model": WHISPER_MODEL,
            "port": WHISPER_PORT,
            "language": WHISPER_LANGUAGE,
            "model_path": WHISPER_MODEL_PATH
        },
        "kokoro": {
            "port": KOKORO_PORT,
            "models_dir": KOKORO_MODELS_DIR,
            "cache_dir": KOKORO_CACHE_DIR,
            "default_voice": KOKORO_DEFAULT_VOICE
        }
    }
    
    return json.dumps(config, indent=2)


@mcp.resource("voice://config/whisper")
async def whisper_configuration() -> str:
    """
    Whisper service configuration in JSON format.
    
    Shows all Whisper-specific settings including:
    - Model selection
    - Port configuration
    - Language settings
    - Model storage path
    
    These settings control how the local Whisper.cpp service operates.
    """
    config = {
        "service": "whisper",
        "configuration": {
            "model": WHISPER_MODEL,
            "port": WHISPER_PORT,
            "language": WHISPER_LANGUAGE,
            "model_path": WHISPER_MODEL_PATH,
            "endpoint": f"http://127.0.0.1:{WHISPER_PORT}/v1"
        },
        "environment_variables": {
            "VOICEMODE_WHISPER_MODEL": os.getenv("VOICEMODE_WHISPER_MODEL", "[not set]"),
            "VOICEMODE_WHISPER_PORT": os.getenv("VOICEMODE_WHISPER_PORT", "[not set]"),
            "VOICEMODE_WHISPER_LANGUAGE": os.getenv("VOICEMODE_WHISPER_LANGUAGE", "[not set]"),
            "VOICEMODE_WHISPER_MODEL_PATH": os.getenv("VOICEMODE_WHISPER_MODEL_PATH", "[not set]")
        }
    }
    
    return json.dumps(config, indent=2)


@mcp.resource("voice://config/kokoro")
async def kokoro_configuration() -> str:
    """
    Kokoro TTS service configuration in JSON format.
    
    Shows all Kokoro-specific settings including:
    - Port configuration
    - Models directory
    - Cache directory
    - Default voice selection
    
    These settings control how the local Kokoro TTS service operates.
    """
    config = {
        "service": "kokoro",
        "configuration": {
            "port": KOKORO_PORT,
            "models_dir": KOKORO_MODELS_DIR,
            "cache_dir": KOKORO_CACHE_DIR,
            "default_voice": KOKORO_DEFAULT_VOICE,
            "endpoint": f"http://127.0.0.1:{KOKORO_PORT}/v1"
        },
        "environment_variables": {
            "VOICEMODE_KOKORO_PORT": os.getenv("VOICEMODE_KOKORO_PORT", "[not set]"),
            "VOICEMODE_KOKORO_MODELS_DIR": os.getenv("VOICEMODE_KOKORO_MODELS_DIR", "[not set]"),
            "VOICEMODE_KOKORO_CACHE_DIR": os.getenv("VOICEMODE_KOKORO_CACHE_DIR", "[not set]"),
            "VOICEMODE_KOKORO_DEFAULT_VOICE": os.getenv("VOICEMODE_KOKORO_DEFAULT_VOICE", "[not set]")
        }
    }
    
    return json.dumps(config, indent=2)


@mcp.resource("voice://config/env-template")
async def environment_template() -> str:
    """
    Environment variable template for voice mode configuration.
    
    Provides a ready-to-use template of all available environment variables
    with their current values. This can be saved to ~/.voicemode.env and
    customized as needed.
    
    Sensitive values like API keys are masked for security.
    """
    template_lines = [
        "#!/usr/bin/env bash",
        "# Voice Mode Environment Configuration",
        "# Generated from current settings",
        "",
        "# Core Settings",
        f"export VOICEMODE_BASE_DIR=\"{BASE_DIR}\"",
        f"export VOICEMODE_DEBUG=\"{str(DEBUG).lower()}\"",
        f"export VOICEMODE_SAVE_ALL=\"{str(SAVE_ALL).lower()}\"",
        f"export VOICEMODE_SAVE_AUDIO=\"{str(SAVE_AUDIO).lower()}\"",
        f"export VOICEMODE_SAVE_TRANSCRIPTIONS=\"{str(SAVE_TRANSCRIPTIONS).lower()}\"",
        f"export VOICEMODE_AUDIO_FEEDBACK=\"{str(AUDIO_FEEDBACK_ENABLED).lower()}\"",
        "",
        "# Provider Settings",
        f"export VOICEMODE_PREFER_LOCAL=\"{str(PREFER_LOCAL).lower()}\"",
        f"export VOICEMODE_ALWAYS_TRY_LOCAL=\"{str(ALWAYS_TRY_LOCAL).lower()}\"",
        f"export VOICEMODE_AUTO_START_KOKORO=\"{str(AUTO_START_KOKORO).lower()}\"",
        f"export VOICEMODE_TTS_BASE_URLS=\"{','.join(TTS_BASE_URLS)}\"",
        f"export VOICEMODE_STT_BASE_URLS=\"{','.join(STT_BASE_URLS)}\"",
        f"export VOICEMODE_TTS_VOICES=\"{','.join(TTS_VOICES)}\"",
        f"export VOICEMODE_TTS_MODELS=\"{','.join(TTS_MODELS)}\"",
        "",
        "# Audio Settings",
        f"export VOICEMODE_AUDIO_FORMAT=\"{AUDIO_FORMAT}\"",
        f"export VOICEMODE_TTS_AUDIO_FORMAT=\"{TTS_AUDIO_FORMAT}\"",
        f"export VOICEMODE_STT_AUDIO_FORMAT=\"{STT_AUDIO_FORMAT}\"",
        "",
        "# Whisper Configuration",
        f"export VOICEMODE_WHISPER_MODEL=\"{WHISPER_MODEL}\"",
        f"export VOICEMODE_WHISPER_PORT=\"{WHISPER_PORT}\"",
        f"export VOICEMODE_WHISPER_LANGUAGE=\"{WHISPER_LANGUAGE}\"",
        f"export VOICEMODE_WHISPER_MODEL_PATH=\"{WHISPER_MODEL_PATH}\"",
        "",
        "# Kokoro Configuration",
        f"export VOICEMODE_KOKORO_PORT=\"{KOKORO_PORT}\"",
        f"export VOICEMODE_KOKORO_MODELS_DIR=\"{KOKORO_MODELS_DIR}\"",
        f"export VOICEMODE_KOKORO_CACHE_DIR=\"{KOKORO_CACHE_DIR}\"",
        f"export VOICEMODE_KOKORO_DEFAULT_VOICE=\"{KOKORO_DEFAULT_VOICE}\"",
        "",
        "# Silence Detection",
        f"export VOICEMODE_DISABLE_SILENCE_DETECTION=\"{str(DISABLE_SILENCE_DETECTION).lower()}\"",
        f"export VOICEMODE_VAD_AGGRESSIVENESS=\"{VAD_AGGRESSIVENESS}\"",
        f"export VOICEMODE_SILENCE_THRESHOLD_MS=\"{SILENCE_THRESHOLD_MS}\"",
        f"export VOICEMODE_MIN_RECORDING_DURATION=\"{MIN_RECORDING_DURATION}\"",
        f"export VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD=\"{INITIAL_SILENCE_GRACE_PERIOD}\"",
        f"export VOICEMODE_DEFAULT_LISTEN_DURATION=\"{DEFAULT_LISTEN_DURATION}\"",
        "",
        "# Streaming",
        f"export VOICEMODE_STREAMING_ENABLED=\"{str(STREAMING_ENABLED).lower()}\"",
        f"export VOICEMODE_STREAM_CHUNK_SIZE=\"{STREAM_CHUNK_SIZE}\"",
        f"export VOICEMODE_STREAM_BUFFER_MS=\"{STREAM_BUFFER_MS}\"",
        f"export VOICEMODE_STREAM_MAX_BUFFER=\"{STREAM_MAX_BUFFER}\"",
        "",
        "# Event Logging",
        f"export VOICEMODE_EVENT_LOG_ENABLED=\"{str(EVENT_LOG_ENABLED).lower()}\"",
        f"export VOICEMODE_EVENT_LOG_DIR=\"{EVENT_LOG_DIR}\"",
        f"export VOICEMODE_EVENT_LOG_ROTATION=\"{EVENT_LOG_ROTATION}\"",
        "",
        "# API Keys (masked for security)",
        f"# export OPENAI_API_KEY=\"{mask_sensitive(OPENAI_API_KEY, 'api_key')}\"",
    ]
    
    return "\n".join(template_lines)