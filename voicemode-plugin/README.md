# VoiceMode Plugin for Claude Code

Voice conversations with Claude Code using local speech-to-text (STT) and text-to-speech (TTS) services.

## Installation

```bash
# Add plugin from local path (for development)
/plugin marketplace add /path/to/voicemode-plugin
/plugin install voicemode

# Or install from marketplace (once published)
/plugin install voicemode
```

## Slash Commands

- `/voicemode:install` - Install VoiceMode and dependencies
- `/voicemode:converse` - Start a voice conversation
- `/voicemode:status` - Check service status
- `/voicemode:start` - Start voice services
- `/voicemode:stop` - Stop voice services

## Features

- **Local STT** - Whisper.cpp for fast, private speech-to-text
- **Local TTS** - Kokoro for natural text-to-speech with multiple voices
- **MCP Integration** - Full MCP server with converse and service management tools
- **Audio Hooks** - Sound feedback during tool execution via hook receiver

## Prerequisites

Before using VoiceMode, install the services:

```bash
# Install VoiceMode
curl -sL https://voicemode.ai/install.sh | bash

# Install services
voicemode whisper service install
voicemode kokoro install
```

## Components

This plugin includes:

1. **MCP Server** - `voicemode-mcp` via uvx
2. **Skill File** - VoiceMode usage patterns and documentation
3. **Slash Commands** - Quick access to common operations
4. **Hooks** - Sound font integration via `voicemode-hook-receiver`

## Usage

Start a voice conversation:
```
/voicemode:converse Hello, how can I help you today?
```

Check services are running:
```
/voicemode:status
```

## Documentation

- [VoiceMode Documentation](https://voicemode.ai/docs)
- [GitHub Repository](https://github.com/mbailey/voicemode)

## License

MIT License - see LICENSE file for details.
