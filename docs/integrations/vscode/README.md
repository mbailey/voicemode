# Voice Mode Integration: VS Code

> 🔗 **Official Documentation**: [VS Code Documentation](https://code.visualstudio.com/docs)  
> 📦 **Download/Install**: [Get VS Code](https://code.visualstudio.com/download)  
> 🏷️ **Version Requirements**: VS Code v1.99+ (with MCP preview feature)

## Overview

Visual Studio Code is a popular open-source code editor from Microsoft. With the MCP preview feature in v1.99+, Voice Mode brings natural voice conversations to VS Code, enabling hands-free coding and verbal interactions with AI assistants.

## Prerequisites

- [ ] VS Code v1.99+ installed
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Enable MCP in VS Code settings
# Configure Voice Mode in .vscode/mcp.json
# Use Copilot Chat with voice commands
```

## Installation Steps

### 1. Install VS Code

**Download and install from:** https://code.visualstudio.com/download

- **macOS**: Download the .zip file and move to Applications
- **Linux**: Use package manager or download .deb/.rpm package  
- **Windows**: Download the installer and run

### 2. Enable MCP Preview Feature

1. Open VS Code Settings (Cmd+, or Ctrl+,)
2. Search for "chat.mcp.enabled"
3. Enable the checkbox for "Chat: Mcp: Enabled"
4. Restart VS Code

### 3. Configure VS Code for Voice Mode

**Configuration File Location:**
Create a `.vscode/mcp.json` file in your workspace root or user settings:

**Add Voice Mode to MCP servers:**

```json
{
  "servers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key"
      },
      "type": "stdio"
    }
  }
}
```

**Note:** Using `uvx` means Voice Mode will be downloaded and run on-demand. No separate installation required!

### 4. Restart VS Code

After saving the configuration and enabling MCP, restart VS Code for changes to take effect.

### 5. Environment Variables (Optional)

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
   - Open Command Palette (Cmd+Shift+P or Ctrl+Shift+P)
   - Search for "Developer: Show Running Extensions"
   - Verify MCP servers are loaded

2. **Test Voice Mode:**
   - Open VS Code
   - Open Copilot Chat (if available)
   - Type: "@voice-mode talk to me"
   - Try saying: "Hello, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
In Copilot Chat:
@voice-mode "Let's have a voice conversation"
You: "What does this code do?"
AI: [Speaks the explanation]
```

### Voice-Enabled Coding
```
@voice-mode "Help me refactor this function using voice"
You: "Make this function async"
AI: [Explains changes verbally while showing code]
```

## Troubleshooting

### Voice Mode Not Available
- Ensure MCP is enabled in VS Code settings (chat.mcp.enabled)
- Check that `.vscode/mcp.json` exists and is valid JSON
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for VS Code
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### MCP Feature Not Available
- Ensure you have VS Code v1.99 or higher
- Check that the MCP preview feature is enabled
- Try using VS Code Insiders if stable version doesn't have it yet

## Platform-Specific Notes

### macOS
- Grant microphone permissions to VS Code when prompted
- Code Helper processes may also need microphone access

### Linux
- Install PulseAudio or PipeWire for audio support
- May need: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)

### Windows
- Native Windows support requires WSL2
- For best results, run VS Code from WSL2

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In VS Code terminal
   uvx voice-mode kokoro-start
   ```

2. **Configure endpoints in `.vscode/mcp.json`:**
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
- Configure LiveKit server in environment variables
- Useful for collaborative coding sessions with voice

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../configuration.md)
- 🎤 [Local STT/TTS Setup](../whisper.md)
- 🏠 [LiveKit Integration](../livekit/README.md)
- 💬 [VS Code MCP Documentation](https://code.visualstudio.com/docs/mcp)
- 🐛 [Troubleshooting Guide](../troubleshooting/README.md)
- 💻 [VS Code Official Docs](https://code.visualstudio.com/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)