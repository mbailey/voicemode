# Getting Started with VoiceMode

VoiceMode brings voice conversations to AI coding assistants. It works as both an MCP server for Claude Code and as a standalone CLI tool.

## What is VoiceMode?

VoiceMode provides:

- **MCP Server**: Adds voice tools to Claude Code - no installation needed
- **CLI Tool**: Use VoiceMode's tools directly from your terminal
- **Local Services**: Optional privacy-focused speech processing

## Quick Start: Using with Claude Code

The fastest way to get started is using VoiceMode with Claude Code.

### Installation

Install UV package manager (if not already installed), then run the VoiceMode installer:

```bash
# Install UV package manager (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install VoiceMode and configure services
uvx voice-mode-install

# Add to Claude Code MCP
claude mcp add --scope user voicemode -- uvx --refresh voice-mode
```

The installer will:

- Install missing system dependencies (FFmpeg, PortAudio, etc.)
- Set up your environment for VoiceMode
- Offer to install local voice services (Whisper STT and Kokoro TTS)

**Alternative UV installation methods:**
- **macOS**: `brew install uv`
- **With pip**: `pip install uv`

Learn more: [UV Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

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
# Install local services (use --yes for non-interactive environments like Claude Code)
voicemode whisper install   # Speech-to-text
voicemode kokoro install    # Text-to-speech

# Start services
voicemode whisper start
voicemode kokoro start
```

VoiceMode will automatically detect and use these local services when available.

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
