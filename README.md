# VoiceMode

> Natural voice conversations with Claude Code (and other MCP capable agents)

[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode)](https://pepy.tech/project/voice-mode)
[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode/month)](https://pepy.tech/project/voice-mode)
[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode/week)](https://pepy.tech/project/voice-mode)

VoiceMode enables natural voice conversations with Claude Code. Voice isn't about replacing typing - it's about being available when typing isn't.

**Perfect for:**

- Walking to your next meeting
- Cooking while debugging
- Giving your eyes a break after hours of screen time
- Holding a coffee (or a dog)
- Any moment when your hands or eyes are busy

## See It In Action

[![VoiceMode Demo](https://img.youtube.com/vi/cYdwOD_-dQc/maxresdefault.jpg)](https://www.youtube.com/watch?v=cYdwOD_-dQc)

## Quick Start

**Requirements:** Computer with microphone and speakers

### Option 1: Claude Code Plugin (Recommended)

The fastest way for Claude Code users to get started:

```bash
# Add the VoiceMode marketplace
claude plugin marketplace add mbailey/voicemode

# Install VoiceMode plugin
claude plugin install voicemode@voicemode

## Install dependencies (CLI, Local Voice Services)

/voicemode:install

# Start talking!
/voicemode:converse
```

### Option 2: Python installer package

Installs dependencies and the VoiceMode Python package.

```bash
# Install UV package manager (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run the installer (sets up dependencies and local voice services)
uvx voice-mode-install

# Add to Claude Code
claude mcp add --scope user voicemode -- uvx --refresh voice-mode

# Optional: Add OpenAI API key as fallback for local services
export OPENAI_API_KEY=your-openai-key

# Start a conversation
claude converse
```

For manual setup, see the [Getting Started Guide](docs/tutorials/getting-started.md).

## Features

- **Natural conversations** - speak naturally, hear responses immediately
- **Works offline** - optional local voice services (Whisper STT, Kokoro TTS)
- **Low latency** - fast enough to feel like a real conversation
- **Smart silence detection** - stops recording when you stop speaking
- **Privacy options** - run entirely locally or use cloud services

## Compatibility

**Platforms:** Linux, macOS, Windows (WSL), NixOS
**Python:** 3.10-3.14

## Configuration

VoiceMode works out of the box. For customization:

```bash
# Set OpenAI API key (if using cloud services)
export OPENAI_API_KEY="your-key"

# Or configure via file
voicemode config edit
```

See the [Configuration Guide](docs/guides/configuration.md) for all options.

## Remote Agent (Operator)

VoiceMode includes agent management for running headless Claude Code instances that can be woken remotely from the iOS app or web interface.

### Quick Start

```bash
# Start the operator agent in a tmux session
voicemode agent start

# Check if it's running
voicemode agent status

# Send a message to the operator
voicemode agent send "Hello, please check my calendar"

# Stop the operator
voicemode agent stop
```

### The Operator Concept

The **operator** is a headless Claude Code instance running in tmux that:
- Listens for remote connections from voicemode.dev
- Can be woken by the iOS app or web interface
- Responds via voice using VoiceMode's TTS/STT capabilities

Think of it like a phone operator - always there to help when called.

### Agent Commands

| Command | Description |
|---------|-------------|
| `voicemode agent start` | Start operator in tmux session |
| `voicemode agent stop` | Send Ctrl-C to stop Claude gracefully |
| `voicemode agent stop --kill` | Kill the tmux window |
| `voicemode agent status` | Show running/stopped status |
| `voicemode agent send "msg"` | Send message (auto-starts if needed) |
| `voicemode agent send --no-start "msg"` | Send message (fail if not running) |

### Agent Directory Structure

Agent configuration lives in `~/.voicemode/agents/`:

```
~/.voicemode/agents/
├── voicemode.env       # Shared settings for all agents
├── AGENT.md            # AI entry point
├── CLAUDE.md           # Claude-specific instructions
├── SKILL.md            # Shared behavior
└── operator/           # Default agent
    ├── voicemode.env   # Operator-specific settings
    ├── AGENT.md
    ├── CLAUDE.md
    └── SKILL.md        # Operator behavior
```

### Configuration (voicemode.env)

Agent-specific settings override base settings. Available options:

```bash
# Base settings (~/.voicemode/agents/voicemode.env)
VOICEMODE_VOICE=nova           # Default TTS voice
VOICEMODE_SPEED=1.0            # Speech rate

# Operator settings (~/.voicemode/agents/operator/voicemode.env)
VOICEMODE_AGENT_REMOTE=true    # Enable remote connections
VOICEMODE_AGENT_STARTUP_MESSAGE=  # Message sent on startup
VOICEMODE_AGENT_CLAUDE_ARGS=   # Extra args for Claude Code
```

## Permissions Setup (Optional)

To use VoiceMode without permission prompts, add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
```

See the [Permissions Guide](docs/guides/permissions.md) for more options.

## Local Voice Services

For privacy or offline use, install local speech services:

- **[Whisper.cpp](docs/guides/whisper-setup.md)** - Local speech-to-text
- **[Kokoro](docs/guides/kokoro-setup.md)** - Local text-to-speech with multiple voices

These provide the same API as OpenAI, so VoiceMode switches seamlessly between them.

## Installation Details

<details>
<summary><strong>System Dependencies by Platform</strong></summary>

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y ffmpeg gcc libasound2-dev libasound2-plugins libportaudio2 portaudio19-dev pulseaudio pulseaudio-utils python3-dev
```

**WSL2 users**: The pulseaudio packages above are required for microphone access.

#### Fedora/RHEL

```bash
sudo dnf install alsa-lib-devel ffmpeg gcc portaudio portaudio-devel python3-devel
```

#### macOS

```bash
brew install ffmpeg node portaudio
```

#### NixOS

```bash
# Use development shell
nix develop github:mbailey/voicemode

# Or install system-wide
nix profile install github:mbailey/voicemode
```

</details>

<details>
<summary><strong>Alternative Installation Methods</strong></summary>

#### From source

```bash
git clone https://github.com/mbailey/voicemode.git
cd voicemode
uv tool install -e .
```

#### NixOS system-wide

```nix
# In /etc/nixos/configuration.nix
environment.systemPackages = [
  (builtins.getFlake "github:mbailey/voicemode").packages.${pkgs.system}.default
];
```

</details>

## Troubleshooting


| Problem | Solution |
|---------|----------|
| No microphone access | Check terminal/app permissions. WSL2 needs pulseaudio packages. |
| UV not found | Run `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| OpenAI API error | Verify `OPENAI_API_KEY` is set correctly |
| No audio output | Check system audio settings and available devices |


### Save Audio for Debugging

```bash
export VOICEMODE_SAVE_AUDIO=true
# Files saved to ~/.voicemode/audio/YYYY/MM/
```

## Documentation

- [Getting Started](docs/tutorials/getting-started.md) - Full setup guide
- [Configuration](docs/guides/configuration.md) - All environment variables
- [Whisper Setup](docs/guides/whisper-setup.md) - Local speech-to-text
- [Kokoro Setup](docs/guides/kokoro-setup.md) - Local text-to-speech
- [Development Setup](docs/tutorials/development-setup.md) - Contributing guide

Full documentation: [voice-mode.readthedocs.io](https://voice-mode.readthedocs.io)

## Links

- **Website**: [getvoicemode.com](https://getvoicemode.com)
- **GitHub**: [github.com/mbailey/voicemode](https://github.com/mbailey/voicemode)
- **PyPI**: [pypi.org/project/voice-mode](https://pypi.org/project/voice-mode/)
- **YouTube**: [@getvoicemode](https://youtube.com/@getvoicemode)
- **Twitter/X**: [@getvoicemode](https://twitter.com/getvoicemode)
- **Newsletter**: [![Subscribe](https://img.shields.io/badge/Subscribe-Newsletter-orange?style=flat-square)](https://buttondown.com/voicemode)

## License

MIT - A [Failmode](https://failmode.com) Project

---
mcp-name: com.failmode/voicemode
