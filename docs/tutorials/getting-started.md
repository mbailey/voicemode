# Getting Started with VoiceMode

VoiceMode brings voice conversations to AI coding assistants. It works as both an MCP server for Claude Code and as a standalone CLI tool.

## What is VoiceMode?

VoiceMode provides:

- **MCP Server**: Adds voice tools to Claude Code - no installation needed
- **CLI Tool**: Use VoiceMode's tools directly from your terminal
- **Local Services**: Optional privacy-focused speech processing

## Quick Start: Using with Claude Code

The fastest way to get started is using VoiceMode with Claude Code.

### Option 1: Universal Installer (Recommended)

The easiest way - installs UV and all dependencies automatically:

```bash
# Install UV package manager (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run the VoiceMode installer
uvx voice-mode-install
```

This installer will:

- Check and install system dependencies (PortAudio, FFmpeg, gcc, etc.)
- Install VoiceMode MCP package via UV
- Configure shell completions for the `voicemode` CLI tool
- Optionally install and configure local STT/TTS services (Whisper, Kokoro)
  - Services are enabled to start automatically on boot
  - Services start immediately after installation
- Validate the installation and provide next steps

### Option 2: Manual Installation

If you already have UV installed and prefer to set up dependencies manually:

```bash
# First install system dependencies (required for building Python extensions):
# macOS
brew install portaudio ffmpeg

# Linux (Debian/Ubuntu)
sudo apt-get install python3-dev gcc libasound2-dev libportaudio2 ffmpeg

# Linux (Fedora/RHEL)
sudo dnf install python3-devel gcc alsa-lib-devel portaudio ffmpeg

# Then install VoiceMode package
uv tool install voice-mode
```

Learn more: [UV Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

### 1. Add VoiceMode to Claude

```bash
claude mcp add --user voicemode -- uvx --refresh voice-mode
```

### 2. Configure Your API Key

Set your OpenAI API key as an environment variable:

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

Or add it to your shell configuration file (`~/.bashrc`, `~/.zshrc`, etc.)

### 3. Verify Installation

```bash
# Check that VoiceMode is connected
claude mcp list
```

You should see `voicemode` in the list of connected servers.

### 4. Start Using Voice

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
voicemode whisper install   # Speech-to-text
voicemode kokoro install    # Text-to-speech

# Start services
voicemode whisper start
voicemode kokoro start
```

VoiceMode will automatically detect and use these local services when available.

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
voicemode whisper status
voicemode kokoro status

# View logs
voicemode logs --tail 50
```

## Next Steps

- **[Configuration Guide](../guides/configuration.md)** - Customize VoiceMode
- **[Development Setup](development-setup.md)** - Contribute to VoiceMode
- **[Service Guides](../guides/)** - Set up Whisper, Kokoro, or LiveKit
- **[CLI Reference](../reference/cli.md)** - All available commands

## Getting Help

- **GitHub Issues**: [github.com/mbailey/voicemode/issues](https://github.com/mbailey/voicemode/issues)
- **Discord**: Join our community for support

Welcome to voice-enabled AI coding! 🎙️
