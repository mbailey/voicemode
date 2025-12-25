# Whisper Speech-to-Text Setup

Whisper is a local speech recognition service that converts audio to text for VoiceMode using OpenAI's Whisper model. It provides offline STT capabilities with various model sizes to balance speed and accuracy.

## Quick Start

```bash
# Install whisper service with default base model (includes Core ML on Apple Silicon!)
voice-mode whisper install

# Install with a different model
voice-mode whisper install --model large-v3

# Install without any model
voice-mode whisper install --no-model

# List available models and their status
voice-mode whisper models

# Download additional models (with Core ML support on Apple Silicon)
voice-mode whisper model install large-v2

# Start the service
voice-mode whisper start
```

**Apple Silicon Bonus:** On M1/M2/M3/M4 Macs, VoiceMode automatically downloads pre-built Core ML models for 2-3x faster performance. No Xcode or Python dependencies required!

Default endpoint: `http://127.0.0.1:2022/v1`

## Installation Methods

### Automatic Installation (Recommended)

VoiceMode includes an installation tool that sets up Whisper.cpp automatically:

```bash
# Install with default base model (142MB) - good balance of speed and accuracy
voice-mode whisper install

# Install with a specific model
voice-mode whisper install --model small

# Skip Core ML on Apple Silicon (not recommended)
voice-mode whisper install --skip-core-ml

# Install without downloading any model
voice-mode whisper install --no-model
```

This will:
- Clone and build Whisper.cpp with GPU support (if available)
- Download the specified model (default: base)
- **On Apple Silicon:** Automatically download pre-built Core ML models for 2-3x faster performance
- Create a start script with environment variable support
- Set up automatic startup (launchd on macOS, systemd on Linux)

### Manual Installation

#### macOS
```bash
# Install via Homebrew
brew install whisper.cpp

# Download model
mkdir -p ~/.voicemode/models/whisper
cd ~/.voicemode/models/whisper
curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin
```

#### Linux
```bash
# Clone and build whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make

# Download model
mkdir -p ~/.voicemode/models/whisper
cd ~/.voicemode/models/whisper
wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin
```

### Prerequisites

