# Whisper Reference

Local speech-to-text (STT) service using Whisper.cpp.

## Overview

Whisper provides fast, accurate, private speech-to-text on your local machine. It's optimized for Apple Silicon but works on any platform.

## Installation

```bash
voicemode whisper service install
```

See @docs/installation.md for detailed installation guide with model options.

## Service Management

### Using MCP Tools

```python
# Check status
voicemode:service("whisper", "status")

# Start service
voicemode:service("whisper", "start")

# Stop service
voicemode:service("whisper", "stop")

# Restart service
voicemode:service("whisper", "restart")

# View logs
voicemode:service("whisper", "logs", lines=50)

# Enable auto-start on login
voicemode:service("whisper", "enable")

# Disable auto-start
voicemode:service("whisper", "disable")
```

### Using CLI

```bash
voicemode whisper service status
voicemode whisper service start
voicemode whisper service stop
voicemode whisper service restart
voicemode whisper service logs
voicemode whisper service logs -f  # Follow logs
```

## Model Selection

Whisper supports multiple model sizes, trading accuracy for speed:

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| tiny | 75MB | Fastest | Good | Quick testing, low-power devices |
| base | 150MB | Fast | Better | **Recommended default** |
| small | 460MB | Medium | Very Good | Higher accuracy needs |
| medium | 1.5GB | Slow | Excellent | Professional transcription |

### Changing Models

```bash
# Install with different model
voicemode whisper service install --model small

# Check current model
ls ~/.voicemode/services/whisper/models/
```

## Configuration

### Port

Whisper runs on port **2022** by default, exposing an OpenAI-compatible `/v1/audio/transcriptions` endpoint.

### Model Location

Models are stored in:
```
~/.voicemode/services/whisper/models/
```

## Troubleshooting

### Service Won't Start

1. Check if FFmpeg is installed:
   ```bash
   ffmpeg -version
   ```

2. Check service logs:
   ```bash
   voicemode whisper service logs
   ```

3. Verify model files exist:
   ```bash
   ls -lh ~/.voicemode/services/whisper/models/
   ```

### Model Download Stuck

Check network connectivity and disk space. Try reinstalling:
```bash
voicemode whisper service uninstall
voicemode whisper service install
```

### Port Already in Use

Check if another process is using port 2022:
```bash
lsof -i :2022
```

### Slow Transcription

- Try a smaller model (tiny or base)
- Ensure the service has completed initial model loading
- Check system resource usage

## API Compatibility

Whisper exposes an OpenAI-compatible endpoint:

```
POST http://localhost:2022/v1/audio/transcriptions
```

This allows VoiceMode to seamlessly switch between local Whisper and cloud OpenAI STT.
