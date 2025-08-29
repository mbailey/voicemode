# Voice Mode Integration: Continue

> 🔗 **Official Documentation**: [Continue Documentation](https://continue.dev/docs)  
> 📦 **Download/Install**: [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Continue.continue)  
> 🏷️ **Version Requirements**: Continue v0.8.0+, VS Code v1.90+

## Overview

Continue is an open-source AI assistant for VS Code and JetBrains IDEs. Voice Mode enhances Continue with natural voice conversations, enabling hands-free coding assistance and verbal interactions with any LLM.

## Prerequisites

- [ ] VS Code installed
- [ ] Continue extension installed
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Install Continue from VS Code marketplace
# Configure Voice Mode in config.json
# Use Cmd+M and voice commands
```

## Installation Steps

### 1. Install Continue

1. Open VS Code
2. Go to Extensions (Cmd+Shift+X or Ctrl+Shift+X)
3. Search for "Continue"
4. Click Install on the extension by Continue

### 2. Configure Continue for Voice Mode

**Configuration File Location:**
- **macOS**: `~/.continue/config.json`
- **Linux**: `~/.continue/config.json`
- **Windows**: `%USERPROFILE%\.continue\config.json`

**Add Voice Mode to Continue configuration:**

```json
{
  "models": [
    {
      "title": "Your existing model config",
      "provider": "openai",
      "model": "gpt-4"
    }
  ],
  "contextProviders": [
    {
      "name": "voice-mode",
      "params": {
        "command": "uvx",
        "args": ["voice-mode"],
        "env": {
          "OPENAI_API_KEY": "your-openai-key"
        }
      }
    }
  ],
  "slashCommands": [
    {
      "name": "voice",
      "description": "Have a voice conversation",
      "params": {
        "command": "uvx",
        "args": ["voice-mode", "converse"],
        "env": {
          "OPENAI_API_KEY": "your-openai-key"
        }
      }
    }
  ]
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

1. **Check Continue Configuration:**
   - Open Continue sidebar (Cmd+M or Ctrl+M)
   - Click settings icon
   - Verify voice-mode is in context providers

2. **Test Voice Mode:**
   - Open Continue chat (Cmd+M or Ctrl+M)
   - Type: "/voice let's talk"
   - Try saying: "Hello, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
In Continue chat:
/voice
You: "Explain this function"
Continue: [Speaks the explanation]
```

### Voice-Driven Code Generation
```
/voice generate code
You: "Create a React component for a todo list"
Continue: [Explains and generates code verbally]
```

### Interactive Debugging
```
Select code, then:
/voice debug this
You: "Why is this throwing an error?"
Continue: [Analyzes and explains verbally]
```

## Troubleshooting

### Voice Mode Not Available
- Check Continue's `config.json` for proper formatting
- Ensure Voice Mode is in contextProviders or slashCommands
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for VS Code
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### Continue Not Loading Voice Mode
- Check Continue logs: View → Output → Continue
- Ensure `uvx` is installed and in PATH
- Try running `uvx voice-mode` manually

## Platform-Specific Notes

### macOS
- Grant microphone permissions to VS Code
- Continue may need additional file system permissions

### Linux
- Install PulseAudio or PipeWire for audio support
- May need: `sudo apt-get install portaudio19-dev` (Debian/Ubuntu)

### Windows
- Native Windows support requires WSL2
- Run VS Code from WSL2 for best results

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # In terminal
   uvx voice-mode kokoro-start
   ```

2. **Update config.json:**
   ```json
   {
     "slashCommands": [
       {
         "name": "voice",
         "description": "Have a voice conversation",
         "params": {
           "command": "uvx",
           "args": ["voice-mode", "converse"],
           "env": {
             "OPENAI_API_KEY": "your-key",
             "VOICEMODE_TTS_BASE_URLS": "http://127.0.0.1:8880/v1,https://api.openai.com/v1",
             "VOICEMODE_STT_BASE_URLS": "http://127.0.0.1:2022/v1,https://api.openai.com/v1"
           }
         }
       }
     ]
   }
   ```

### LiveKit Integration

For room-based voice conversations:
- Configure LiveKit in environment variables
- Useful for collaborative debugging sessions

### Custom LLM + Voice

Continue supports any LLM provider:
- Use voice with local models (Ollama, etc.)
- Combine voice with custom model configurations
- Create voice-enabled workflows for any LLM

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../configuration.md)
- 🎤 [Local STT/TTS Setup](../whisper.md)
- 🏠 [LiveKit Integration](../livekit/README.md)
- 💬 [Continue Documentation](https://continue.dev/docs)
- 🐛 [Troubleshooting Guide](../troubleshooting/README.md)
- 💻 [Continue GitHub](https://github.com/continuedev/continue)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)