**macOS**:
- Xcode Command Line Tools (`xcode-select --install`) - Only for building whisper.cpp
- Homebrew (https://brew.sh)
- cmake (`brew install cmake`)

**Note for Apple Silicon users:** Core ML models are pre-built and downloaded automatically. No Xcode, PyTorch, or coremltools required!

**Linux**:
- Build essentials (`sudo apt install build-essential` on Ubuntu/Debian)

## Core ML Acceleration (Apple Silicon)

On Apple Silicon Macs (M1/M2/M3/M4), VoiceMode automatically downloads pre-built Core ML models from Hugging Face for 2-3x faster transcription:

- **Automatic:** Core ML models download alongside regular models
- **No Dependencies:** No PyTorch, Xcode, or coremltools needed
- **Pre-built:** Models are pre-compiled and ready to use
- **Performance:** 2-3x faster than Metal acceleration alone

To skip Core ML (not recommended):
```bash
voice-mode whisper model install large-v3 --skip-core-ml
```

## Model Management

### Available Models

| Model | Size | RAM Usage | Accuracy | Speed | Language Support |
|-------|------|-----------|----------|-------|-----------------|
| **tiny** | 39 MB | ~390 MB | Low | Fastest | Multilingual |
| **tiny.en** | 39 MB | ~390 MB | Low | Fastest | English only |
| **base** | 142 MB | ~500 MB | Fair | Fast | Multilingual |
| **base.en** | 142 MB | ~500 MB | Fair | Fast | English only |
| **small** | 466 MB | ~1 GB | Good | Moderate | Multilingual |
| **small.en** | 466 MB | ~1 GB | Good | Moderate | English only |
| **medium** | 1.5 GB | ~2.6 GB | Very Good | Slow | Multilingual |
| **medium.en** | 1.5 GB | ~2.6 GB | Very Good | Slow | English only |
| **large-v1** | 2.9 GB | ~3.9 GB | Excellent | Slower | Multilingual |
| **large-v2** | 2.9 GB | ~3.9 GB | Excellent | Slower | Multilingual (recommended) |
| **large-v3** | 3.1 GB | ~3.9 GB | Best | Slowest | Multilingual |
| **large-v3-turbo** | 1.6 GB | ~2.5 GB | Very Good | Moderate | Multilingual |

### Model Commands

```bash
# List all models with installation status
voice-mode whisper models

# Show/set active model
voice-mode whisper model active
voice-mode whisper model active small.en

# Install models
voice-mode whisper model install                  # Install default (large-v2)
voice-mode whisper model install medium           # Install specific model
voice-mode whisper model install all              # Install all models
voice-mode whisper model install large-v3 --force # Force re-download

# Remove models
voice-mode whisper model remove tiny
voice-mode whisper model remove tiny.en --force   # Skip confirmation
```

Note: After changing the active model, restart the whisper service for changes to take effect.

## Service Configuration

### Environment Variables

Configure in `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_WHISPER_MODEL=large-v2
VOICEMODE_WHISPER_PORT=2022
VOICEMODE_WHISPER_THREADS=          # Auto-detected if not set
VOICEMODE_WHISPER_LANGUAGE=auto
VOICEMODE_WHISPER_MODEL_PATH=~/.voicemode/models/whisper
```

**Thread Configuration**: By default, VoiceMode auto-detects the number of CPU cores and configures threads accordingly. You can override this by setting `VOICEMODE_WHISPER_THREADS` to a specific number.

### Running the Server

#### OpenAI-Compatible Server Mode

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
- `--model`: Path to model file
- `--host`: Server host (default: 127.0.0.1)
- `--port`: Server port (VoiceMode expects 2022)
- `--inference-path`: OpenAI-compatible endpoint path
- `--threads`: Number of threads for processing (auto-detected by VoiceMode)
- `--processors`: Number of parallel processors
- `--convert`: Convert audio to required format automatically (required for VoiceMode)
- `--print-progress`: Show transcription progress

**Note**: When using VoiceMode's managed service, threads are auto-detected based on your CPU cores. The `--convert` flag is required for VoiceMode to work correctly with various audio formats.

### Service Management

#### macOS (LaunchAgent)

```bash
# Start/stop service
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Enable/disable at startup
launchctl load -w ~/Library/LaunchAgents/com.voicemode.whisper.plist
launchctl unload -w ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Check status
launchctl list | grep whisper
```

#### Linux (Systemd)

```bash
# Start/stop service
systemctl --user start whisper
systemctl --user stop whisper

# Enable/disable at startup
systemctl --user enable whisper
systemctl --user disable whisper

# Check status and logs
systemctl --user status whisper
journalctl --user -u whisper -f
```

## Hardware Acceleration

### Apple Silicon (CoreML)

CoreML provides 2-3x faster transcription on Apple Silicon Macs:

```bash
# Install with CoreML support (when available)
voice-mode whisper model install base.en --skip-core-ml=false

# Performance comparison
# CPU Only: ~1x baseline
# Metal: ~3-4x faster
# CoreML + Metal: ~8-12x faster
```

**Note**: CoreML support requires full Xcode installation and may be disabled in some versions due to installation complexity.

### GPU Acceleration

The installation tool automatically detects and enables:
- **Mac (Apple Silicon)**: Metal acceleration
- **NVIDIA GPU**: CUDA acceleration
- **CPU**: Optimized CPU builds

## Integration with VoiceMode

VoiceMode automatically detects Whisper when available:

1. **First**: Checks for Whisper.cpp on `http://127.0.0.1:2022/v1`
2. **Fallback**: Uses OpenAI API (requires `OPENAI_API_KEY`)

### Custom Configuration

To use a different endpoint or force Whisper use:

```bash
export STT_BASE_URL=http://127.0.0.1:2022/v1
```

Or in MCP configuration:
```json
"voice-mode": {
  "env": {
    "STT_BASE_URL": "http://127.0.0.1:2022/v1"
  }
}
```

## Fully Local Setup

For completely offline voice processing, combine Whisper with Kokoro:

```bash
export STT_BASE_URL=http://127.0.0.1:2022/v1  # Whisper for STT
export TTS_BASE_URL=http://127.0.0.1:8880/v1  # Kokoro for TTS
export TTS_VOICE=af_sky                       # Kokoro voice
```

## Troubleshooting

### Service Won't Start
- Check if port 2022 is already in use: `lsof -i :2022`
- Verify model file exists at configured path
- Check service logs for error messages

### Poor Transcription Quality
- Try a larger model (base → small → medium → large)
- Ensure audio input quality is good
- Set specific language instead of 'auto' if known

### High CPU Usage
- Use a smaller model for better performance
- Consider English-only models (.en) for English content
- Enable GPU acceleration if available

### Model Installation Issues
- Verify adequate disk space (models range from 39MB to 3GB)
- Check network connectivity to Hugging Face
- Use `--force` flag to re-download corrupted models

## Performance Monitoring

```bash
# Check service status
voice-mode whisper status

# View performance statistics
voice-mode statistics

# Monitor real-time processing
tail -f ~/.voicemode/services/whisper/logs/performance.log

# Test model functionality
voice-mode whisper model test base.en
```

## File Locations

- **Models**: `~/.voicemode/models/whisper/` or `~/.voicemode/services/whisper/models/`
- **Service Config**: `~/.voicemode/services/whisper/config.json`
- **Model Preferences**: `~/.voicemode/whisper-models.txt`
- **Logs**: `~/.voicemode/services/whisper/logs/`
- **LaunchAgent** (macOS): `~/Library/LaunchAgents/com.voicemode.whisper.plist`
- **Systemd Service** (Linux): `~/.config/systemd/user/whisper.service`