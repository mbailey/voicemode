# Kokoro ONNX Text-to-Speech Setup

Kokoro ONNX is a lightweight alternative to the PyTorch-based Kokoro service. It uses ONNX Runtime for efficient CPU inference with lower memory usage and better multi-core utilisation.

## Why Kokoro ONNX?

| Feature | Kokoro (PyTorch) | Kokoro ONNX |
|---------|------------------|-------------|
| Model size | ~310 MB | ~88 MB (int8) |
| Memory usage | ~2 GB | ~300 MB |
| CPU utilisation | Single core | All cores |
| Inference time | ~30s+ | <10s |
| GPU required | Optional | No (optional) |
| Startup time | Slower | Faster |

### Real-world Benchmarks

Streaming TTS on CPU (text: "Hello! How can I help you today?"):

| Metric | Kokoro ONNX | Kokoro PyTorch | Improvement |
|--------|-------------|----------------|-------------|
| Time to first audio (TTFA) | 1.6s | 7.8s | **4.9x faster** |
| Total streaming time | 3.6s | 9.8s | **2.7x faster** |

ONNX Runtime uses all CPU cores in parallel, while PyTorch uses a single core at 100%.

**GPU Acceleration**: ONNX Runtime supports GPU via `onnxruntime-gpu` (NVIDIA CUDA), `onnxruntime-directml` (Windows - AMD/Intel/NVIDIA), or `onnxruntime-migraphx` (Linux AMD). CPU inference is already fast due to multi-core utilisation.

## Quick Start

```bash
# Install kokoro-onnx service
voicemode service install kokoro-onnx

# Start the service
voicemode service start kokoro-onnx

# Check status
voicemode service status kokoro-onnx

# Stop the service
voicemode service stop kokoro-onnx
```

Default endpoint: `http://127.0.0.1:8881/v1`

## Installation

### Option 1: Automatic (Recommended)

```bash
# Install dependencies and download models automatically
voicemode service install kokoro-onnx

# Start the service
voicemode service start kokoro-onnx
```

This will:
- Install Python dependencies (kokoro-onnx, fastapi, uvicorn)
- Download the int8 model and voices file to `~/.voicemode/models/`
- Install the start script

### Option 2: Manual Installation

```bash
# Install dependencies
pip install kokoro-onnx fastapi uvicorn

# Download model files
mkdir -p ~/.voicemode/models
cd ~/.voicemode/models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

# Start the service
voicemode service start kokoro-onnx
```

## Configuration

Add to `~/.voicemode/voicemode.env`:

```bash
# Kokoro ONNX settings
VOICEMODE_KOKORO_ONNX_PORT=8881
VOICEMODE_KOKORO_ONNX_MODEL=kokoro-v1.0.int8.onnx
VOICEMODE_KOKORO_ONNX_VOICES=voices-v1.0.bin
VOICEMODE_KOKORO_ONNX_MODELS_DIR=~/.voicemode/models

# Use kokoro-onnx as primary TTS (fallback to PyTorch kokoro)
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8881/v1,http://127.0.0.1:8880/v1
```

For Claude Code, add to `~/.claude/settings.json`:

```json
{
  "env": {
    "VOICEMODE_TTS_BASE_URLS": "http://127.0.0.1:8881/v1"
  }
}
```

## Available Models

| Model | Size | Quality | Speed |
|-------|------|---------|-------|
| kokoro-v1.0.onnx | 310 MB | Best | Slower |
| kokoro-v1.0.fp16.onnx | 169 MB | High | Medium |
| kokoro-v1.0.int8.onnx | 88 MB | Good | Fast |

The int8 model is recommended for most use cases.

## API Endpoints

The server exposes OpenAI-compatible endpoints:

### Health Check
```bash
curl http://localhost:8881/health
```

### List Voices
```bash
curl http://localhost:8881/v1/voices
```

### Generate Speech
```bash
curl -X POST http://localhost:8881/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello world", "voice": "af_heart"}' \
  -o output.pcm

# Play PCM audio (24kHz, 16-bit, mono)
ffplay -f s16le -ar 24000 -ac 1 output.pcm
```

### Available Formats

- `pcm` - Raw PCM audio (default)
- `wav` - WAV format
- `mp3` - MP3 format (requires pydub)

## Troubleshooting

### Model not found

Ensure model files are in the correct location:

```bash
ls ~/.voicemode/models/
# Should show: kokoro-v1.0.int8.onnx  voices-v1.0.bin
```

### Service won't start

Check if port 8881 is in use:

```bash
lsof -i :8881
```

### Wrong TTS service being used

Verify the TTS URL configuration:

```bash
grep TTS_BASE_URL ~/.voicemode/voicemode.env
```

Ensure kokoro-onnx (8881) comes before kokoro (8880) in the URL list.

## Running Manually

For development or debugging:

```bash
cd ~/code/voicemode
VOICEMODE_KOKORO_ONNX_MODEL=kokoro-v1.0.int8.onnx \
VOICEMODE_KOKORO_ONNX_VOICES=voices-v1.0.bin \
uv run python -m uvicorn voice_mode.services.kokoro_onnx.server:app \
  --host 0.0.0.0 --port 8881
```

## See Also

- [Kokoro Setup](kokoro-setup.md) - PyTorch-based Kokoro service
- [Configuration Guide](configuration.md) - VoiceMode configuration
- [Selecting Voices](selecting-voices.md) - Voice selection guide

## Appendix: Raw Benchmark Logs

<details>
<summary>Kokoro ONNX (port 8881)</summary>

```
2026-02-13 11:16:29,448 - voicemode - INFO - simple_tts_failover called with: text='Hello! How can I help you today?...', voice=af_sky, model=tts-1
2026-02-13 11:16:29,449 - voicemode - INFO - simple_tts_failover: Starting with TTS_BASE_URLS = ['http://127.0.0.1:8881/v1']
2026-02-13 11:16:29,449 - voicemode - INFO - Trying TTS endpoint: http://127.0.0.1:8881/v1
2026-02-13 11:16:29,452 - voicemode - INFO - TTS: Converting text to speech: 'Hello! How can I help you today?'
2026-02-13 11:16:31,076 - voicemode - INFO - First audio chunk received after 1.623s
2026-02-13 11:16:33,081 - voicemode - INFO - Streaming complete - TTFA: 1.623s, Total: 3.629s, Chunks: 24
2026-02-13 11:16:33,082 - voicemode - INFO - ✓ TTS streamed successfully - TTFA: 1.623s
```

</details>

<details>
<summary>Kokoro PyTorch (port 8880)</summary>

```
2026-02-13 11:16:11,799 - voicemode - INFO - simple_tts_failover called with: text='Hello! How can I help you today?...', voice=af_sky, model=tts-1
2026-02-13 11:16:11,799 - voicemode - INFO - simple_tts_failover: Starting with TTS_BASE_URLS = ['http://127.0.0.1:8880/v1']
2026-02-13 11:16:11,799 - voicemode - INFO - Trying TTS endpoint: http://127.0.0.1:8880/v1
2026-02-13 11:16:11,803 - voicemode - INFO - TTS: Converting text to speech: 'Hello! How can I help you today?'
2026-02-13 11:16:19,578 - voicemode - INFO - First audio chunk received after 7.774s
2026-02-13 11:16:21,625 - voicemode - INFO - Streaming complete - TTFA: 7.774s, Total: 9.821s, Chunks: 25
2026-02-13 11:16:21,625 - voicemode - INFO - ✓ TTS streamed successfully - TTFA: 7.774s
```

</details>
