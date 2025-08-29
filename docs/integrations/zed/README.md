# Voice Mode Integration: Zed

> 🔗 **Official Documentation**: [Zed Documentation](https://zed.dev/docs)  
> 📦 **Download/Install**: [Get Zed](https://zed.dev/download)  
> 🏷️ **Version Requirements**: Zed v0.150.0+

## Overview

Zed is a high-performance, multiplayer code editor built from the ground up for speed and collaboration. Voice Mode enhances Zed with natural voice conversations, perfect for collaborative coding sessions and hands-free development.

## Prerequisites

- [ ] Zed installed and configured
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Configure Voice Mode in Zed settings
# Open Assistant Panel and use voice commands
```

## Installation Steps

### 1. Install Zed

**Download and install from:** https://zed.dev/download

- **macOS**: Download and run the installer (Apple Silicon or Intel)
- **Linux**: Download the AppImage or use the install script  
- **Windows**: Not yet supported (use WSL2 with Linux version)

### 2. Configure Zed for Voice Mode

**Configuration File Location:**
- **macOS**: `~/Library/Application Support/Zed/settings.json`
- **Linux**: `~/.config/zed/settings.json`

**Add Voice Mode to context servers:**

```json
{
  "context_servers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
```

**Note:** Using `uvx` means Voice Mode will be downloaded and run on-demand. No separate installation required!

### 3. Restart Zed

After saving the configuration, restart Zed for changes to take effect.

### 4. Environment Variables (Optional)

For advanced configuration, you can set these environment variables:

```bash
# Required
export OPENAI_API_KEY="your-key"

# Optional - Custom STT/TTS endpoints (comma-separated lists)
export VOICEMODE_TTS_BASE_URLS="http://127.0.0.1:8880/v1,https://api.openai.com/v1"
export VOICEMODE_STT_BASE_URLS="http://127.0.0.1:2022/v1,https://api.openai.com/v1"

# Optional - Voice preferences (comma-separated lists)
export VOICEMODE_TTS_VOICES="af_sky,nova,alloy"
export VOICEMODE_TTS_MODELS="gpt-4o-mini-tts,tts-1-hd,tts-1"
```

## Verification

1. **Check Context Server Status:**
   - Open Zed Settings (Cmd+, or Ctrl+,)
   - Look for context_servers configuration
   - Verify voice-mode is listed

2. **Test Voice Mode:**
   - Open Zed
   - Open Assistant Panel (Cmd+Shift+A or Ctrl+Shift+A)
   - Type: "/voice-mode talk to me"
   - Try saying: "Hello, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
In Assistant Panel:
/voice-mode "Let's have a conversation"
You: "Explain this Rust code"
Assistant: [Speaks the explanation]
```

### Collaborative Voice Coding
```
During a multiplayer session:
/voice-mode "Help us refactor this module"
Team: [Discusses verbally while coding together]
```

## Troubleshooting

### Voice Mode Not Available
- Ensure Voice Mode is configured in `settings.json`
- Check that context_servers section is properly formatted
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for Zed
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### Context Server Not Loading
- Check Zed logs: `~/Library/Logs/Zed/Zed.log` (macOS)
- Ensure `uvx` is installed and in PATH
- Try running `uvx voice-mode` manually to test

## Platform-Specific Notes

### macOS
- Grant microphone permissions to Zed when prompted
- Zed GPU acceleration works best with Metal support

### Linux
- Install PulseAudio or PipeWire for audio support
- May need: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)
- Wayland users may experience better performance than X11

### Windows
- Native Windows support not available yet
- Use WSL2 with the Linux version of Zed

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In terminal
   uvx voice-mode kokoro-start
   ```

2. **Configure endpoints in settings.json:**
   ```json
   {
     "context_servers": {
       "voice-mode": {
         "command": "uvx",
         "args": ["voice-mode"],
         "env": {
           "OPENAI_API_KEY": "your-key",
           "VOICEMODE_TTS_BASE_URLS": "http://127.0.0.1:8880/v1,https://api.openai.com/v1",
           "VOICEMODE_STT_BASE_URLS": "http://127.0.0.1:2022/v1,https://api.openai.com/v1"
         }
       }
     }
   }
   ```

### LiveKit Integration

For room-based voice conversations:
- Perfect for Zed's multiplayer features
- Configure LiveKit in environment variables
- Enable real-time voice collaboration

### Performance Optimization

Zed's high performance pairs well with Voice Mode:
- Local STT/TTS reduces latency
- GPU acceleration improves response times
- Multiplayer + voice enables new workflows

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Local STT/TTS Setup](../../whisper.md)
- 🏠 [LiveKit Integration](../../livekit/README.md)
- 💬 [Zed Context Servers](https://zed.dev/docs/context-servers)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)
- 💻 [Zed Official Docs](https://zed.dev/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)