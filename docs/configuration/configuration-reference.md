# Voice Mode Configuration Reference

This is a comprehensive reference of all configuration options available in Voice Mode.

**Note:** Voice Mode automatically creates `~/.voicemode/voicemode.env` on first run with basic settings. You can edit this file to customize your configuration. Environment variables always take precedence over file settings.

## API Keys and Authentication

```bash
# OpenAI API Key (Required for cloud services)
# Used for both TTS and STT services when using OpenAI-compatible endpoints
OPENAI_API_KEY=your-key-here
```

## Text-to-Speech (TTS) Configuration

```bash
# TTS Service Base URLs (comma-separated list)
# Default: http://127.0.0.1:8880/v1,https://api.openai.com/v1
# The system will try URLs in order of preference
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1,https://api.openai.com/v1

# Voice Preferences (comma-separated list)
# Default: af_sky,alloy
# OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
# Kokoro voices: af_sky, af_sarah, af_nicole, af_lilly, af_zara, am_adam, am_michael, bf_emma, bf_isabella
VOICEMODE_VOICES=af_sky,alloy

# TTS Models (comma-separated list)
# Default: gpt-4o-mini-tts,tts-1-hd,tts-1
# OpenAI models: tts-1, tts-1-hd, gpt-4o-mini-tts (emotional)
# Kokoro: uses tts-1 compatibility
VOICEMODE_TTS_MODELS=gpt-4o-mini-tts,tts-1-hd,tts-1
```

## Speech-to-Text (STT) Configuration

```bash
# STT Service Base URLs (comma-separated list)
# Default: https://api.openai.com/v1
# For local Whisper: http://127.0.0.1:2022/v1
VOICEMODE_STT_BASE_URLS=https://api.openai.com/v1

# Whisper Model (for local Whisper)
# Options: tiny, base, small, medium, large, large-v2, large-v3
# Default: large-v2
VOICEMODE_WHISPER_MODEL=large-v2

# Whisper Language
# Default: auto (automatic detection)
# Options: en, es, fr, de, it, pt, ru, zh, ja, ko, etc.
VOICEMODE_WHISPER_LANGUAGE=auto

# Whisper Port
# Default: 2022
VOICEMODE_WHISPER_PORT=2022
```

## LiveKit Configuration

```bash
# LiveKit Server WebSocket URL
# Default: ws://127.0.0.1:7880
# For LiveKit Cloud: wss://your-project.livekit.cloud
LIVEKIT_URL=ws://127.0.0.1:7880

# LiveKit API Credentials
# Default: devkey/secret (for local development)
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

## Audio Configuration

```bash
# Default Audio Format
# Default: pcm
# Supported: pcm, opus, mp3, wav, flac, aac
VOICEMODE_AUDIO_FORMAT=pcm

# TTS Audio Format (overrides default for TTS)
# Default: pcm (optimal for streaming)
VOICEMODE_TTS_AUDIO_FORMAT=pcm

# STT Audio Format (overrides default for STT)
# Default: mp3 (if global is pcm, since OpenAI doesn't support pcm)
VOICEMODE_STT_AUDIO_FORMAT=mp3

# Audio Quality Settings
VOICEMODE_OPUS_BITRATE=32000     # Opus bitrate in bps (default: 32000)
VOICEMODE_MP3_BITRATE=64k        # MP3 bitrate (default: 64k)
VOICEMODE_AAC_BITRATE=64k        # AAC bitrate (default: 64k)
```

## Audio Feedback

```bash
# Enable Audio Feedback (chimes when recording starts/stops)
# Default: true
VOICEMODE_AUDIO_FEEDBACK=true

# Audio Feedback Style (Note: Currently not implemented)
# Default: whisper
# Options: whisper, shout
VOICE_MCP_FEEDBACK_STYLE=whisper

# Skip Text-to-Speech
# Default: false
# When enabled: Skip TTS for faster text-only responses
# Can be overridden per-call with skip_tts parameter in converse()
VOICEMODE_SKIP_TTS=false
```

## Streaming Configuration

```bash
# Enable Streaming Playback
# Default: true
VOICEMODE_STREAMING_ENABLED=true

# Streaming Buffer Settings
VOICEMODE_STREAM_CHUNK_SIZE=4096    # Download chunk size in bytes (default: 4096)
VOICEMODE_STREAM_BUFFER_MS=150      # Initial buffer before playback in ms (default: 150)
VOICEMODE_STREAM_MAX_BUFFER=2.0     # Maximum buffer in seconds (default: 2.0)
```

## Provider Preferences

```bash
# Prefer Local Services
# Default: true
# When enabled, prioritizes local services (Kokoro, Whisper) over cloud
VOICEMODE_PREFER_LOCAL=true

# Always Try Local Services
# Default: true
# Always attempt local providers even if marked unhealthy
VOICEMODE_ALWAYS_TRY_LOCAL=true

# Auto-start Kokoro TTS
# Default: false
# Automatically starts Kokoro TTS service on first use if not running
VOICEMODE_AUTO_START_KOKORO=false

