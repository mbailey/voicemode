# Getting Started with VoiceMode

VoiceMode brings voice conversations to Claude Code and other AI coding assistants.

> **Note:** This guide covers using VoiceMode with Claude Code. For other MCP clients (Claude Desktop, Cursor, etc.), see [Other MCP Clients](other-clients.md).

## What is VoiceMode?

VoiceMode provides:

- **MCP Server**: Adds voice tools to Claude Code
- **CLI Tool**: Use VoiceMode's tools directly from your terminal
- **Local Services**: Optional privacy-focused speech processing

## Quick Start

**Requirements:** Computer with microphone and speakers

### Option 1: Claude Code Plugin (Recommended)

The fastest way for Claude Code users to get started:

```bash
# Add the plugin marketplace
claude plugin marketplace add mbailey/plugins

# Install VoiceMode plugin
claude plugin install voicemode@mbailey

# Install dependencies (CLI, Local Voice Services)
/voicemode:install

# Start talking!
/voicemode:converse
```

The plugin includes commands, skills, and hooks that enhance your Claude Code experience.

### Option 2: Install Script

The install script handles dependencies and setup:

```bash
# Run the installer
curl -fsSL https://getvoicemode.com/install.sh | bash

# Add to Claude Code
claude mcp add --scope user voicemode -- uvx --refresh voice-mode

# Optional: Add OpenAI API key as fallback for local services
export OPENAI_API_KEY=your-openai-key

# Start a conversation
claude converse
```

The installer will:

- Install system dependencies (FFmpeg, PortAudio, UV, etc.)
- Install the VoiceMode Python package
- Offer to install local voice services (Whisper STT and Kokoro TTS)

## Verify Installation

Check that VoiceMode is connected:

```bash
claude mcp list
```

You should see `voicemode` in the list of connected servers.

## Start Using Voice

In Claude Code, simply type:
```
converse
```

Speak when you hear the chime, and Claude will respond with voice!

## Alternative: Using as a CLI Tool

If you want to use VoiceMode from the command line:

### Installation

```bash
# Install with pip
uv tool install voice-mode

# Or install from source in editable mode
git clone https://github.com/mbailey/voicemode
cd voicemode
uv tool install -e .
```

### Basic Usage

```bash
# Set your API key
export OPENAI_API_KEY="sk-your-api-key-here"

# Start a voice conversation
voicemode converse
```

## Setting Up Local Services (Optional)

For complete privacy, you can run voice services locally instead of using OpenAI.

### Quick Setup

```bash
# Install local services
voicemode service install whisper   # Speech-to-text
voicemode service install kokoro    # Text-to-speech

# Start services
voicemode service start whisper
voicemode service start kokoro

# Check status of all services
voicemode service status
```

VoiceMode will automatically detect and use these local services when available.

### Enable Auto-Start (Recommended)

To have services start automatically at login:

```bash
# Enable services to start at boot/login
voicemode service enable whisper
voicemode service enable kokoro
```

On macOS, this creates launchd agents. On Linux, it creates systemd user services.

### Download Sizes and Requirements

| Service | Download Size | Disk Space | First Start Time |
|---------|---------------|------------|------------------|
| Whisper (tiny) | ~75MB | ~150MB | 30 seconds |
| Whisper (base) | ~150MB | ~300MB | 1-2 minutes |
| Whisper (small) | ~460MB | ~1GB | 2-3 minutes |
| Kokoro TTS | ~350MB | ~700MB | 2-3 minutes |

**Recommended**: Whisper base + Kokoro = ~500MB download, ~1GB disk space.

### Waiting for Services

After installation, services download models on first start. Wait for them to be ready:

```bash
# Wait for Whisper (port 2022)
while ! nc -z localhost 2022 2>/dev/null; do sleep 2; done
echo "Whisper ready"

# Wait for Kokoro (port 8880)
while ! nc -z localhost 8880 2>/dev/null; do sleep 2; done
echo "Kokoro ready"
```

Learn more: [Whisper Setup Guide](../guides/whisper-setup.md) | [Kokoro Setup Guide](../guides/kokoro-setup.md)

## Configuration

VoiceMode works out of the box with sensible defaults. To customize:

### Select Your Voice

```bash
# OpenAI voices
export VOICEMODE_VOICES="nova,shimmer"

# Or Kokoro voices (if using local TTS)
export VOICEMODE_VOICES="af_sky,am_adam"
```

Available OpenAI voices: alloy, echo, fable, onyx, nova, shimmer

### Project-Specific Settings

Create `.voicemode.env` in your project:

```bash
export VOICEMODE_VOICES="af_nova,nova"
export VOICEMODE_TTS_SPEED=1.2
```

Learn more: [Configuration Guide](../guides/configuration.md)

## Troubleshooting

### Voice Not Working in Claude?

1. **Check MCP connection**:
   ```bash
   claude mcp list
   ```
   
2. **Verify OPENAI_API_KEY** is set in your MCP configuration

3. Add to your MCP config:
   ```json
   "env": {
     "OPENAI_API_KEY": "sk-...",
   }
   ```

### No Audio Input?

```bash
# List audio devices
voicemode diag devices

# Test TTS and STT
voicemode converse
```

### Service Issues?

```bash
# Check service status
voicemode service status           # All services
voicemode service status whisper   # Specific service

# View logs
voicemode service logs whisper -n 50
voicemode service logs kokoro -n 50

# Check if service is responding
voicemode service health whisper
voicemode service health kokoro
```

## Running VoiceMode as a Service (Advanced)

For remote access or persistent operation, run VoiceMode as a background service:

```bash
# Start the VoiceMode HTTP server
voicemode service start voicemode

# Enable auto-start at boot/login
voicemode service enable voicemode

# Check all services
voicemode service status
```

The HTTP server enables remote access from other machines on your network or via secure tunnels.

For security best practices when running remotely, see the [Configuration Guide](../guides/configuration.md#http-server-security).

## Next Steps

- **[Configuration Guide](../guides/configuration.md)** - Customize VoiceMode
- **[Development Setup](development-setup.md)** - Contribute to VoiceMode
- **[Service Guides](../guides/)** - Set up Whisper, Kokoro, or LiveKit
- **[CLI Reference](../reference/cli.md)** - All available commands

## Getting Help

- **GitHub Issues**: [github.com/mbailey/voicemode/issues](https://github.com/mbailey/voicemode/issues)
- **Discord**: Join our community for support

Welcome to voice-enabled AI coding! 🎙️
