# Voice Mode Integration: [TOOL NAME]

> 🔗 **Official Documentation**: [Tool Name Documentation](https://example.com/docs)  
> 📦 **Download/Install**: [Get Tool Name](https://example.com/download)  
> 🏷️ **Version Requirements**: Tool Name v1.0.0+

## Overview

Brief description of [Tool Name] and how Voice Mode enhances it with natural voice conversations.

## Prerequisites

- [ ] [Tool Name] installed and configured
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Quick command to get started
[tool-specific-command] voice-mode
```

## Installation Steps

### 1. Install [Tool Name]

**Download and install from:** [Installation URL]

- **macOS**: [Platform-specific instructions]
- **Linux**: [Platform-specific instructions]  
- **Windows**: [Platform-specific instructions]

### 2. Configure [Tool Name] for Voice Mode

**Configuration File Location:**
- **macOS**: `~/path/to/config`
- **Linux**: `~/.config/path/to/config`
- **Windows**: `%APPDATA%\Path\To\Config`

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

### 3. Restart [Tool Name]

After saving the configuration, restart [Tool Name] for changes to take effect.

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
   - [Tool-specific way to check MCP servers are loaded]
   - Look for "voice-mode" in the list of active servers

2. **Test Voice Mode:**
   - Open [Tool Name]
   - [Specific steps to trigger Voice Mode]
   - Try saying: "Hello, can you hear me?"


## Usage Examples

### Basic Voice Conversation
```
[Example interaction or command]
```

### Voice-Enabled Coding
```
[Example of using voice while coding]
```

## Troubleshooting

### Voice Mode Not Available
- Ensure Voice Mode is properly configured in [config file]
- Check that MCP servers are enabled in [Tool Name]
- Verify your OPENAI_API_KEY is set correctly

### No Audio Input/Output
- Check system audio permissions for [Tool Name]
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Ensure microphone is not muted

### [Tool-Specific Issue]
- [Solution steps]

## Platform-Specific Notes

### macOS
- [Any macOS-specific configuration or issues]

### Linux
- [Any Linux-specific configuration or issues]

### Windows
- [Any Windows-specific configuration or issues]
- Note: Native Windows support requires WSL2

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for privacy:

1. **Start Kokoro TTS:**
   ```bash
   # Tool-specific command if different
   ```

2. **Configure endpoints:**
   ```json
   {
     "env": {
       "VOICEMODE_TTS_BASE_URLS": "http://127.0.0.1:8880/v1,https://api.openai.com/v1",
       "VOICEMODE_STT_BASE_URLS": "http://127.0.0.1:2022/v1,https://api.openai.com/v1"
     }
   }
   ```

### LiveKit Integration

For room-based voice conversations:
- [Tool-specific LiveKit setup if applicable]

## See Also

- 📚 [Voice Mode Documentation](../../README.md)
- 🔧 [Configuration Reference](../configuration.md)
- 🎤 [Local STT/TTS Setup](../whisper.md)
- 🏠 [LiveKit Integration](../livekit/README.md)
- 💬 [Tool Name MCP Documentation](https://example.com/mcp-docs)
- 🐛 [Troubleshooting Guide](../troubleshooting/README.md)
- 💻 [Tool Name Official Docs](https://example.com/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../README.md#troubleshooting)