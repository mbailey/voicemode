---
name: voicemode
description: This skill provides voice interaction capabilities for AI assistants. This skill should be used when users want to have voice conversations, speak with Claude, check voice service status, or manage voice services like Whisper and Kokoro.
---

# VoiceMode

## Overview

This skill enables natural voice conversations between Claude and users by providing access to VoiceMode's speech-to-text (STT) and text-to-speech (TTS) capabilities. It integrates with both local and cloud-based voice services for flexible, high-quality voice interactions.

## When to Use This Skill

Load this skill when:
- User says "converse", "speak to me", "talk to me", or similar phrases
- User wants to start or continue a voice conversation
- User needs to check voice service status (Whisper, Kokoro, LiveKit)
- User wants to manage voice services (start, stop, restart)
- User needs voice configuration or troubleshooting help
- User mentions voice-related issues or preferences

## Core Capabilities

### 1. Voice Conversations

Start natural voice conversations using the converse tool:

```python
# Basic conversation
voicemode:converse(message="Hello! How can I help you today?")

# With specific settings
voicemode:converse(
    message="Let me help you with that",
    voice="nova",  # TTS voice selection
    wait_for_response=True,  # Listen for user response
    listen_duration_max=60  # Maximum listening time
)
```

**Key Parameters:**
- `message`: Text to speak
- `wait_for_response`: Whether to listen for response (default: true)
- `voice`: TTS voice name (auto-selected if not specified)
- `tts_provider`: Provider selection ("openai" or "kokoro")
- `listen_duration_max`: Max listening time in seconds (default: 120)
- `disable_silence_detection`: Disable auto-stop on silence

### 2. Service Management

Manage voice services using the service tool:

```python
# Check service status
voicemode:service(service_name="whisper", action="status")
voicemode:service(service_name="kokoro", action="status")

# Start/stop services
voicemode:service(service_name="whisper", action="start")
voicemode:service(service_name="kokoro", action="stop")

# View service logs
voicemode:service(service_name="whisper", action="logs", lines=100)
```

**Supported Services:**
- `whisper`: Local STT using Whisper.cpp
- `kokoro`: Local TTS with multiple voices
- `livekit`: Room-based real-time communication

**Actions:**
- `status`: Check if service is running
- `start`: Start the service
- `stop`: Stop the service
- `restart`: Restart the service
- `logs`: View recent logs
- `enable`: Start at boot/login
- `disable`: Remove from startup

### 3. Voice Configuration

VoiceMode supports multiple configuration methods:

**Environment Variables:**
- `VOICEMODE_TTS_VOICE`: Default TTS voice
- `VOICEMODE_TTS_PROVIDER`: Default TTS provider
- `VOICEMODE_STT_PROVIDER`: Default STT provider
- `VOICEMODE_AUDIO_FORMAT`: Audio format (wav, mp3, etc.)

**Voice Preferences:**
- Project-level: `.voicemode` file in project root
- User-level: `~/.voicemode` file in home directory

**Configuration Files:**
- Main config: `~/.voicemode/config/config.yaml`
- Pronunciation: `~/.voicemode/config/pronunciation.yaml`

## Voice Service Architecture

### Provider System
VoiceMode uses OpenAI-compatible endpoints for all services:
- Automatic discovery of available services
- Health checking and failover support
- Transparent switching between providers

### Available Providers

**Cloud Services (requires API key):**
- OpenAI API: High-quality TTS/STT

**Local Services (no API key needed):**
- Whisper.cpp: Fast local STT
- Kokoro: Local TTS with multiple voices
- LiveKit: WebRTC-based communication

### Audio Processing
- Requires FFmpeg for audio format conversion
- Supports PCM, MP3, WAV, FLAC, AAC, Opus formats
- WebRTC VAD for voice activity detection
- Automatic format negotiation based on provider

## Common Workflows

### Starting a Voice Conversation

When using MCP tools:
```python
# Simple start
voicemode:converse("Hello! What would you like to discuss today?")

# With specific voice
voicemode:converse(
    message="Let's begin our conversation",
    voice="echo",  # or "alloy", "nova", etc.
    tts_provider="openai"
)
```

When using CLI directly:
```bash
# Simple conversation
voicemode converse

# Speak without waiting
voicemode converse -m "Hello there!" --no-wait

# Continuous conversation mode
voicemode converse --continuous

# With specific voice
voicemode converse --voice nova
```

### Checking Voice Setup

When using MCP tools:
```python
# Check all services
voicemode:service("whisper", "status")
voicemode:service("kokoro", "status")
```

When using CLI directly:
```bash
# Check service status
voicemode whisper service status
voicemode kokoro status
voicemode livekit status

# Check dependencies
voicemode deps

# Diagnostic commands
voicemode diag info
voicemode diag devices
voicemode diag registry
```

### Managing Services

```bash
# Whisper service management
voicemode whisper service start
voicemode whisper service stop
voicemode whisper service restart
voicemode whisper service logs

# Kokoro service management
voicemode kokoro start
voicemode kokoro stop
voicemode kokoro restart
voicemode kokoro logs

# LiveKit service management
voicemode livekit start
voicemode livekit stop
voicemode livekit restart
```

### Configuration Management

```bash
# Edit configuration file
voicemode config edit

# View configuration
voicemode config list
voicemode config get VOICEMODE_TTS_VOICE

# Set configuration
voicemode config set VOICEMODE_TTS_VOICE nova
```

## Installation and Setup

### Quick Install
```bash
# Install VoiceMode package
curl -sL https://voicemode.ai/install.sh | bash

# Or with UV
uv tool install voice-mode-install
voice-mode-install

# Update to latest version
voicemode update
```

### Service Installation

Using CLI commands:
```bash
# Install Whisper for local STT
voicemode whisper service install

# Install Kokoro for local TTS
voicemode kokoro install

# Install LiveKit for room-based communication
voicemode livekit install

# Both services auto-start after installation
```

## Documentation References

For detailed information, reference these docs:
- `docs/reference/`: API and parameter documentation
- `docs/tutorials/`: Step-by-step guides
- `docs/services/`: Service-specific documentation
- `CLAUDE.md`: Project-specific Claude guidance
- `README.md`: Installation and general usage

## Logging and Debugging

VoiceMode maintains comprehensive logs in `~/.voicemode/`:
- `logs/conversations/`: Daily conversation logs
- `logs/events/`: Detailed operational events
- `audio/`: Saved audio recordings
- `config/`: User configuration files

To enable debug logging, set `VOICEMODE_DEBUG=true` or use `--debug` flag.

## Tips for Effective Use

1. **Provider Selection**: Let VoiceMode auto-select providers based on availability
2. **Voice Preferences**: Set user preferences in `~/.voicemode` file
3. **Service Management**: Start services before conversations for best performance
4. **Error Handling**: Check service logs if voice interactions fail
5. **Audio Quality**: Use local services (Whisper/Kokoro) for privacy and speed

## Integration Notes

- VoiceMode runs as an MCP server via stdio transport
- Compatible with Claude Code and other MCP clients
- Supports concurrent instances with audio playback management
- Works with tmux and terminal multiplexers