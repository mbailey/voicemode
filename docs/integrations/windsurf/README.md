# Voice Mode Integration: Windsurf

> 🔗 **Official Documentation**: [Windsurf Documentation](https://docs.codeium.com/windsurf)  
> 📦 **Download/Install**: [Get Windsurf](https://codeium.com/windsurf)  
> 🏷️ **Version Requirements**: Windsurf v1.0.0+

## Overview

Windsurf is an AI-powered IDE by Codeium that provides intelligent code completion and AI assistance. Voice Mode enhances Windsurf with natural voice conversations, enabling hands-free coding and verbal interactions with Codeium's AI models.

## Prerequisites

- [ ] Windsurf installed and configured
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Configure Voice Mode in Windsurf settings
# Use Cascade with voice commands for AI-powered coding
```

## Installation Steps

### 1. Install Windsurf

**Download and install from:** https://codeium.com/windsurf

- **macOS**: Download the .dmg file and drag to Applications
- **Linux**: Download the AppImage or .deb package  
- **Windows**: Download the installer and run

### 2. Configure Windsurf for Voice Mode

**Configuration File Location:**
- **macOS**: `~/Library/Application Support/Windsurf/User/mcp.json`
- **Linux**: `~/.config/Windsurf/User/mcp.json`
- **Windows**: `%APPDATA%\Windsurf\User\mcp.json`

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

### 3. Restart Windsurf

After saving the configuration, restart Windsurf for changes to take effect.

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
   - Open Windsurf Settings
   - Navigate to Extensions or MCP configuration
   - Look for "voice-mode" in active servers

2. **Test Voice Mode:**
   - Open Windsurf
   - Open Cascade or AI Chat panel
   - Type: "Let's talk with voice"
   - Try saying: "Hello, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
In Cascade:
"Enable voice mode"
You: "What's the best way to implement this feature?"
Cascade: [Responds verbally with suggestions]
```

### Voice-Driven Code Generation
```
"Generate code using voice"
You: "Create a Python class for user authentication"
Cascade: [Explains approach verbally while generating code]
```

### Interactive Debugging
```
"Debug with voice"
You: "Why is this function returning null?"
Cascade: [Analyzes and explains verbally]
```

## Troubleshooting

### Voice Mode Not Available
- Ensure Voice Mode is configured in `mcp.json`
- Check that MCP servers are enabled in Windsurf
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for Windsurf
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### MCP Server Connection Issues
- Check Windsurf logs for MCP errors
- Ensure `uvx` is installed and accessible
- Try running `uvx voice-mode` manually

## Platform-Specific Notes

### macOS
- Grant microphone permissions to Windsurf
- May need to allow permissions for Windsurf Helper processes

### Linux
- Install PulseAudio or PipeWire for audio support
- May need: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)

### Windows
- Native Windows support may require additional configuration
- Consider using WSL2 for better compatibility

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In Windsurf terminal
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
- Configure LiveKit server details
- Enable collaborative voice coding sessions

### Codeium AI + Voice Mode

Combine Windsurf's AI capabilities with voice:
- Voice-directed code completion
- Verbal code reviews with Codeium
- Natural language refactoring requests

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Local STT/TTS Setup](../../whisper.md)
- 🏠 [LiveKit Integration](../../livekit/README.md)
- 💬 [Windsurf Documentation](https://docs.codeium.com/windsurf)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)
- 💻 [Codeium Official Site](https://codeium.com/)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)