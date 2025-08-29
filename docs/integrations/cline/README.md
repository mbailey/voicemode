# Voice Mode Integration: Cline

> 🔗 **Official Documentation**: [Cline Documentation](https://github.com/saoudrizwan/claude-dev)  
> 📦 **Download/Install**: [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=saoudrizwan.claude-dev)  
> 🏷️ **Version Requirements**: Cline v2.0.0+, VS Code v1.90+

## Overview

Cline (formerly Claude Dev) is an autonomous AI coding agent that runs in VS Code. Voice Mode enhances Cline by enabling voice-driven autonomous coding sessions, allowing you to direct complex coding tasks through natural conversation.

## Prerequisites

- [ ] VS Code installed
- [ ] Cline extension installed
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Install Cline from VS Code marketplace
# Configure Voice Mode as MCP server
# Start voice-driven coding: "Hey Cline, let's build this feature"
```

## Installation Steps

### 1. Install Cline

1. Open VS Code
2. Go to Extensions (Cmd+Shift+X or Ctrl+Shift+X)
3. Search for "Cline" or "Claude Dev"
4. Click Install on the extension by Saoud Rizwan

### 2. Configure Cline for Voice Mode

**Configuration Location:**
Cline uses VS Code's settings for MCP configuration. Add to your workspace or user settings:

1. Open VS Code Settings (Cmd+, or Ctrl+,)
2. Click the "Open Settings (JSON)" icon
3. Add the following configuration:

```json
{
  "claude-dev.mcpServers": {
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

### 3. Restart VS Code

After saving the configuration, restart VS Code for changes to take effect.

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
   - Open Cline sidebar (click Cline icon in Activity Bar)
   - Look for MCP server indicators
   - Voice Mode should appear in available tools

2. **Test Voice Mode:**
   - Open Cline chat
   - Type: "Let's have a voice conversation"
   - Try saying: "Hello Cline, can you hear me?"

## Usage Examples

### Voice-Driven Autonomous Coding
```
In Cline chat:
"Start voice mode"
You: "Create a REST API with user authentication"
Cline: [Speaks plan, then autonomously implements]
```

### Interactive Voice Debugging
```
"Debug this code with voice"
You: "The login function is failing"
Cline: [Analyzes code verbally, suggests fixes]
```

### Voice-Guided Refactoring
```
"Let's refactor using voice"
You: "Make this code more modular"
Cline: [Explains approach verbally while refactoring]
```

## Troubleshooting

### Voice Mode Not Available
- Check Cline settings for MCP configuration
- Ensure Voice Mode is listed in available MCP servers
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for VS Code
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### Cline Not Responding to Voice
- Ensure Voice Mode MCP server is running
- Check VS Code Developer Tools console for errors
- Try restarting the Cline extension

## Platform-Specific Notes

### macOS
- Grant microphone permissions to VS Code and Code Helper
- Cline may need additional permissions for file system access

### Linux
- Install PulseAudio or PipeWire for audio support
- May need: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)

### Windows
- Native Windows support requires WSL2
- Run VS Code from WSL2 for best compatibility

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In VS Code terminal
   uvx voice-mode kokoro-start
   ```

2. **Configure endpoints in settings:**
   ```json
   {
     "claude-dev.mcpServers": {
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
- Useful for pair programming with voice
- Configure LiveKit details in environment variables

### Autonomous Voice Workflows

Configure Cline to use voice for specific tasks:
- Code reviews with verbal explanations
- Architecture discussions before implementation
- Real-time debugging sessions

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../configuration.md)
- 🎤 [Local STT/TTS Setup](../whisper.md)
- 🏠 [LiveKit Integration](../livekit/README.md)
- 💬 [Cline GitHub Repository](https://github.com/saoudrizwan/claude-dev)
- 🐛 [Troubleshooting Guide](../troubleshooting/README.md)
- 💻 [VS Code MCP Support](https://code.visualstudio.com/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)