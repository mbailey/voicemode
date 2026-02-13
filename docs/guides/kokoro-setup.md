# Kokoro Text-to-Speech Setup

Kokoro is a high-quality local text-to-speech service that provides natural-sounding voices in multiple languages. It offers an OpenAI-compatible API that VoiceMode can use as an alternative to cloud-based TTS services.

## Quick Start

```bash
# Install kokoro service
voicemode service install kokoro

# Start the service
voicemode service start kokoro

# Check status
voicemode service status kokoro
```

Default endpoint: `http://127.0.0.1:8880/v1`

## Installation Methods

### Automatic Installation (Recommended)

VoiceMode includes an installation tool that handles everything:

```bash
# Install kokoro with default settings
voicemode service install kokoro

# Or using Claude Code
claude converse "Please install kokoro-fastapi"
```

This will:
- Clone the kokoro-fastapi repository to `~/.voicemode/kokoro-fastapi`
- Install UV package manager if needed
- Set up automatic startup (systemd on Linux, launchd on macOS)
- Start the service on port 8880
- Download models automatically on first use

### Manual Installation

#### Prerequisites
```bash
# Ensure Python 3.8+ is installed
python3 --version

# Install uvx
pip install uvx
```

#### Download and Run
```bash
# Create models directory
mkdir -p ~/Models/kokoro

# Run kokoro-fastapi with uvx
uvx kokoro-fastapi[cpu] serve \
  --host 127.0.0.1 \
  --port 8880 \
  --models-dir ~/Models/kokoro
```

Models download automatically from [Hugging Face](https://huggingface.co/hexgrad/Kokoro-82M) on first use.

## Available Voices

### English Voices
- **American Female**: `af_sky` (default), `af_sarah`
- **American Male**: `am_adam`, `am_michael`
- **British Female**: `bf_emma`, `bf_isabella`
- **British Male**: `bm_george`, `bm_lewis`

### International Voices
- **Spanish**: `ef_dora` (female), `em_alex` (male)
- **French**: `ff_siwis` (female), `fm_gabriel` (male)
- **Italian**: `if_sara` (female), `im_nicola` (male)
- **Portuguese**: `pf_dora` (female), `pm_alex` (male)
- **Chinese**: `zf_xiaobei` (female), `zm_yunjian` (male)
- **Japanese**: `jf_alpha` (female), `jm_kumo` (male)
- **Hindi**: `hf_alpha` (female), `hm_omega` (male)

## Service Configuration

### Environment Variables

Configure in `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_KOKORO_PORT=8880
VOICEMODE_KOKORO_MODELS_DIR=~/Models/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro
VOICEMODE_KOKORO_DEFAULT_VOICE=af_sky
```

### Service Management

#### macOS (LaunchAgent)

```bash
# Start/stop service
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro.plist
launchctl unload ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Enable/disable at startup
launchctl load -w ~/Library/LaunchAgents/com.voicemode.kokoro.plist
launchctl unload -w ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Check status
launchctl list | grep kokoro
```

#### Linux (Systemd)

```bash
# Start/stop service
systemctl --user start kokoro
systemctl --user stop kokoro

# Enable/disable at startup
systemctl --user enable kokoro
systemctl --user disable kokoro

# Check status and logs
systemctl --user status kokoro
journalctl --user -u kokoro -f
```

## Integration with VoiceMode

VoiceMode automatically detects Kokoro when available:

1. **First**: Checks for Kokoro on `http://127.0.0.1:8880/v1`
2. **Fallback**: Uses OpenAI API (requires `OPENAI_API_KEY`)

### Custom Configuration

To use a different endpoint or specify a voice:

```bash
export TTS_BASE_URL=http://127.0.0.1:8880/v1
export TTS_VOICE=af_sky  # Optional: specify voice
```

Or in MCP configuration:
```json
"voicemode": {
  ...
  "env": {
    "TTS_BASE_URL": "http://127.0.0.1:8880/v1",
    "TTS_VOICE": "af_sky"
  }
}
```

## Fully Local Setup

For completely offline voice processing, combine Kokoro with Whisper:

```bash
export TTS_BASE_URL=http://127.0.0.1:8880/v1  # Kokoro for TTS
export STT_BASE_URL=http://127.0.0.1:2022/v1  # Whisper for STT
export TTS_VOICE=af_sky                       # Kokoro voice
```

## Service Files

### macOS LaunchAgent

Create `~/Library/LaunchAgents/com.voicemode.kokoro.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uvx</string>
        <string>kokoro-fastapi[cpu]</string>
        <string>serve</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8880</string>
        <string>--models-dir</string>
        <string>/Users/YOUR_USERNAME/Models/kokoro</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

### Linux Systemd Service

Create `~/.config/systemd/user/kokoro.service`:

```ini
[Unit]
Description=Kokoro Text-to-Speech Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/uvx kokoro-fastapi[cpu] serve \
    --host 127.0.0.1 \
    --port 8880 \
    --models-dir %h/Models/kokoro
Restart=always
RestartSec=10
Environment="PATH=/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
```

## Performance

Kokoro runs locally on your machine:
- **Generation time**: 1-3 seconds for short phrases
- **CPU usage**: Moderate, depends on text length
- **Memory**: ~500MB-1GB depending on loaded models
- **Disk space**: ~300MB per language model

For better performance:
- Use CPU version for most systems: `kokoro-fastapi[cpu]`
- GPU version available for CUDA-enabled systems
- Adjust cache directory to SSD for faster access

## Troubleshooting

### Service Won't Start
- Check if port 8880 is already in use: `lsof -i :8880`
- Verify uvx is installed: `which uvx`
- Check Python version: `python3 --version` (requires 3.8+)

### Models Not Found
- Ensure models directory exists and has correct permissions
- Models download automatically on first request
- Manual download: https://huggingface.co/hexgrad/Kokoro-82M

### Voice Not Working
- Verify service is running: `curl http://127.0.0.1:8880/v1/models`
- Check logs for errors (see service management commands)
- Try a different voice to rule out model issues

### Performance Issues
- Ensure adequate CPU resources are available
- Consider using a smaller text chunk size
- Check disk I/O if models are on slow storage

## File Locations

- **Models**: `~/Models/kokoro/` or `~/.voicemode/services/kokoro/models/`
- **Cache**: `~/.voicemode/cache/kokoro/`
- **Service Files**:
  - macOS: `~/Library/LaunchAgents/com.voicemode.kokoro.plist`
  - Linux: `~/.config/systemd/user/kokoro.service`
- **Installation**: `~/.voicemode/kokoro-fastapi/`
