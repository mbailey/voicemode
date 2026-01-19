---
name: voicemode
description: Voice interaction for Claude Code. Use when users mention voice mode, speak, talk, converse, voice status, or voice troubleshooting.
---

## First-Time Setup

If VoiceMode isn't working or MCP fails to connect, run:

```
/voicemode:install
```

After install, reconnect MCP: `/mcp` → select voicemode → "Reconnect" (or restart Claude Code).

---

# VoiceMode

Natural voice conversations with Claude Code using speech-to-text (STT) and text-to-speech (TTS).

**Note:** The Python package is `voice-mode` (hyphen), but the CLI command is `voicemode` (no hyphen).

## When to Use MCP vs CLI

| Task | Use | Why |
|------|-----|-----|
| Voice conversations | MCP `voicemode:converse` | Faster - server already running |
| Service start/stop | MCP `voicemode:service` | Works within Claude Code |
| Installation | CLI `voice-mode-install` | One-time setup |
| Configuration | CLI `voicemode config` | Edit settings directly |
| Diagnostics | CLI `voicemode diag` | Administrative tasks |

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

## Best Practices

1. **Narrate without waiting** - Use `wait_for_response=False` when announcing actions
2. **One question at a time** - Don't bundle multiple questions in voice mode
3. **Check status first** - Verify services are running before starting conversations
4. **Let VoiceMode auto-select** - Don't hardcode providers unless user has preference
5. **First run is slow** - Model downloads happen on first start (2-5 min), then instant

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

## DJ Mode

Background music during VoiceMode sessions with track-level control.

```bash
# Core playback
voicemode dj play /path/to/music.mp3  # Play a file or URL
voicemode dj status                    # What's playing
voicemode dj pause                     # Pause playback
voicemode dj resume                    # Resume playback
voicemode dj stop                      # Stop playback

# Navigation and volume
voicemode dj next                      # Skip to next chapter
voicemode dj prev                      # Go to previous chapter
voicemode dj volume 30                 # Set volume to 30%

# Music For Programming
voicemode dj mfp list                  # List available episodes
voicemode dj mfp play 49               # Play episode 49
voicemode dj mfp sync                  # Convert CUE files to chapters

# Music library
voicemode dj find "daft punk"          # Search library
voicemode dj library scan              # Index ~/Audio/music
voicemode dj library stats             # Show library info

# Play history and favorites
voicemode dj history                   # Show recent plays
voicemode dj favorite                  # Toggle favorite on current track
```

**Configuration:** Set `VOICEMODE_DJ_VOLUME` in `~/.voicemode/voicemode.env` to customize startup volume (default: 50%).

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

# DJ Mode
voicemode dj play <file|url>        # Start playback
voicemode dj status                 # What's playing
voicemode dj next/prev              # Navigate chapters
voicemode dj stop                   # Stop playback
voicemode dj mfp play 49            # Music For Programming
```

## Documentation Index

| Topic | Link |
|-------|------|
| Converse Parameters | [All Parameters](../../docs/reference/converse-parameters.md) |
| Installation | [Getting Started](../../docs/tutorials/getting-started.md) |
| Configuration | [Configuration Guide](../../docs/guides/configuration.md) |
| Claude Code Plugin | [Plugin Guide](../../docs/guides/claude-code-plugin.md) |
| Whisper STT | [Whisper Setup](../../docs/guides/whisper-setup.md) |
| Kokoro TTS | [Kokoro Setup](../../docs/guides/kokoro-setup.md) |
| Pronunciation | [Pronunciation Guide](../../docs/guides/pronunciation.md) |
| Troubleshooting | [Troubleshooting](../../docs/troubleshooting/index.md) |
| CLI Reference | [CLI Docs](../../docs/reference/cli.md) |
| DJ Mode | [Background Music](docs/dj-mode/README.md) |
