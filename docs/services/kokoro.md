# Kokoro Text-to-Speech Service

High-quality local text-to-speech service for voice-mode with multiple natural-sounding voices in various languages.

## Quick Start

```bash
# macOS  
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Linux
systemctl --user start kokoro
```

Default endpoint: `http://127.0.0.1:8880/v1`

## Install

### Prerequisites
```bash
# Ensure Python 3.8+ is installed
python3 --version

# Install uvx (if not already installed)
pip install uvx
```

### Download Models
```bash
# Create models directory
mkdir -p ~/Models/kokoro

# Download models (automatic on first run)
# Or manually from: https://huggingface.co/hexgrad/Kokoro-82M
```

## Configure

Environment variables in `~/.voicemode.env`:

```bash
VOICEMODE_KOKORO_PORT=8880
VOICEMODE_KOKORO_MODELS_DIR=~/Models/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro
VOICEMODE_KOKORO_DEFAULT_VOICE=af_sky
```

### LaunchAgent (macOS)

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

### Systemd Service (Linux)

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

## Control

### macOS Commands

```bash
# Start service
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Stop service
launchctl unload ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Restart service  
launchctl unload ~/Library/LaunchAgents/com.voicemode.kokoro.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Enable at startup
launchctl load -w ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Disable at startup
launchctl unload -w ~/Library/LaunchAgents/com.voicemode.kokoro.plist

# Check status
launchctl list | grep kokoro
```

### Linux Commands

```bash
# Start service
systemctl --user start kokoro

# Stop service
systemctl --user stop kokoro

# Restart service
systemctl --user restart kokoro

# Enable at startup  
systemctl --user enable kokoro

# Disable at startup
systemctl --user disable kokoro

# Check status
systemctl --user status kokoro

# View logs
journalctl --user -u kokoro -f
```

## Available Voices

### English
- `af_sky`, `af_sarah` - American Female
- `am_adam`, `am_michael` - American Male  
- `bf_emma`, `bf_isabella` - British Female
- `bm_george`, `bm_lewis` - British Male

### Other Languages
- Spanish: `ef_dora`, `em_alex`
- French: `ff_siwis`, `fm_gabriel`
- Italian: `if_sara`, `im_nicola`
- Portuguese: `pf_dora`, `pm_alex`
- Chinese: `zf_xiaobei`, `zm_yunjian`
- Japanese: `jf_alpha`, `jm_kumo`
- Hindi: `hf_alpha`, `hm_omega`

## Troubleshooting

### Service won't start
- Check if port 8880 is already in use: `lsof -i :8880`
- Verify uvx is installed: `which uvx`
- Check Python version: `python3 --version` (requires 3.8+)

### Models not found
- Ensure models directory exists and has correct permissions
- Models download automatically on first request
- Manual download from: https://huggingface.co/hexgrad/Kokoro-82M

### Performance issues
- Use CPU version for most systems: `kokoro-fastapi[cpu]`
- GPU version available for CUDA-enabled systems
- Adjust cache directory location for faster SSD access