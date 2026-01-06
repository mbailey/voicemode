# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Voice Interaction

Load the voicemode skill for voice conversation support: `/voicemode:voicemode`

## Project Overview

VoiceMode is a Python package that provides voice interaction capabilities for AI assistants through the Model Context Protocol (MCP). It enables natural voice conversations with Claude Code and other AI coding assistants by integrating speech-to-text (STT) and text-to-speech (TTS) services.

## Key Commands

### Development & Testing
```bash
# Install in development mode with dependencies
make dev-install

# Run all unit tests
make test
# Or directly: uv run pytest tests/ -v --tb=short

# Run specific test
uv run pytest tests/test_voice_mode.py -v

# Clean build artifacts
make clean
```

### Building & Publishing
```bash
# Build Python package
make build-package

# Build development version (auto-versioned)
make build-dev  

# Test package installation
make test-package

# Release workflow (bumps version, tags, pushes)
make release
```

### Documentation
```bash
# Serve docs locally at http://localhost:8000
make docs-serve

# Build documentation site
make docs-build

# Check docs for errors (strict mode)
make docs-check
```

## Architecture Overview

### Core Components

1. **MCP Server (`voice_mode/server.py`)**
   - FastMCP-based server providing voice tools via stdio transport
   - Auto-imports all tools, prompts, and resources
   - Handles FFmpeg availability checks and logging setup

2. **Tool System (`voice_mode/tools/`)**
   - **converse.py**: Primary voice conversation tool with TTS/STT integration
   - **service.py**: Unified service management for Whisper/Kokoro
   - **providers.py**: Provider discovery and registry management
   - **devices.py**: Audio device detection and management
   - Services subdirectory contains install/uninstall tools for Whisper and Kokoro
   - See [Tool Loading Architecture](docs/reference/tool-loading-architecture.md) for internal details

3. **Provider System (`voice_mode/providers.py`)**
   - Dynamic discovery of OpenAI-compatible TTS/STT endpoints
   - Health checking and failover support
   - Maintains registry of available voice services

4. **Configuration (`voice_mode/config.py`)**
   - Environment-based configuration with sensible defaults
   - Support for voice preference files (project/user level)
   - Audio format configuration (PCM, MP3, WAV, FLAC, AAC, Opus)

5. **Resources (`voice_mode/resources/`)**
   - MCP resources exposed for client access
   - Statistics, configuration, changelog, and version information
   - Whisper model management

### Service Architecture

The project supports multiple voice service backends:
- **OpenAI API**: Cloud-based TTS/STT (requires API key)
- **Whisper.cpp**: Local speech-to-text service
- **Kokoro**: Local text-to-speech with multiple voices

Services can be installed and managed through MCP tools, with automatic service discovery and health checking.

### Key Design Patterns

1. **OpenAI API Compatibility**: All voice services expose OpenAI-compatible endpoints, enabling transparent switching between providers
2. **Dynamic Tool Discovery**: Tools are auto-imported from the tools directory structure
3. **Failover Support**: Automatic fallback between services based on availability
4. **Local Microphone Transport**: Direct audio capture via PyAudio for voice interactions
5. **Audio Format Negotiation**: Automatic format validation against provider capabilities

## Development Notes

- The project uses `uv` for package management (not pip directly)
- Python 3.10+ is required
- FFmpeg is required for audio processing
- The project follows a modular architecture with FastMCP patterns
- Service installation tools handle platform-specific setup (launchd on macOS, systemd on Linux)
- Event logging and conversation logging are available for debugging
- WebRTC VAD is used for silence detection when available

## Testing

- Unit tests: `tests/` - run with `make test`
- Manual tests: `tests/manual/` - require user interaction

## Logging

Logs are stored in `~/.voicemode/`:
- `logs/conversations/` - Voice exchange history (JSONL)
- `logs/events/` - Operational events and errors
- `audio/` - Saved TTS/STT audio files
- `voicemode.env` - User configuration

## See Also

- **[skills/voicemode/SKILL.md](skills/voicemode/SKILL.md)** - Voice interaction usage and MCP tools
- **[docs/tutorials/getting-started.md](docs/tutorials/getting-started.md)** - Installation guide
- **[docs/guides/configuration.md](docs/guides/configuration.md)** - Configuration reference
- **[docs/concepts/architecture.md](docs/concepts/architecture.md)** - Detailed architecture