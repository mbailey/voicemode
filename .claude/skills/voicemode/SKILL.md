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
Use default converse tool parameters unless there's a good reason not to. Timing parameters (`listen_duration_max`, `listen_duration_min`) use smart defaults with silence detection - don't override unless the user requests it or you see a clear need. Defaults are configurable by the user via `~/.voicemode/voicemode.env`.

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

## Handling Pauses and Wait Requests

When the user asks you to wait or give them time:

**Short pauses (up to 60 seconds):** If the user says something ending with "wait" (e.g., "hang on", "give me a sec", "wait"), VoiceMode automatically pauses for 60 seconds then resumes listening. This is built-in.

**Longer pauses (2+ minutes):** Use `bash sleep N` where N is seconds. For example, if the user says "give me 5 minutes":
```bash
sleep 300  # Wait 5 minutes
```
Then call converse again when the wait is over:
```python
voicemode:converse("Five minutes is up. Ready when you are.")
```

**Configuration:** The short pause duration is configurable via `VOICEMODE_WAIT_DURATION` (default: 60 seconds).

## STT Recovery - Manual Transcription

If Whisper STT fails but the audio was recorded successfully, you can manually transcribe the saved audio file:

```bash
# Transcribe the most recent recording
whisper-cli ~/.voicemode/audio/latest-STT.wav

# Or check if file exists first (safe for inclusion in automation)
if [ -f ~/.voicemode/audio/latest-STT.wav ]; then
  whisper-cli ~/.voicemode/audio/latest-STT.wav
fi
```

**Requirements:**
- Audio saving must be enabled via one of:
  - `VOICEMODE_SAVE_AUDIO=true` in `~/.voicemode/voicemode.env`
  - `VOICEMODE_SAVE_ALL=true` (saves all audio and transcriptions)
  - `VOICEMODE_DEBUG=true` (enables debug mode with audio saving)

**How it works:**
- VoiceMode saves all STT recordings to `~/.voicemode/audio/` with timestamps
- The `latest-STT.wav` symlink always points to the most recent recording
- If the STT API fails, the recording is still saved for manual recovery
- This lets you recover the user's speech without asking them to repeat

**When to use:**
- STT service timeout or connection failure
- Transcription returned empty but user definitely spoke
- Need to verify what was actually said vs. what was transcribed

See also: [Troubleshooting - No Speech Detected](../../docs/troubleshooting/index.md#1-no-speech-detected)

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
| voicemode | 8765 | HTTP/SSE server |

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

## Voice Handoff Between Agents

Transfer voice conversations between Claude Code agents for multi-agent workflows.

**Use cases:**
- Personal assistant routing to project-specific foremen
- Foremen delegating to workers for focused tasks
- Returning control when work is complete

### Quick Reference

```python
# 1. Announce the transfer
voicemode:converse("Transferring you to a project agent.", wait_for_response=False)

# 2. Spawn with voice instructions (mechanism depends on your setup)
spawn_agent(path="/path", prompt="Load voicemode skill, use converse to greet user")

# 3. Go quiet - let new agent take over
```

**Hand-back:**
```python
voicemode:converse("Transferring you back to the assistant.", wait_for_response=False)
# Stop conversing, exit or go idle
```

### Key Principles

1. **Announce transfers**: Always tell the user before transferring
2. **One speaker**: Only one agent should use converse at a time
3. **Distinct voices**: Different voices make handoffs audible
4. **Provide context**: Tell receiving agent why user is being transferred

### Detailed Documentation

See [Call Routing](../../../docs/guides/agents/call-routing/) for comprehensive guides:
- [Handoff Pattern](../../../docs/guides/agents/call-routing/handoff.md) - Complete hand-off and hand-back process
- [Voice Proxy](../../../docs/guides/agents/call-routing/proxy.md) - Relay pattern for agents without voice
- [Call Routing Overview](../../../docs/guides/agents/call-routing/README.md) - All routing patterns

## Sharing Voice Services Over Tailscale

Expose local Whisper (STT) and Kokoro (TTS) to other devices on your Tailnet via HTTPS.

### Why

- Browsers require HTTPS for microphone access (e.g., VoiceMode Connect web app)
- Tailscale serve provides automatic HTTPS with valid Let's Encrypt certificates for `*.ts.net` domains
- Enables using your powerful local machine's GPU from any device on your Tailnet

### Setup

```bash
# Expose TTS (Kokoro on port 8880)
tailscale serve --bg --set-path /v1/audio/speech http://localhost:8880/v1/audio/speech

# Expose STT (Whisper on port 2022)
tailscale serve --bg --set-path /v1/audio/transcriptions http://localhost:2022/v1/audio/transcriptions

# Verify configuration
tailscale serve status

# Reset all serve config
tailscale serve reset
```

### Endpoints

After setup, endpoints are available at:
- **TTS:** `https://<hostname>.<tailnet>.ts.net/v1/audio/speech`
- **STT:** `https://<hostname>.<tailnet>.ts.net/v1/audio/transcriptions`

### Important Notes

- **Path mapping**: Tailscale strips the incoming path before forwarding, so you MUST include the full path in the target URL
- **Same-machine testing**: Traffic doesn't route through Tailscale locally — test from another Tailnet device
- **Multiple paths**: You can configure different paths to different backends on the same or different machines
- **CORS**: Kokoro has CORS configured to allow `https://app.voicemode.dev` origins

### Use with VoiceMode Connect

In the VoiceMode Connect web app settings (app.voicemode.dev/settings), set:
- **TTS Endpoint**: `https://<hostname>.<tailnet>.ts.net`
- **STT Endpoint**: `https://<hostname>.<tailnet>.ts.net`

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

## Related Skills

- **[VoiceMode Connect](../voicemode-connect/SKILL.md)** - Remote voice via mobile/web clients (no local STT/TTS needed)
