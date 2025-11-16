---
name: voicemode
description: This skill provides voice interaction capabilities for AI assistants. This skill should be used when users mention voice mode, want to have voice conversations, speak with Claude, check voice service status, or manage voice services like Whisper and Kokoro.
---

# VoiceMode

## Overview

This skill enables natural voice conversations between Claude and users by providing access to VoiceMode's speech-to-text (STT) and text-to-speech (TTS) capabilities. It integrates with both local and cloud-based voice services for flexible, high-quality voice interactions.

## When to Use This Skill

Load this skill when:
- User mentions "voice mode" or "voicemode"
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

### Token Efficiency Note

When using `voicemode converse` via CLI commands, redirect STDERR to `/dev/null` to save tokens by suppressing verbose diagnostic output. This prevents FFmpeg warnings and debug messages from consuming context:

```bash
voicemode converse -m "Hello" 2>/dev/null
```

**Note**: Omit the `2>/dev/null` redirection when debugging issues or troubleshooting audio problems, as STDERR contains useful diagnostic information.

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
# Simple conversation (redirect STDERR to save tokens)
voicemode converse 2>/dev/null

# Speak without waiting
voicemode converse -m "Hello there!" --no-wait 2>/dev/null

# Continuous conversation mode
voicemode converse --continuous 2>/dev/null

# With specific voice
voicemode converse --voice nova 2>/dev/null

# Note: Omit 2>/dev/null for debugging or diagnostics
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

## Communication Guidelines

### Voice Mode Parallel Operations (DEFAULT BEHAVIOR)

When using voice mode, **ALWAYS use the parallel pattern by default**:
- **Speak without waiting** (`wait_for_response=false`) before performing other actions
- **Narrate actions while performing them** - this creates natural conversation flow
- **Execute tools in parallel** - speak and act simultaneously for better responsiveness

Example patterns:

When using MCP tools:
```python
# ALWAYS do this - speak while acting
voicemode:converse("Let me search for that information", wait_for_response=False)
Grep(pattern="search_term", path="/path")  # Runs while speaking
```

When using CLI commands with Bash tool:
```bash
# Run voice announcement and action in parallel (redirect STDERR to save tokens)
voicemode converse -m "Let me check the service status" --no-wait 2>/dev/null &
voicemode whisper service status

# Note: Omit 2>/dev/null for debugging or diagnostics
```

Only wait for response when:
- Asking questions that need answers
- Getting confirmation for important actions
- At natural conversation endpoints

### Asking Questions

When asking questions, especially in voice mode:
- **Ask questions one at a time** - avoid bundling multiple questions
- **Wait for the answer** before proceeding to the next question
- **Keep questions clear and concise** for voice conversations
- This ensures clarity and prevents overwhelming in voice interactions

Example:
```python
# Good - one question at a time
voicemode:converse("What type of voice service would you prefer?", wait_for_response=True)
# Wait for answer...
voicemode:converse("Would you like me to install it now?", wait_for_response=True)

# Avoid - multiple questions at once
# voicemode:converse("What voice do you want, and should I install Whisper, and do you need Kokoro too?")
```

## Tips for Effective Use

1. **Parallel Operations**: Use speak-without-waiting pattern for most actions
2. **Provider Selection**: Let VoiceMode auto-select providers based on availability
3. **Voice Preferences**: Set user preferences in `~/.voicemode` file
4. **Service Management**: Start services before conversations for best performance
5. **Error Handling**: Check service logs if voice interactions fail
6. **Audio Quality**: Use local services (Whisper/Kokoro) for privacy and speed

## Integration Notes

- VoiceMode runs as an MCP server via stdio transport
- Compatible with Claude Code and other MCP clients
- Supports concurrent instances with audio playback management
- Works with tmux and terminal multiplexers