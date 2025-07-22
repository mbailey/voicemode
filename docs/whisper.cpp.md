# Whisper.cpp STT Setup

Whisper.cpp is a local speech-to-text engine that provides an OpenAI-compatible API. Voice Mode can use it as an alternative to OpenAI's speech-to-text service.

## How Voice Mode Uses Whisper

Voice Mode automatically checks for local STT services before falling back to OpenAI:

1. **First**: Checks for Whisper.cpp on `http://127.0.0.1:2022/v1`
2. **Fallback**: Uses OpenAI API (requires `OPENAI_API_KEY`)

## Setting Up Whisper.cpp

### Quick Installation

Voice Mode includes an installation tool that sets up Whisper.cpp automatically:

```bash
# Install with default large-v2 model (recommended)
claude run install_whisper_cpp

# Install with a specific model
claude run install_whisper_cpp --model base.en
```

This will:
- Clone and build Whisper.cpp with GPU support (if available)
- Download the specified model (default: large-v2)
- Create a start script with environment variable support
- Set up automatic startup (launchd on macOS, systemd on Linux)

### Manual Installation

Alternatively, install Whisper.cpp following the [official instructions](https://github.com/ggerganov/whisper.cpp).

### Running the OpenAI-Compatible Server

To run Whisper.cpp with an OpenAI-compatible API endpoint:

```bash
whisper-server \
  --model models/ggml-large-v2.bin \
  --host 127.0.0.1 \
  --port 2022 \
  --inference-path "/v1/audio/transcriptions" \
  --threads 4 \
  --processors 1 \
  --convert \
  --print-progress
```

Key options:
- `--model`: Model file path (supports tiny, base, small, medium, large-v2, large-v3)
- `--host`: Server host (default: 127.0.0.1)
- `--port`: Server port (Voice Mode expects 2022)
- `--inference-path`: OpenAI-compatible endpoint path
- `--threads`: Number of threads for processing
- `--processors`: Number of parallel processors
- `--convert`: Convert audio to required format automatically
- `--print-progress`: Show transcription progress

Voice Mode will automatically detect and use it when running on port 2022!

## Manual Configuration (Optional)

To use a different Whisper endpoint or force its use:

```bash
export STT_BASE_URL=http://127.0.0.1:2022/v1
```

Or add to your MCP configuration:
```json
"voice-mode": {
  "env": {
    "STT_BASE_URL": "http://127.0.0.1:2022/v1"
  }
}
```

## Model Selection

### Available Models

| Model | Size | RAM Usage | Accuracy | Speed |
|-------|------|-----------|----------|-------|
| tiny | 39 MB | ~390 MB | Low | Fastest |
| base | 142 MB | ~500 MB | Fair | Fast |
| small | 466 MB | ~1 GB | Good | Moderate |
| medium | 1.5 GB | ~2.6 GB | Very Good | Slow |
| large-v2 | 3 GB | ~3.9 GB | Excellent | Slower |
| large-v3 | 3 GB | ~3.9 GB | Best | Slowest |

### Switching Models

Set the `VOICEMODE_WHISPER_MODEL` environment variable:

```bash
# Use base model for faster processing
export VOICEMODE_WHISPER_MODEL=base.en

# Use large-v2 for best accuracy (default)
export VOICEMODE_WHISPER_MODEL=large-v2
```

### Viewing Available Models

Use the MCP resource to see installed models:

```bash
claude resource read whisper://models
```

### Hardware Optimization

The installation tool automatically detects and enables:
- **Mac (Apple Silicon)**: Metal acceleration
- **NVIDIA GPU**: CUDA acceleration
- **CPU**: Optimized CPU builds

## Performance

Local Whisper typically processes speech in 1-3 seconds depending on:
- Hardware (GPU/CPU)
- Model size
- Audio length

## Fully Local Setup

For completely offline voice processing, combine Whisper with Kokoro:

```bash
export STT_BASE_URL=http://127.0.0.1:2022/v1
export TTS_BASE_URL=http://127.0.0.1:8880/v1
export TTS_VOICE=af_sky
```