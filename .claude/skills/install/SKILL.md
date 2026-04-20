---
name: install
description: Install VoiceMode, FFmpeg, and local voice services
allowed-tools: Bash(uvx:*), Bash(voicemode:*), Bash(brew:*), Bash(uname:*), Bash(which:*)
---

# /voicemode:install

Install VoiceMode and all dependencies for voice conversations.

## Quick Install (Non-Interactive)

```bash
uvx voice-mode-install --yes
voicemode service install whisper
voicemode service install kokoro
```

## Steps

1. Check architecture: `uname -m` (arm64 = Apple Silicon, recommended)
2. Check installed: `which voicemode`, `which ffmpeg`
3. Install missing: `uvx voice-mode-install --yes`
4. Install services: `voicemode service install whisper`, `voicemode service install kokoro`
5. Verify: `voicemode service status whisper`, `voicemode service status kokoro`
6. Reconnect MCP: Run `/mcp` → select voicemode → Reconnect (or restart Claude Code)

## Whisper Models

| Model | Size | RAM | Accuracy |
|-------|------|-----|----------|
| base | ~150MB | ~300MB | Good (default) |
| large-v2 | ~3GB | ~5GB | Best (16GB+ RAM) |
| large-v3-turbo | ~1.5GB | ~3GB | Fast & accurate |

Recommended for 16GB+: `voicemode whisper install --model large-v2`

## Prerequisites

- **UV**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Homebrew**: `brew.sh` (installer will install if missing on macOS)
