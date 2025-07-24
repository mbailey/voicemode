"""MCP resources for voice mode configuration."""

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
    Complete voice mode configuration.
    
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
    lines = []
    lines.append("Voice Mode Configuration")
    lines.append("=" * 80)
    lines.append("")
    
    # Core Settings
    lines.append("Core Settings:")
    lines.append(f"  Base Directory: {BASE_DIR}")
    lines.append(f"  Debug Mode: {DEBUG}")
    lines.append(f"  Save All: {SAVE_ALL}")
    lines.append(f"  Save Audio: {SAVE_AUDIO}")
    lines.append(f"  Save Transcriptions: {SAVE_TRANSCRIPTIONS}")
    lines.append(f"  Audio Feedback: {AUDIO_FEEDBACK_ENABLED}")
    lines.append("")
    
    # Provider Settings
    lines.append("Provider Settings:")
    lines.append(f"  Prefer Local: {PREFER_LOCAL}")
    lines.append(f"  Always Try Local: {ALWAYS_TRY_LOCAL}")
    lines.append(f"  Auto-start Kokoro: {AUTO_START_KOKORO}")
    lines.append(f"  TTS Endpoints: {', '.join(TTS_BASE_URLS)}")
    lines.append(f"  STT Endpoints: {', '.join(STT_BASE_URLS)}")
    lines.append(f"  TTS Voices: {', '.join(TTS_VOICES)}")
    lines.append(f"  TTS Models: {', '.join(TTS_MODELS)}")
    if OPENAI_API_KEY:
        lines.append(f"  OpenAI API Key: {mask_sensitive(OPENAI_API_KEY, 'openai_api_key')}")
    lines.append("")
    
    # Audio Settings
    lines.append("Audio Settings:")
    lines.append(f"  Format: {AUDIO_FORMAT}")
    lines.append(f"  TTS Format: {TTS_AUDIO_FORMAT}")
    lines.append(f"  STT Format: {STT_AUDIO_FORMAT}")
    lines.append(f"  Sample Rate: {SAMPLE_RATE} Hz")
    lines.append(f"  Channels: {CHANNELS}")
    lines.append("")
    
    # Silence Detection
    lines.append("Silence Detection:")
    lines.append(f"  Disabled: {DISABLE_SILENCE_DETECTION}")
    lines.append(f"  VAD Aggressiveness: {VAD_AGGRESSIVENESS}")
    lines.append(f"  Silence Threshold: {SILENCE_THRESHOLD_MS} ms")
    lines.append(f"  Min Recording Duration: {MIN_RECORDING_DURATION} s")
    lines.append(f"  Initial Silence Grace: {INITIAL_SILENCE_GRACE_PERIOD} s")
    lines.append(f"  Default Listen Duration: {DEFAULT_LISTEN_DURATION} s")
    lines.append("")
    
    # Streaming
    lines.append("Streaming:")
    lines.append(f"  Enabled: {STREAMING_ENABLED}")
    lines.append(f"  Chunk Size: {STREAM_CHUNK_SIZE} bytes")
    lines.append(f"  Buffer: {STREAM_BUFFER_MS} ms")
    lines.append(f"  Max Buffer: {STREAM_MAX_BUFFER} s")
    lines.append("")
    
    # Event Logging
    lines.append("Event Logging:")
    lines.append(f"  Enabled: {EVENT_LOG_ENABLED}")
    lines.append(f"  Directory: {EVENT_LOG_DIR}")
    lines.append(f"  Rotation: {EVENT_LOG_ROTATION}")
    lines.append("")
    
    # Whisper
    lines.append("Whisper Configuration:")
    lines.append(f"  Model: {WHISPER_MODEL}")
    lines.append(f"  Port: {WHISPER_PORT}")
    lines.append(f"  Language: {WHISPER_LANGUAGE}")
    lines.append(f"  Model Path: {WHISPER_MODEL_PATH}")
    lines.append(f"  Endpoint: http://127.0.0.1:{WHISPER_PORT}/v1")
    lines.append("")
    
    # Kokoro
    lines.append("Kokoro Configuration:")
    lines.append(f"  Port: {KOKORO_PORT}")
    lines.append(f"  Models Directory: {KOKORO_MODELS_DIR}")
    lines.append(f"  Cache Directory: {KOKORO_CACHE_DIR}")
    lines.append(f"  Default Voice: {KOKORO_DEFAULT_VOICE}")
    lines.append(f"  Endpoint: http://127.0.0.1:{KOKORO_PORT}/v1")
    
    return "\n".join(lines)


