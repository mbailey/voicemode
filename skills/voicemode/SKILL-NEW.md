---
name: voicemode
description: Voice interaction for Claude Code. Use when users mention voice mode, speak, talk, converse, voice status, or voice troubleshooting.
---

# VoiceMode

Natural voice conversations with Claude Code using speech-to-text (STT) and text-to-speech (TTS).

**Note:** The Python package is `voice-mode` (hyphen), but the CLI command is `voicemode` (no hyphen).

## Usage

Use the `converse` MCP tool to speak to users and hear their responses:

```python
# Speak and listen for response (most common usage)
voicemode:converse("Hello! What would you like to work on?")

# Speak without waiting (for narration while working)
voicemode:converse("Searching the codebase now...", wait_for_response=False)
```

For most conversations, just pass your message - defaults handle everything else.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `message` | required | Text to speak |
| `wait_for_response` | true | Listen after speaking |
| `voice` | auto | TTS voice |

For all parameters, see [Converse Parameters](../../docs/reference/converse-parameters.md).

## Check Status

```bash
voicemode service status          # All services
voicemode service status whisper  # Specific service
```

Shows service status including running state, ports, and health.

## Installation

```bash
# Install VoiceMode CLI and configure services
uvx voice-mode-install --yes

# Install local services (Apple Silicon recommended)
voicemode service install whisper
voicemode service install kokoro
```

See [Getting Started](../../docs/tutorials/getting-started.md) for detailed steps.

## Service Management

```python
# Start/stop services
voicemode:service("whisper", "start")
voicemode:service("kokoro", "start")

# View logs for troubleshooting
voicemode:service("whisper", "logs", lines=50)
```

| Service | Port | Purpose |
|---------|------|---------|
| whisper | 2022 | Speech-to-text |
| kokoro | 8880 | Text-to-speech |
| livekit | 7880 | Real-time rooms |

**Actions:** status, start, stop, restart, logs, enable, disable

## Configuration

```bash
voicemode config list                           # Show all settings
voicemode config set VOICEMODE_TTS_VOICE nova   # Set default voice
voicemode config edit                           # Edit config file
```

Config file: `~/.voicemode/voicemode.env`

See [Configuration Guide](../../docs/guides/configuration.md) for all options.

## CLI Cheat Sheet

```bash
# Service management
voicemode service status            # All services
voicemode service start whisper     # Start a service
voicemode service logs kokoro       # View logs

# Diagnostics
voicemode deps                      # Check dependencies
voicemode diag info                 # System info
voicemode diag devices              # Audio devices

# History search
voicemode history search "keyword"
voicemode history play <exchange_id>
```

## Documentation Index

| Topic | Link |
|-------|------|
| Converse Parameters | [All Parameters](../../docs/reference/converse-parameters.md) |
| Installation | [Getting Started](../../docs/tutorials/getting-started.md) |
| Configuration | [Configuration Guide](../../docs/guides/configuration.md) |
| Whisper STT | [Whisper Setup](../../docs/guides/whisper-setup.md) |
| Kokoro TTS | [Kokoro Setup](../../docs/guides/kokoro-setup.md) |
| Pronunciation | [Pronunciation Guide](../../docs/guides/pronunciation.md) |
| Troubleshooting | [Troubleshooting](../../docs/troubleshooting/index.md) |
| CLI Reference | [CLI Docs](../../docs/reference/cli.md) |
