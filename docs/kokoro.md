# Kokoro TTS Setup

Kokoro is a local text-to-speech engine that provides an OpenAI-compatible API. Voice Mode can use it as an alternative to OpenAI's text-to-speech service.

## How Voice Mode Uses Kokoro

Voice Mode automatically checks for local TTS services before falling back to OpenAI:

1. **First**: Checks for Kokoro on `http://127.0.0.1:8880/v1`
2. **Fallback**: Uses OpenAI API (requires `OPENAI_API_KEY`)

## Setting Up Kokoro

### Automatic Installation (Recommended)

Voice Mode includes an installation tool that handles everything for you:

```bash
# Using Claude Code
claude converse "Please install kokoro-fastapi"

# Or programmatically
await install_kokoro_fastapi()
```

This will:
- Clone the kokoro-fastapi repository to `~/.voicemode/kokoro-fastapi`
- Install UV package manager if needed
- Set up a systemd service (Linux) or LaunchAgent (macOS) for automatic startup
- Start the service on port 8880

### Manual Installation

1. Install and run Kokoro following the [official instructions](https://huggingface.co/hexgrad/Kokoro-82M)
2. Ensure it's running on port 8880 with the OpenAI-compatible API
3. Voice Mode will automatically detect and use it

No configuration needed - Voice Mode will use local Kokoro when available!

## Manual Configuration (Optional)

To use a different Kokoro endpoint or force its use:

```bash
export TTS_BASE_URL=http://127.0.0.1:8880/v1
export TTS_VOICE=af_sky  # Optional: specify voice
```

Or add to your MCP configuration:
```json
"voice-mode": {
  "env": {
    "TTS_BASE_URL": "http://127.0.0.1:8880/v1",
    "TTS_VOICE": "af_sky"
  }
}
```

## Available Voices

- `af_sky` - Female, natural voice (default for Kokoro)
- `af_nova` - Female, similar to OpenAI's nova
- `af_sky` - Female, previously removed from OpenAI
- `af_bella` - Female
- `am_adam` - Male
- `am_echo` - Male

## Performance

Kokoro runs locally on your machine, so performance depends on your hardware. Typical generation times are 1-3 seconds for short phrases.

## Service Management

### Linux (systemd)

```bash
# Check status
systemctl --user status kokoro-fastapi-8880

# Start/stop/restart
systemctl --user start kokoro-fastapi-8880
systemctl --user stop kokoro-fastapi-8880
systemctl --user restart kokoro-fastapi-8880

# View logs
journalctl --user -u kokoro-fastapi-8880 -f

# Disable auto-start
systemctl --user disable kokoro-fastapi-8880
```

### macOS (launchd)

```bash
# Check if running
launchctl list | grep kokoro

# Stop/start
launchctl unload ~/Library/LaunchAgents/com.voicemode.kokoro-8880.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro-8880.plist
```