@mcp.resource("voice://config/whisper")
async def whisper_configuration() -> str:
    """
    Whisper service configuration.
    
    Shows all Whisper-specific settings including:
    - Model selection
    - Port configuration
    - Language settings
    - Model storage path
    
    These settings control how the local Whisper.cpp service operates.
    """
    lines = []
    lines.append("Whisper Service Configuration")
    lines.append("=" * 40)
    lines.append("")
    
    lines.append("Current Settings:")
    lines.append(f"  Model: {WHISPER_MODEL}")
    lines.append(f"  Port: {WHISPER_PORT}")
    lines.append(f"  Language: {WHISPER_LANGUAGE}")
    lines.append(f"  Model Path: {WHISPER_MODEL_PATH}")
    lines.append(f"  Endpoint: http://127.0.0.1:{WHISPER_PORT}/v1")
    lines.append("")
    
    lines.append("Environment Variables:")
    lines.append(f"  VOICEMODE_WHISPER_MODEL: {os.getenv('VOICEMODE_WHISPER_MODEL', '[not set]')}")
    lines.append(f"  VOICEMODE_WHISPER_PORT: {os.getenv('VOICEMODE_WHISPER_PORT', '[not set]')}")
    lines.append(f"  VOICEMODE_WHISPER_LANGUAGE: {os.getenv('VOICEMODE_WHISPER_LANGUAGE', '[not set]')}")
    lines.append(f"  VOICEMODE_WHISPER_MODEL_PATH: {os.getenv('VOICEMODE_WHISPER_MODEL_PATH', '[not set]')}")
    
    return "\n".join(lines)


@mcp.resource("voice://config/kokoro")
async def kokoro_configuration() -> str:
    """
    Kokoro TTS service configuration.
    
    Shows all Kokoro-specific settings including:
    - Port configuration
    - Models directory
    - Cache directory
    - Default voice selection
    
    These settings control how the local Kokoro TTS service operates.
    """
    lines = []
    lines.append("Kokoro Service Configuration")
    lines.append("=" * 40)
    lines.append("")
    
    lines.append("Current Settings:")
    lines.append(f"  Port: {KOKORO_PORT}")
    lines.append(f"  Models Directory: {KOKORO_MODELS_DIR}")
    lines.append(f"  Cache Directory: {KOKORO_CACHE_DIR}")
    lines.append(f"  Default Voice: {KOKORO_DEFAULT_VOICE}")
    lines.append(f"  Endpoint: http://127.0.0.1:{KOKORO_PORT}/v1")
    lines.append("")
    
    lines.append("Environment Variables:")
    lines.append(f"  VOICEMODE_KOKORO_PORT: {os.getenv('VOICEMODE_KOKORO_PORT', '[not set]')}")
    lines.append(f"  VOICEMODE_KOKORO_MODELS_DIR: {os.getenv('VOICEMODE_KOKORO_MODELS_DIR', '[not set]')}")
    lines.append(f"  VOICEMODE_KOKORO_CACHE_DIR: {os.getenv('VOICEMODE_KOKORO_CACHE_DIR', '[not set]')}")
    lines.append(f"  VOICEMODE_KOKORO_DEFAULT_VOICE: {os.getenv('VOICEMODE_KOKORO_DEFAULT_VOICE', '[not set]')}")
    
    return "\n".join(lines)


def parse_env_file(file_path: Path) -> Dict[str, str]:
    """Parse an environment file and return a dictionary of key-value pairs."""
    config = {}
    if not file_path.exists():
        return config
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    config[key] = value
    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
    
    return config


