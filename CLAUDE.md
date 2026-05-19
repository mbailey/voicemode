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

# Release workflow (bumps version, tags, pushes) — see "Releases & Changelog" below before running
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

## Releases & Changelog

**The changelog is the release notes.** Keep it accurate continuously — it is not written at release time.

### Versioning

- Semantic Versioning, `X.Y.Z`. New backward-compatible features → minor bump (e.g. `8.6.1` → `8.7.0`); fixes only → patch.
- **Source of truth: `voice_mode/__version__.py`** — auto-updated by the release script. **Never edit it by hand** (it says so itself). `pyproject.toml` reads it via `[tool.hatch.version]`.
- The release script also bumps `server.json`, `installer/pyproject.toml`, and `.claude-plugin/plugin.json` (the plugin gets a `p0` suffix, e.g. `8.7.0p0`). Don't bump these manually either.

### The CHANGELOG is continuously maintained

- Format: [Keep a Changelog](https://keepachangelog.com/) — a `## [Unreleased]` section at the top with `### Added / Changed / Deprecated / Removed / Fixed` (this project also uses a `### Migration` subsection).
- **As PRs land, their user-facing changes go into `## [Unreleased]`** — not deferred to release day. Reference task IDs (`VM-xxxx`) and PR links, matching the existing entry style.
- Write entries as **release notes for users**: GitHub Actions extracts the version's changelog section verbatim into the GitHub Release (see below), so it must read well standalone and showcase new functionality.
- The `/changelog` skill (`claude-code-tools:changelog`) can help draft entries, but headline/showcase wording is human-curated because it ships to users.

### Cutting a release — `make release`

```bash
make release        # prompts for the new version, then runs scripts/release.py X.Y.Z
```

`scripts/release.py X.Y.Z` does **all of this automatically** — do NOT do these by hand:

1. Bumps the version in all four files above.
2. **Rewrites the CHANGELOG header**: turns `## [Unreleased]` into `## [Unreleased]` (fresh empty) + `## [X.Y.Z] - YYYY-MM-DD` below it. **So never manually cut the version header or add the date — that is the release script's job.** Your only changelog responsibility before a release is making sure the *Unreleased* section is complete and accurate.
3. `git commit -m "chore: bump version to X.Y.Z for all packages"`.
4. Creates annotated tag `vX.Y.Z`.
5. `git push origin` (the **current branch**) + pushes the tag.

Useful flags (pass via `scripts/release.py` directly): `--current` (print version), `--no-commit` (update files only), `--no-push` (commit + tag, no push), `--package package|installer`.

### What the tag triggers

Pushing a `v*` tag fires two GitHub Actions workflows:

- **`create-release.yml`** — `awk`-extracts the `## [X.Y.Z] - DATE` section from CHANGELOG.md and publishes it as the GitHub Release body. **The header must be exactly `## [X.Y.Z] - DATE`** or extraction yields empty notes — another reason to let `release.py` write it.
- **`publish-pypi-and-mcp.yml`** — builds and publishes packages to PyPI and the MCP registry.

Monitor: https://github.com/mbailey/voicemode/actions

### Pre-release checklist (do this before `make release`)

1. **Be on `master` and `git pull` first.** Mike merges PRs locally (`--no-ff`) and pushes master; `release.py` pushes whatever branch you're on, so the tag must be cut from an up-to-date `master` or merged work is silently excluded.
2. Verify `## [Unreleased]` is complete — every merged user-facing PR represented, headline features showcased. Cross-check against `git log <last-tag>..origin/master`.
3. Decide the version bump per SemVer.
4. `make release`, then watch the Actions run.

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

## VoiceMode Suite

This is the core Python package. VoiceMode is a suite of related projects:

**For a complete overview of all VoiceMode components**, read:
- **[voicemode-meta/COMPONENTS.md](../voicemode-meta/COMPONENTS.md)** - Full suite documentation

Quick reference:
- **voicemode** (this repo) - Python MCP server for local voice mode
- **voicemode-dev** - Cloudflare Workers backend for voicemode.dev
- **voicemode-ios** - Native iOS app
- **voicemode-macos** - Native macOS app
- **voicemode-meta** - Project coordination and operations

## See Also

- **[skills/voicemode/SKILL.md](skills/voicemode/SKILL.md)** - Voice interaction usage and MCP tools
- **[skills/voicemode-connect/SKILL.md](skills/voicemode-connect/SKILL.md)** - Remote voice via mobile/web clients
- **[docs/tutorials/getting-started.md](docs/tutorials/getting-started.md)** - Installation guide
- **[docs/guides/configuration.md](docs/guides/configuration.md)** - Configuration reference
- **[docs/concepts/architecture.md](docs/concepts/architecture.md)** - Detailed architecture