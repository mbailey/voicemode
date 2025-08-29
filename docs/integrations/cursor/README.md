# Voice Mode Integration: Cursor

> 🔗 **Official Documentation**: [Cursor Documentation](https://docs.cursor.com/)  
> 📦 **Download/Install**: [Get Cursor](https://cursor.com/)  
> 🏷️ **Version Requirements**: Cursor v0.8.0+

## Overview

Cursor is an AI-powered code editor built for pair programming with AI. Voice Mode enhances Cursor by enabling natural voice conversations with Claude, allowing you to code hands-free and explain complex ideas naturally.

## Prerequisites

- [ ] Cursor installed and configured
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Configure Cursor for Voice Mode
# Then in Cursor: Cmd+K → "Talk to me"
```

## Installation Steps

### 1. Install Cursor

**Download and install from:** https://cursor.com/

- **macOS**: Download the .dmg file and drag to Applications
- **Linux**: Download the AppImage or .deb package  
- **Windows**: Download the installer and run

### 2. Configure Cursor for Voice Mode

**Configuration File Location:**
- **macOS**: `~/Library/Application Support/Cursor/User/.cursor/mcp.json`
- **Linux**: `~/.config/Cursor/User/.cursor/mcp.json`
- **Windows**: `%APPDATA%\Cursor\User\.cursor\mcp.json`

**Add Voice Mode to MCP servers:**

```json
{
  "mcpServers": {
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

### 3. Restart Cursor

After saving the configuration, restart Cursor for changes to take effect.

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

1. **Check MCP Server Status:**
   - Open Cursor Settings (Cmd+, on macOS)
   - Navigate to the MCP section
   - Look for "voice-mode" in the list of active servers

2. **Test Voice Mode:**
   - Open Cursor
   - Press Cmd+K (macOS) or Ctrl+K (Windows/Linux)
   - Type: "Talk to me" or "Let's have a voice conversation"
   - Try saying: "Hello, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
Cmd+K → "Talk to me"
You: "Can you explain what this function does?"
Claude: [Speaks the explanation]
```

### Voice-Enabled Coding
```
Cmd+K → "Let's work on this code with voice"
You: "Refactor this function to use async/await"
Claude: [Explains the refactoring verbally while showing code]
```

## Troubleshooting

### Voice Mode Not Available
- Ensure Voice Mode is properly configured in `.cursor/mcp.json`
- Check that the file exists in the correct location for your OS
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for Cursor
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### MCP Server Not Starting
- Check Cursor logs: Help → Toggle Developer Tools → Console
- Ensure `uvx` is installed and in your PATH
- Try running `uvx voice-mode` manually to test

## Platform-Specific Notes

### macOS
- Grant microphone permissions when prompted
- If using Cursor from Terminal, ensure Terminal has microphone access

### Linux
- Install PulseAudio or PipeWire for audio support
- May need to run: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)

### Windows
- Native Windows support requires WSL2
- Run Cursor from WSL2 for best compatibility

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In Cursor terminal or system terminal
   uvx voice-mode kokoro-start
   ```

2. **Configure endpoints:**
   ```json
   {
     "mcpServers": {
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
- Configure LiveKit server details in environment variables
- Use "transport": "livekit" in voice commands

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../configuration.md)
- 🎤 [Local STT/TTS Setup](../whisper.md)
- 🏠 [LiveKit Integration](../livekit/README.md)
- 💬 [Cursor MCP Documentation](https://docs.cursor.com/mcp)
- 🐛 [Troubleshooting Guide](../troubleshooting/README.md)
- 💻 [Cursor Official Docs](https://docs.cursor.com/)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)