@mcp.resource("voice://config/env-vars")
async def environment_variables() -> str:
    """
    All voice mode environment variables with current values.
    
    Shows each configuration variable with:
    - Name: The environment variable name
    - Environment Value: Current value from environment
    - Config File Value: Value from ~/.voicemode.env (if exists)
    - Description: What the variable controls
    
    This helps identify configuration sources and troubleshoot settings.
    """
    # Parse config file
    user_config_path = Path.home() / ".voicemode.env"
    file_config = parse_env_file(user_config_path)
    
    # Define all configuration variables with descriptions
    config_vars = [
        # Core Settings
        ("VOICEMODE_BASE_DIR", "Base directory for all voicemode data"),
        ("VOICEMODE_DEBUG", "Enable debug mode (true/false)"),
        ("VOICEMODE_SAVE_ALL", "Save all audio and transcriptions (true/false)"),
        ("VOICEMODE_SAVE_AUDIO", "Save audio files (true/false)"),
        ("VOICEMODE_SAVE_TRANSCRIPTIONS", "Save transcription files (true/false)"),
        ("VOICEMODE_AUDIO_FEEDBACK", "Enable audio feedback (true/false)"),
        # Provider Settings
        ("VOICEMODE_PREFER_LOCAL", "Prefer local providers over cloud (true/false)"),
        ("VOICEMODE_ALWAYS_TRY_LOCAL", "Always attempt local providers (true/false)"),
        ("VOICEMODE_AUTO_START_KOKORO", "Auto-start Kokoro service (true/false)"),
        ("VOICEMODE_TTS_BASE_URLS", "Comma-separated list of TTS endpoints"),
        ("VOICEMODE_STT_BASE_URLS", "Comma-separated list of STT endpoints"),
        ("VOICEMODE_TTS_VOICES", "Comma-separated list of preferred voices"),
        ("VOICEMODE_TTS_MODELS", "Comma-separated list of preferred models"),
        # Audio Settings
        ("VOICEMODE_AUDIO_FORMAT", "Audio format for recording (pcm/mp3/wav/flac/aac/opus)"),
        ("VOICEMODE_TTS_AUDIO_FORMAT", "Audio format for TTS output"),
        ("VOICEMODE_STT_AUDIO_FORMAT", "Audio format for STT input"),
        # Whisper Configuration
        ("VOICEMODE_WHISPER_MODEL", "Whisper model to use (e.g., large-v2)"),
        ("VOICEMODE_WHISPER_PORT", "Whisper server port"),
        ("VOICEMODE_WHISPER_LANGUAGE", "Language for transcription"),
        ("VOICEMODE_WHISPER_MODEL_PATH", "Path to Whisper models"),
        # Kokoro Configuration
        ("VOICEMODE_KOKORO_PORT", "Kokoro server port"),
        ("VOICEMODE_KOKORO_MODELS_DIR", "Directory for Kokoro models"),
        ("VOICEMODE_KOKORO_CACHE_DIR", "Directory for Kokoro cache"),
        ("VOICEMODE_KOKORO_DEFAULT_VOICE", "Default Kokoro voice"),
        # Silence Detection
        ("VOICEMODE_DISABLE_SILENCE_DETECTION", "Disable silence detection (true/false)"),
        ("VOICEMODE_VAD_AGGRESSIVENESS", "Voice activity detection aggressiveness (0-3)"),
        ("VOICEMODE_SILENCE_THRESHOLD_MS", "Silence threshold in milliseconds"),
        ("VOICEMODE_MIN_RECORDING_DURATION", "Minimum recording duration in seconds"),
        ("VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD", "Initial silence grace period in seconds"),
        ("VOICEMODE_DEFAULT_LISTEN_DURATION", "Default listen duration in seconds"),
        # Streaming
        ("VOICEMODE_STREAMING_ENABLED", "Enable audio streaming (true/false)"),
        ("VOICEMODE_STREAM_CHUNK_SIZE", "Stream chunk size in bytes"),
        ("VOICEMODE_STREAM_BUFFER_MS", "Stream buffer in milliseconds"),
        ("VOICEMODE_STREAM_MAX_BUFFER", "Maximum stream buffer in seconds"),
        # Event Logging
        ("VOICEMODE_EVENT_LOG_ENABLED", "Enable event logging (true/false)"),
        ("VOICEMODE_EVENT_LOG_DIR", "Directory for event logs"),
        ("VOICEMODE_EVENT_LOG_ROTATION", "Log rotation policy (daily/weekly/monthly)"),
        # API Keys
        ("OPENAI_API_KEY", "OpenAI API key for cloud TTS/STT"),
    ]
    
    result = []
    result.append("Voice Mode Environment Variables")
    result.append("=" * 80)
    result.append("")
    
    for var_name, description in config_vars:
        env_value = os.getenv(var_name)
        config_value = file_config.get(var_name)
        
        # Mask sensitive values
        if 'KEY' in var_name or 'SECRET' in var_name:
            if env_value:
                env_value = mask_sensitive(env_value, var_name)
            if config_value:
                config_value = mask_sensitive(config_value, var_name)
        
        result.append(f"{var_name}")
        result.append(f"  Environment: {env_value or '[not set]'}")
        result.append(f"  Config File: {config_value or '[not set]'}")
        result.append(f"  Description: {description}")
        result.append("")
    
    return "\n".join(result)


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