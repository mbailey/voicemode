# VoiceMode Installation Guide

Complete installation guide for VoiceMode and local voice services.

## Prerequisites

Before installing VoiceMode, ensure you have:
- **FFmpeg**: Required for audio processing (`ffmpeg -version` to check)
- **Python 3.11+**: Required for VoiceMode package

## Installing VoiceMode Package

Run the installer with `--yes` flag (required for non-interactive environments like Claude Code):

```bash
uvx voice-mode-install --yes
```

This installs the VoiceMode package and CLI. It does NOT install local speech services.

## Using OpenAI API (Alternative to Local Services)

If you have an `OPENAI_API_KEY` set, VoiceMode can use OpenAI's cloud services without installing local services:

- **STT**: OpenAI Whisper API (cloud)
- **TTS**: OpenAI voices (alloy, echo, fable, onyx, nova, shimmer)

This is useful when:
- You don't want to download large models
- You're not on Apple Silicon
- You prefer cloud services

You can also use OpenAI as a fallback - if local services fail, VoiceMode will automatically try OpenAI if the API key is set.

## Local Voice Services

### Service Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| Whisper | 2022 | Speech-to-text (STT) |
| Kokoro | 8880 | Text-to-speech (TTS) |

### When to Install Local Services

Local voice services (Whisper for STT, Kokoro for TTS) are recommended when:
- Running on **Apple Silicon Mac** (arm64) - optimal performance
- Privacy is important - audio stays on device
- Working offline or with unreliable internet
- Faster response times are desired

Check architecture:
```bash
uname -m  # arm64 = Apple Silicon
```

### Download Sizes and Requirements

Get informed consent before installing. Here are the resource requirements:

| Service | Download Size | Disk Space | First Start Time |
|---------|---------------|------------|------------------|
| Whisper (tiny) | ~75MB | ~150MB | 30 seconds |
| Whisper (base) | ~150MB | ~300MB | 1-2 minutes |
| Whisper (small) | ~460MB | ~1GB | 2-3 minutes |
| Whisper (medium) | ~1.5GB | ~3GB | 3-5 minutes |
| Kokoro TTS | ~350MB | ~700MB | 2-3 minutes |

**Recommended setup**: Whisper base + Kokoro = ~500MB download, ~1GB disk space.

### Installing Whisper (Speech-to-Text)

```bash
# Install with base model (recommended)
voicemode whisper service install

# Or specify a different model
voicemode whisper service install --model tiny    # Faster, less accurate
voicemode whisper service install --model small   # More accurate
voicemode whisper service install --model medium  # Most accurate
```

### Installing Kokoro (Text-to-Speech)

```bash
voicemode kokoro install
```

### Service Startup

Services auto-start after installation and are configured to start on login.

**First run behavior**: Services download AI models on first start. The first `converse` call may be slow while models load. Subsequent starts are instant.

## Waiting for Services

After installation, wait for services to be ready:

**Wait for Whisper (port 2022):**
```bash
echo "Waiting for Whisper to be ready..."
while ! nc -z localhost 2022 2>/dev/null; do sleep 2; done
echo "Whisper is ready!"
```

**Wait for Kokoro (port 8880):**
```bash
echo "Waiting for Kokoro to be ready..."
while ! nc -z localhost 8880 2>/dev/null; do sleep 2; done
echo "Kokoro is ready!"
```

## Verifying Installation

Check service status:
```bash
voicemode whisper service status
voicemode kokoro status
```

Check model files:
```bash
ls -lh ~/.voicemode/services/whisper/models/
ls -lh ~/.voicemode/services/kokoro/models/
```

Test voice conversation:
```bash
voicemode converse -m "Hello, voice mode is working!"
```

## Viewing Logs

Monitor service logs during installation or troubleshooting:

```bash
# Follow Whisper logs
voicemode whisper service logs -f

# Follow Kokoro logs
voicemode kokoro logs -f
```

## Updating VoiceMode

```bash
voicemode update
```

## Uninstalling Services

```bash
voicemode whisper service uninstall
voicemode kokoro uninstall
```

## Troubleshooting

See the troubleshooting section in the main VoiceMode skill for common issues.
