# Whisper Speech-to-Text Service

Local speech recognition service that converts audio to text for voice-mode using OpenAI's Whisper model.

## Quick Start

```bash
# macOS
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Linux
systemctl --user start whisper
```

Default endpoint: `http://127.0.0.1:2022/v1`

## Install

### macOS
```bash
# Install whisper.cpp
brew install whisper.cpp

# Download model
mkdir -p ~/.voicemode/models/whisper
cd ~/.voicemode/models/whisper
curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin
```

### Linux
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

## Configure

Environment variables in `~/.voicemode.env`:

```bash
VOICEMODE_WHISPER_MODEL=large-v2
VOICEMODE_WHISPER_PORT=2022
VOICEMODE_WHISPER_LANGUAGE=auto
VOICEMODE_WHISPER_MODEL_PATH=~/.voicemode/models/whisper
```

### LaunchAgent (macOS)

Create `~/Library/LaunchAgents/com.voicemode.whisper.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.whisper</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/whisper-server</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>2022</string>
        <string>--model</string>
        <string>/Users/YOUR_USERNAME/.voicemode/models/whisper/ggml-large-v2.bin</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

### Systemd Service (Linux)

Create `~/.config/systemd/user/whisper.service`:

```ini
[Unit]
Description=Whisper Speech-to-Text Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/whisper-server \
    --host 0.0.0.0 \
    --port 2022 \
    --model %h/.voicemode/models/whisper/ggml-large-v2.bin
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

## Control

### macOS Commands

```bash
# Start service
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Stop service  
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Restart service
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Enable at startup
launchctl load -w ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Disable at startup
launchctl unload -w ~/Library/LaunchAgents/com.voicemode.whisper.plist

# Check status
launchctl list | grep whisper
```

### Linux Commands

```bash
# Start service
systemctl --user start whisper

# Stop service
systemctl --user stop whisper  

# Restart service
systemctl --user restart whisper

# Enable at startup
systemctl --user enable whisper

# Disable at startup
systemctl --user disable whisper

# Check status
systemctl --user status whisper

# View logs
journalctl --user -u whisper -f
```

## Troubleshooting

### Service won't start
- Check if port 2022 is already in use: `lsof -i :2022`
- Verify model file exists at configured path
- Check logs for error messages

### Poor transcription quality
- Try a larger model (base → small → medium → large)
- Ensure audio input quality is good
- Set specific language instead of 'auto' if known

### High CPU usage
- Use a smaller model for better performance
- Consider using GPU acceleration if available