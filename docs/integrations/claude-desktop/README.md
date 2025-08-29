# Voice Mode Integration: Claude Desktop

> 🔗 **Official Website**: [Claude.ai](https://claude.ai)  
> 📦 **Download**: [Download Claude Desktop](https://claude.ai/download)  
> 🏷️ **Version Requirements**: Claude Desktop with MCP support

## Overview

Claude Desktop is Anthropic's official desktop application for Claude. Voice Mode enhances Claude Desktop by adding natural voice conversation capabilities through the Model Context Protocol (MCP).

## Prerequisites

- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../../README.md#system-dependencies))

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-openai-key"

# Claude Desktop will use uvx to run Voice Mode on-demand
# No separate installation needed!
```

## Installation Steps

### 1. Install Claude Desktop

**Download and install from:** https://claude.ai/download

- **macOS**: Download the .dmg file and drag to Applications
- **Windows**: Download the installer and run it
- **Linux**: Available as AppImage or through package managers

### 2. Configure Claude Desktop

**Configuration File Location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

**Add Voice Mode Configuration:**

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

**Example Configuration Files:**
- [`uvx.json`](./uvx.json) - Using uvx (recommended)
- [`pip-install.json`](./pip-install.json) - Using pip installation
- [`python-m.json`](./python-m.json) - Using python -m
- [`livekit.json`](./livekit.json) - With LiveKit support

### 3. Restart Claude Desktop

After saving the configuration, restart Claude Desktop for changes to take effect.

## Verification

1. **Check MCP Server Status:**
   - Open Claude Desktop
   - Look for the MCP icon (puzzle piece) in the interface
   - Click it to see connected servers
   - "voice-mode" should be listed

2. **Test Voice Mode:**
   - In Claude Desktop, type: "Let's have a voice conversation"
   - You should hear Claude speak and the app will listen for your response
   - Try saying: "Hello Claude, can you hear me?"

## Usage Examples

### Basic Voice Conversation
```
Type in Claude Desktop:
"Let's talk about this project"
"Can you help me debug this issue using voice?"
"Tell me about best practices for React"
```

### Voice-Enabled Coding
```
"Read this code and explain what it does"
"Help me refactor this function"
"What tests should I write for this component?"
```

## Environment Variables

Since Claude Desktop uses the configuration file, you have two options:

**Option 1: Set in config file (shown above)**
- Pros: Self-contained, no system setup needed
- Cons: API key is stored in plain text

**Option 2: Inherit from system**
```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"]
      // No env section - inherits from system
    }
  }
}
```
Then set in your shell: `export OPENAI_API_KEY="your-key"`

## Troubleshooting

### Voice Mode Not Available
- Ensure Claude Desktop is fully restarted after config changes
- Check the MCP servers list in Claude Desktop
- Verify the config file is valid JSON (no trailing commas!)

### No Audio
- Grant Claude Desktop microphone permissions in system settings
- Check system audio input/output devices
- Try running with debug: Add `"VOICEMODE_DEBUG": "true"` to env

### MCP Connection Failed
- Ensure `uv` is installed and in your PATH
- Try running `uvx voice-mode --help` in terminal to verify
- Check Claude Desktop logs: Help → View Logs

## Platform-Specific Notes

### macOS
- Grant microphone permissions: System Settings → Privacy & Security → Microphone → Claude
- May need to restart Claude Desktop after granting permissions

### Windows
- Run as Administrator if you encounter permission issues
- Windows Defender may prompt when first using microphone

### Linux
- May need to add user to `audio` group: `sudo usermod -a -G audio $USER`
- Check PulseAudio/PipeWire is running

## Advanced Configuration

### Using Local STT/TTS Services

For complete privacy, use local services:

```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "VOICEMODE_TTS_BASE_URL": "http://127.0.0.1:8880/v1",
        "VOICEMODE_STT_BASE_URL": "http://127.0.0.1:2022/v1"
      }
    }
  }
}
```

### Alternative Installation Method

If you prefer to install Voice Mode permanently:
```bash
pip install voice-mode
```

Then update config to use the installed version:
```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "voice-mode"
    }
  }
}
```

## See Also

- 📚 [Voice Mode Documentation](../../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Local STT/TTS Setup](../../kokoro.md)
- 💬 [Claude Desktop Documentation](https://support.anthropic.com/claude-desktop)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG)