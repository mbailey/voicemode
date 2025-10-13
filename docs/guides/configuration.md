# VoiceMode Configuration Guide

VoiceMode provides flexible configuration through environment variables and configuration files, following standard precedence rules while maintaining sensible defaults.

*Note: The python package is called `voice-mode` but 

## Quick Start

VoiceMode works out of the box with minimal configuration:

### Cloud Setup (Easiest)
```bash
# Just need an OpenAI API key
export OPENAI_API_KEY="your-api-key"
```

### Local Setup
```bash
# Run local services (Whisper + Kokoro)
voicemode kokoro start
voicemode whisper start
# VoiceMode auto-detects them!
```

### Hybrid Setup (Recommended)
```bash
# Use local services with cloud fallback
export OPENAI_API_KEY="your-api-key"  # Fallback
# Local services auto-detected when running
```

## Configuration System

### Configuration Precedence

VoiceMode follows standard configuration precedence (highest to lowest):

1. **Environment variables** - Always win
2. **Project config** - `./voicemode.env` in current directory
3. **User config** - `~/.voicemode/voicemode.env`
4. **Auto-discovered services** - Running local services
5. **Built-in defaults** - Sensible fallbacks

### Configuration Files

VoiceMode automatically creates `~/.voicemode/voicemode.env` on first run with basic settings. This file uses shell export format:

```bash
# ~/.voicemode/voicemode.env example
export OPENAI_API_KEY="sk-..."
export VOICEMODE_VOICES="af_sky,nova"
export VOICEMODE_DEBUG=false
```

### MCP Configuration

When used as an MCP server, add to your Claude or other MCP client configuration:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "your-key-here",
        "VOICEMODE_VOICES": "nova,shimmer"
      }
    }
  }
}
```

## Configuration Reference

### API Keys and Authentication

```bash
# OpenAI API Key (for cloud TTS/STT)
OPENAI_API_KEY=sk-...

# LiveKit credentials (for room-based voice)
LIVEKIT_API_KEY=devkey          # Default for local dev
LIVEKIT_API_SECRET=secret        # Default for local dev
```

### Voice Services

#### Text-to-Speech (TTS)

```bash
# TTS Service URLs (comma-separated, tried in order)
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1,https://api.openai.com/v1

# Voice preferences (comma-separated)
# OpenAI: alloy, echo, fable, onyx, nova, shimmer
# Kokoro: af_sky, af_sarah, am_adam, bf_emma, etc.
VOICEMODE_VOICES=af_sky,nova,alloy

# TTS Models (comma-separated)
# OpenAI: tts-1, tts-1-hd, gpt-4o-mini-tts
VOICEMODE_TTS_MODELS=tts-1-hd,tts-1

# Default TTS voice and model
VOICEMODE_TTS_VOICE=nova
VOICEMODE_TTS_MODEL=tts-1-hd

# Speech speed (0.25 to 4.0)
VOICEMODE_TTS_SPEED=1.0
```

#### Speech-to-Text (STT)

```bash
# STT Service URLs
VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1,https://api.openai.com/v1

# Whisper configuration
VOICEMODE_WHISPER_MODEL=large-v2    # Model size
VOICEMODE_WHISPER_LANGUAGE=auto     # Language detection
VOICEMODE_WHISPER_PORT=2022         # Server port
```

### Audio Configuration

```bash
# Audio formats
VOICEMODE_AUDIO_FORMAT=pcm          # Global default
VOICEMODE_TTS_AUDIO_FORMAT=pcm      # TTS-specific
VOICEMODE_STT_AUDIO_FORMAT=mp3      # STT-specific

# Supported formats: pcm, opus, mp3, wav, flac, aac

# Quality settings
VOICEMODE_OPUS_BITRATE=32000        # Opus bitrate (bps)
VOICEMODE_MP3_BITRATE=64k           # MP3 bitrate
VOICEMODE_AAC_BITRATE=64k           # AAC bitrate
VOICEMODE_SAMPLE_RATE=24000         # Sample rate (Hz)
```

### Audio Feedback

```bash
# Chimes when recording starts/stops
VOICEMODE_AUDIO_FEEDBACK=true
VOICEMODE_FEEDBACK_STYLE=whisper    # or "shout"

# Silence around chimes (for Bluetooth)
VOICEMODE_CHIME_PRE_DELAY=1.0   # Seconds before
VOICEMODE_CHIME_POST_DELAY=0.5  # Seconds after
```

### Voice Activity Detection

```bash
# VAD Aggressiveness (0-3)
# 0: Least aggressive (captures more)
# 3: Most aggressive (filters more)
VOICEMODE_VAD_AGGRESSIVENESS=2

# Silence detection
VOICEMODE_SILENCE_THRESHOLD=3.0     # Seconds of silence
VOICEMODE_MIN_RECORDING_TIME=0.5    # Minimum recording
VOICEMODE_MAX_RECORDING_TIME=120.0  # Maximum recording
```

### LiveKit Configuration

```bash
# Server settings
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_PORT=7880

# Room settings
VOICEMODE_LIVEKIT_ROOM_PREFIX=voicemode
VOICEMODE_LIVEKIT_AUTO_CREATE=true
```

### Local Service Paths

```bash
# Kokoro TTS
VOICEMODE_KOKORO_PORT=8880
VOICEMODE_KOKORO_MODELS_DIR=~/Models/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro

# Service directories
VOICEMODE_DATA_DIR=~/.voicemode
VOICEMODE_LOG_DIR=~/.voicemode/logs
VOICEMODE_CACHE_DIR=~/.voicemode/cache
```

### Debugging and Logging

```bash
# Debug mode (verbose logging, saves all files)
VOICEMODE_DEBUG=true

# Logging levels
VOICEMODE_LOG_LEVEL=info           # debug, info, warning, error
VOICEMODE_SAVE_ALL=false           # Save all audio files
VOICEMODE_SAVE_RECORDINGS=false    # Save input recordings
VOICEMODE_SAVE_TTS=false           # Save TTS output

# Event logging
VOICEMODE_EVENT_LOG=false          # Log all events
VOICEMODE_CONVERSATION_LOG=false   # Log conversations
```

### Development Settings

```bash
# Skip TTS for faster development
VOICEMODE_SKIP_TTS=false

# Disable specific features
VOICEMODE_DISABLE_SILENCE_DETECTION=false
VOICEMODE_DISABLE_VAD=false
```

## Voice Preferences System

VoiceMode supports project-specific voice preferences. Create a `.voicemode.env` file in your project root:

```bash
# Project-specific voices for a game
export VOICEMODE_VOICES="onyx,fable"
export VOICEMODE_TTS_SPEED=0.9
```

This allows different projects to have different voice settings without changing global configuration.

## Service Auto-Discovery

VoiceMode automatically discovers running local services:

1. **Whisper STT**: Checks `http://127.0.0.1:2022/v1`
2. **Kokoro TTS**: Checks `http://127.0.0.1:8880/v1`
3. **LiveKit**: Checks `ws://127.0.0.1:7880`

No configuration needed when services run on default ports!

## Configuration Philosophy

VoiceMode balances MCP compliance with user convenience:

- **Host configuration is authoritative** - Environment variables always win
- **Reasonable defaults** - Works without any configuration
- **Progressive disclosure** - Simple configs for basic use, advanced options available
- **File-based convenience** - Edit familiar config files instead of multiple host configs

## Common Configurations

### Privacy-Focused Local Setup
```bash
# No cloud services, everything local
export VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1
export VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1
export VOICEMODE_VOICES=af_sky
```

### High-Quality Cloud Setup
```bash
# Best quality with OpenAI
export OPENAI_API_KEY=sk-...
export VOICEMODE_TTS_MODEL=tts-1-hd
export VOICEMODE_VOICES=nova,alloy
```

## Troubleshooting Configuration

### Check Active Configuration
```bash
# List all configuration keys
voicemode config list

# Get specific settings
voicemode config get VOICEMODE_TTS_VOICE
voicemode config get OPENAI_API_KEY
```

### Configuration Not Working?

1. **Check precedence**: Environment variables override files
2. **Verify syntax**: Use `export VAR=value` format in files
3. **Check permissions**: Ensure config files are readable
4. **Test services**: Verify local services are running
5. **Enable debug**: Set `VOICEMODE_DEBUG=true` for details

### Reset Configuration
```bash
# Backup and recreate default config
mv ~/.voicemode/voicemode.env ~/.voicemode/voicemode.env.backup
# Edit the configuration file to reset
voicemode config edit
```

## Security Considerations

- **Never commit API keys** to version control
- **Use environment variables** for sensitive data in production
- **Restrict file permissions**: `chmod 600 ~/.voicemode/voicemode.env`
- **Rotate keys regularly** if exposed
- **Use local services** for sensitive audio data
