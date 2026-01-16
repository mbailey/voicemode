---
name: install
description: Install VoiceMode, FFmpeg, and local voice services
---

# VoiceMode Installation

This skill installs VoiceMode system dependencies and optionally configures local voice services.

## Quick Start

Run the bundled dependency installer:

```bash
${SKILL_DIR}/../../bin/install-deps
```

This checks what's installed and reports any missing dependencies.

## Installation Workflow

### Step 1: Check Dependencies

First, run the install-deps script to see what's needed:

```bash
${SKILL_DIR}/../../bin/install-deps
```

If everything is installed, you'll see "All dependencies are installed!" and can skip to Step 3.

### Step 2: Install Missing Dependencies

If dependencies are missing, run with `--install`:

```bash
${SKILL_DIR}/../../bin/install-deps --install
```

On macOS, this requires no sudo. On Linux, you may be prompted for sudo password.

**What gets installed:**
- **macOS**: Homebrew (if needed), portaudio, ffmpeg, uv, voice-mode
- **Debian/Ubuntu**: libportaudio2, ffmpeg, python3-dev, gcc, uv, voice-mode
- **Fedora/RHEL**: portaudio, ffmpeg, python3-devel, gcc, uv, voice-mode

### Step 3: Install Voice Services (Optional)

For local speech-to-text and text-to-speech (recommended on Apple Silicon):

```bash
# Install Whisper (speech-to-text)
voicemode service install whisper

# Install Kokoro (text-to-speech)
voicemode service install kokoro
```

First-time service startup downloads models (2-5 minutes), then startup is instant.

### Step 4: Start Services

```bash
voicemode service start whisper
voicemode service start kokoro
```

Or use MCP tools:
```python
voicemode:service("whisper", "start")
voicemode:service("kokoro", "start")
```

### Step 5: Reconnect MCP

After installation, reconnect the VoiceMode MCP server:
- Run `/mcp` → select voicemode → "Reconnect"
- Or restart Claude Code

## Verify Installation

Check service status:

```bash
voicemode service status
```

Or via MCP:
```python
voicemode:service("whisper", "status")
voicemode:service("kokoro", "status")
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `voicemode: command not found` | Run `source ~/.local/bin/env` or restart shell |
| Service won't start | Check logs: `voicemode service logs whisper` |
| MCP tools not available | Reconnect MCP or restart Claude Code |

## Platform Notes

### macOS (Apple Silicon)
- No sudo required for any installation
- Local services highly recommended
- GPU acceleration for fast inference

### macOS (Intel)
- Same as Apple Silicon but slower inference
- Cloud services may be preferred

### Linux
- sudo required for apt/dnf package installation
- Local services work but may be slower without GPU
- Consider cloud services for better performance