# Simple Failover Mode
# Default: true
# Try each endpoint in order without health checks
VOICEMODE_SIMPLE_FAILOVER=true
```

## Silence Detection / Voice Activity Detection (VAD)

```bash
# Enable Silence Detection
# Default: true
# Automatically stops recording when silence is detected
VOICEMODE_ENABLE_SILENCE_DETECTION=true

# VAD Aggressiveness (0-3)
# Default: 2
# Controls how strictly WebRTC VAD filters out non-speech audio
# 0: Least aggressive filtering - more permissive, may include non-speech sounds
# 1: Slightly stricter filtering
# 2: Balanced filtering - good for most environments (default)
# 3: Most aggressive filtering - very strict, may cut off soft speech
# Use lower values (0-1) in quiet environments, higher values (2-3) in noisy environments
VOICEMODE_VAD_AGGRESSIVENESS=2

# Silence Threshold (milliseconds)
# Default: 1000 (1 second)
# How long to wait after speech stops before ending recording
VOICEMODE_SILENCE_THRESHOLD_MS=1000

# Minimum Recording Duration (seconds)
# Default: 0.5
# Prevents premature cutoff for very short responses
VOICEMODE_MIN_RECORDING_DURATION=0.5

# Initial Silence Grace Period (seconds)
# Default: 4.0
# How long to wait for user to start speaking before timing out
VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD=4.0
```

## Development & Debugging

```bash
# Enable Debug Mode
# Default: false
# When enabled: detailed logging and debug information
# Values: false, true, trace (trace provides detailed function call logging)
VOICEMODE_DEBUG=false

# Save Audio Files
# Default: false
# When enabled: saves audio files to ~/voicemode_audio/
VOICEMODE_SAVE_AUDIO=false

# Save Transcriptions
# Default: false
# When enabled: saves transcriptions alongside audio files
VOICEMODE_SAVE_TRANSCRIPTIONS=false

# Save All (master switch)
# Default: false
# Enables both audio and transcription saving
VOICEMODE_SAVE_ALL=false
```

## Event Logging

```bash
# Enable Event Logging
# Default: true
# Logs voice interaction events in JSONL format for analysis
VOICEMODE_EVENT_LOG_ENABLED=true

# Event Log Directory
# Default: ~/voicemode_logs
VOICEMODE_EVENT_LOG_DIR=/path/to/logs

# Event Log Rotation
# Default: daily
# Currently only 'daily' is supported
VOICEMODE_EVENT_LOG_ROTATION=daily
```

## Service Configuration

```bash
# Kokoro Port
# Default: 8880
VOICEMODE_KOKORO_PORT=8880

# Kokoro Models Directory
# Default: ~/.voicemode/models/kokoro
VOICEMODE_KOKORO_MODELS_DIR=~/.voicemode/models/kokoro

# Kokoro Cache Directory
# Default: ~/.voicemode/cache/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro

# Default Kokoro Voice
# Default: af_sky
VOICEMODE_KOKORO_DEFAULT_VOICE=af_sky

# Service Auto-enable
# Default: true
# Automatically enable services after installation
VOICEMODE_SERVICE_AUTO_ENABLE=true
```

## Directory Structure

```bash
# Base directory for all voicemode data
# Default: ~/.voicemode
VOICEMODE_BASE_DIR=~/.voicemode

# Models directory
# Default: ~/.voicemode/models
VOICEMODE_MODELS_DIR=~/.voicemode/models

# Whisper models path
# Default: ~/.voicemode/models/whisper
VOICEMODE_WHISPER_MODEL_PATH=~/.voicemode/models/whisper
```

## Example Configurations

### Use Kokoro TTS with OpenAI STT
```bash
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1,https://api.openai.com/v1
VOICEMODE_TTS_VOICES=af_sky,af_nova
VOICEMODE_STT_BASE_URLS=https://api.openai.com/v1
OPENAI_API_KEY=your-key-here
```

### Use local Whisper STT with OpenAI TTS
```bash
VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1,https://api.openai.com/v1
VOICEMODE_TTS_BASE_URLS=https://api.openai.com/v1
VOICEMODE_TTS_VOICES=nova,alloy
OPENAI_API_KEY=your-key-here
```

### Use both local services (Kokoro + Whisper)
```bash
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1
VOICEMODE_TTS_VOICES=af_sky,af_nova
VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1
```

### Enable auto-start and local preference
```bash
VOICEMODE_PREFER_LOCAL=true
VOICEMODE_AUTO_START_KOKORO=true
```

### High-quality audio settings
```bash
VOICEMODE_TTS_AUDIO_FORMAT=opus
VOICEMODE_OPUS_BITRATE=64000
VOICEMODE_TTS_MODELS=tts-1-hd
```

### Debug configuration
```bash
VOICEMODE_DEBUG=true
VOICEMODE_SAVE_AUDIO=true
VOICEMODE_EVENT_LOG_ENABLED=true
```