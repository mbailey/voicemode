# VoiceMode


> **Install via:** `uv tool install voice-mode` | [getvoicemode.com](https://getvoicemode.com)

[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode)](https://pepy.tech/project/voice-mode)
[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode/month)](https://pepy.tech/project/voice-mode)
[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode/week)](https://pepy.tech/project/voice-mode)

Natural voice conversations for AI assistants. VoiceMode brings human-like voice interactions to Claude Code, AI code editors through the Model Context Protocol (MCP).

## 🖥️ Compatibility

**Runs on:** Linux • macOS • Windows (WSL) • NixOS | **Python:** 3.10-3.14

## ✨ Features

- **🎙️ Natural Voice Conversations** with Claude Code - ask questions and hear responses
- **🗣️ Supports local Voice Models** - works with any OpenAI API compatible STT/TTS services
- **⚡ Real-time** - low-latency voice interactions with automatic transport selection
- **🔧 MCP Integration** - seamless with Claude Code (and other MCP clients)
- **🎯 Silence detection** - automatically stops recording when you stop speaking (no more waiting!)
- **🔄 Multiple transports** - local microphone or LiveKit room-based communication (optional)  

## 🎯 Simple Requirements

**All you need to get started:**

1. **🎤 Computer with microphone and speakers**
2. **🔑 OpenAI API Key** (Recommended, if only as a backup for local services)

## Quick Start

### Install VoiceMode and dependencies with UV (Recommended)

- Linux (fedora, debian/ubuntu) 
- macOS
- Windows WSL

```bash
# Install VoiceMode MCP python package and dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh 
uvx voice-mode-install

# While local voice services can be installed automatically, we recommend
# providing an OpenAI API key as a fallback in case local services are unavailable
export OPENAI_API_KEY=your-openai-key  # Optional but recommended

# Add VoiceMode to Claude
claude mcp add --scope user voicemode -- uvx --refresh voice-mode

# Start a voice conversation
claude converse
```

### Manual Installation

For manual setup steps, see the [Getting Started Guide](docs/tutorials/getting-started.md).

## 🎬 Demo

Watch VoiceMode in action with Claude Code:

[![VoiceMode Demo](https://img.youtube.com/vi/cYdwOD_-dQc/maxresdefault.jpg)](https://www.youtube.com/watch?v=cYdwOD_-dQc)

The `converse` function makes voice interactions natural - it automatically waits for your response by default, creating a real conversation flow.

## Installation

### Prerequisites
- Python 3.10-3.14
- [Astral UV](https://github.com/astral-sh/uv) - Package manager (install with `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- OpenAI API Key (or compatible service)

> **Note on LiveKit:** LiveKit integration is optional and requires Python 3.10-3.13 (Python 3.14 support pending upstream dependencies). Install with: `uv tool install voice-mode[livekit]`. See [LiveKit Integration Guide](docs/guides/livekit-setup.md) for details.

#### System Dependencies

<details>
<summary><strong>Ubuntu/Debian</strong></summary>

```bash
sudo apt update
sudo apt install -y ffmpeg gcc libasound2-dev libasound2-plugins libportaudio2 portaudio19-dev pulseaudio pulseaudio-utils python3-dev
```

**Note for WSL2 users**: WSL2 requires additional audio packages (pulseaudio, libasound2-plugins) for microphone access.
</details>

<details>
<summary><strong>Fedora/RHEL</strong></summary>

```bash
sudo dnf install alsa-lib-devel ffmpeg gcc portaudio portaudio-devel python3-devel
```
</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install ffmpeg node portaudio
```
</details>

<details>
<summary><strong>Windows (WSL)</strong></summary>

Follow the Ubuntu/Debian instructions above within WSL.
</details>

<details>
<summary><strong>NixOS</strong></summary>

VoiceMode includes a flake.nix with all required dependencies. You can either:

1. **Use the development shell** (temporary):
```bash
nix develop github:mbailey/voicemode
```

2. **Install system-wide** (see Installation section below)
</details>

### Quick Install

```bash
# Using Claude Code (recommended)
claude mcp add --scope user voicemode uvx --refresh voice-mode
```

### Configuration for AI Coding Assistants

> 📖 **Looking for detailed setup instructions?** Check our comprehensive [Getting Started Guide](docs/tutorials/getting-started.md) for step-by-step instructions!

Below are quick configuration snippets. For full installation and setup instructions, see the integration guides above.

<details>
<summary><strong>Claude Code (CLI)</strong></summary>

```bash
claude mcp add --scope user voicemode -- uvx --refresh voice-mode
```

Or with environment variables:
```bash
claude mcp add --scope user --env OPENAI_API_KEY=your-openai-key voicemode -- uvx --refresh voice-mode
```
</details>

### Alternative Installation Options

<details>
<summary><strong>From source</strong></summary>

```bash
git clone https://github.com/mbailey/voicemode.git
cd voicemode
uv tool install -e .
```
</details>

<details>
<summary><strong>NixOS Installation Options</strong></summary>

**1. Install with nix profile (user-wide):**
```bash
nix profile install github:mbailey/voicemode
```

**2. Add to NixOS configuration (system-wide):**
```nix
# In /etc/nixos/configuration.nix
environment.systemPackages = [
  (builtins.getFlake "github:mbailey/voicemode").packages.${pkgs.system}.default
];
```

**3. Add to home-manager:**
```nix
# In home-manager configuration
home.packages = [
  (builtins.getFlake "github:mbailey/voicemode").packages.${pkgs.system}.default
];
```

**4. Run without installing:**
```bash
nix run github:mbailey/voicemode
```
</details>

## Configuration

- 📖 **[Getting Started](docs/tutorials/getting-started.md)** - Step-by-step setup guide
- 🔧 **[Configuration Reference](docs/guides/configuration.md)** - All environment variables

### Quick Setup

The only required configuration is your OpenAI API key:

```bash
export OPENAI_API_KEY="your-key"
```

## Local STT/TTS Services

For privacy-focused or offline usage, VoiceMode supports local speech services:

- **[Whisper.cpp](docs/guides/whisper-setup.md)** - Local speech-to-text with OpenAI-compatible API
- **[Kokoro](docs/guides/kokoro-setup.md)** - Local text-to-speech with multiple voice options

These services provide the same API interface as OpenAI, allowing seamless switching between cloud and local processing.

## Troubleshooting

### Common Issues

- **No microphone access**: Check system permissions for terminal/application
  - **WSL2 Users**: Additional audio packages (pulseaudio, libasound2-plugins) required for microphone access
- **UV not found**: Install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **OpenAI API error**: Verify your `OPENAI_API_KEY` is set correctly
- **No audio output**: Check system audio settings and available devices

### Audio Saving

To save all audio files (both TTS output and STT input):

```bash
export VOICEMODE_SAVE_AUDIO=true
```

Audio files are saved to: `~/.voicemode/audio/YYYY/MM/` with timestamps in the filename.

## Documentation

📚 **[Read the full documentation at voice-mode.readthedocs.io](https://voice-mode.readthedocs.io)**

### Getting Started

- **[Getting Started](docs/tutorials/getting-started.md)** - Step-by-step setup for all supported tools
- **[Configuration Guide](docs/guides/configuration.md)** - Complete environment variable reference

### Development

- **[Development Setup](docs/tutorials/development-setup.md)** - Local development guide

### Service Guides

- **[Whisper.cpp Setup](docs/guides/whisper-setup.md)** - Local speech-to-text configuration
- **[Kokoro Setup](docs/guides/kokoro-setup.md)** - Local text-to-speech configuration
- **[LiveKit Integration](docs/guides/livekit-setup.md)** - Real-time voice communication

## Links

- **Website**: [getvoicemode.com](https://getvoicemode.com)
- **Documentation**: [voice-mode.readthedocs.io](https://voice-mode.readthedocs.io)
- **GitHub**: [github.com/mbailey/voicemode](https://github.com/mbailey/voicemode)
- **PyPI**: [pypi.org/project/voice-mode](https://pypi.org/project/voice-mode/)

### Community

- **Twitter/X**: [@getvoicemode](https://twitter.com/getvoicemode)
- **YouTube**: [@getvoicemode](https://youtube.com/@getvoicemode)

## See Also

- 🚀 [Getting Started](docs/tutorials/getting-started.md) - Setup instructions for all supported tools
- 🔧 [Configuration Reference](docs/guides/configuration.md) - Environment variables and options
- 🎤 [Local Services Setup](docs/guides/kokoro-setup.md) - Run TTS/STT locally for privacy

## License

MIT - A [Failmode](https://failmode.com) Project

---
mcp-name: com.failmode/voicemode
