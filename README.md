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
claude mcp add --scope user voicemode -- uvx --refresh --from voice-mode voicemode-mcp-launcher

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

**Platforms:** Linux, macOS, Windows (native or WSL), NixOS
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

## Uninstall

```bash
voicemode uninstall
```

This one command reverses the install: it stops and removes the Whisper,
Kokoro, mlx-audio, and voicemode ("serve") services; removes the Claude Code
MCP registration (both user and local scope); backs up
`~/.voicemode/voicemode.env` (renamed, not deleted); and removes the
`voice-mode` package itself (`uv tool uninstall voice-mode` — done last,
since it's the running binary). **Voice clones, recordings, conversations,
transcriptions, and models are never removed automatically** — even with
`--remove-all-data` — and are listed in the printed report so you know
what's still on disk.

Flags:

- `-y`, `--yes` — skip the confirmation prompt (non-interactive use)
- `--remove-models` — also delete downloaded Whisper/Kokoro/mlx-audio models
- `--remove-all-data` — also delete everything else under `~/.voicemode/`
  (logs, transcriptions, audio, conversations, cache, config backup)
  **except** voice clones (`voices/`, `voices.json`), which stay put no
  matter what

**Both install paths:**

- **Claude Code plugin** (Quick Start Option 1) — `voicemode uninstall`
  still tears down the services, config, and package, but `claude mcp
  remove` cannot see a plugin-managed MCP registration. Also run `claude
  plugin uninstall voicemode` to remove the plugin itself (the command
  detects the plugin and reminds you of this step).
- **Python installer package** (Quick Start Option 2) — `voicemode
  uninstall` is the complete reversal; no extra step needed.

Need to remove just one service instead of everything? `voicemode service
uninstall whisper|kokoro|mlx-audio|voicemode` uninstalls a single service.

For a complete manual-removal reference — every path VoiceMode and its
installer write to disk, including shared tools like `uv` and Homebrew that
this command intentionally leaves alone — see
[docs/reference/uninstall.md](docs/reference/uninstall.md).

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
- [Uninstall](docs/reference/uninstall.md) - Complete manual removal reference
- [Development Setup](docs/tutorials/development-setup.md) - Contributing guide

Full documentation: [voicemode.dev](https://voicemode.dev)

## Links

- **Website**: [voicemode.dev](https://voicemode.dev)
- **GitHub**: [github.com/mbailey/voicemode](https://github.com/mbailey/voicemode)
- **PyPI**: [pypi.org/project/voice-mode](https://pypi.org/project/voice-mode/)
- **YouTube**: [@getvoicemode](https://youtube.com/@getvoicemode)
- **Twitter/X**: [@getvoicemode](https://twitter.com/getvoicemode)
- **Newsletter**: [![Subscribe](https://img.shields.io/badge/Subscribe-Newsletter-orange?style=flat-square)](https://buttondown.com/voicemode)

## License

MIT - A [Failmode](https://failmode.com) Project

---
mcp-name: dev.voicemode/voicemode
