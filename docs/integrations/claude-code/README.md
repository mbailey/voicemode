# Voice Mode Integration: Claude Code

> 🔗 **Official Documentation**: [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)  
> 📦 **Download/Install**: [npm install -g @anthropic-ai/claude-code](https://www.npmjs.com/package/@anthropic-ai/claude-code)  
> 🏷️ **Version Requirements**: Claude Code v0.1.0+

## Overview

Claude Code is Anthropic's official CLI for Claude that enables powerful AI-assisted coding directly from your terminal. Voice Mode enhances Claude Code by adding natural voice conversation capabilities, allowing you to speak your coding requests and hear Claude's responses.

## Prerequisites

- [ ] Claude Code installed (`npm install -g @anthropic-ai/claude-code`) - [See npm setup guide to avoid sudo](../../npm-global-no-sudo.md)
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Add Voice Mode to Claude Code (user-level)
claude mcp add --scope user voice-mode uvx voice-mode

# Set your OpenAI API key
export OPENAI_API_KEY="your-openai-key"

# Start a voice conversation
claude converse
```

## Installation Steps

### 1. Install Voice Mode

The easiest way is using Claude Code's MCP management:

```bash
# Add at user level (recommended)
claude mcp add --scope user voice-mode uvx voice-mode

# Or add at project level
claude mcp add voice-mode uvx voice-mode
```

### 2. Configure Environment

Claude Code can manage environment variables for you:

```bash
# Add with environment variable
claude mcp add voice-mode --env OPENAI_API_KEY=your-key uvx voice-mode
```

Or set in your shell profile:
```bash
export OPENAI_API_KEY="your-openai-key"
```

### 3. Environment Variables (Optional)

For advanced configuration, you can set these environment variables:

```bash
# Required
export OPENAI_API_KEY="your-key"

# Optional - Use local Kokoro TTS
export VOICEMODE_TTS_BASE_URL="http://127.0.0.1:8880/v1"
export VOICEMODE_TTS_VOICE="af_sky"

# Optional - Use local Whisper STT
export VOICEMODE_STT_BASE_URL="http://127.0.0.1:2022/v1"

# Optional - Debug mode
export VOICEMODE_DEBUG="true"
```

## Verification

1. **Check Installation:**
   ```bash
   # List installed MCP servers
   claude mcp list
   ```

2. **Test Voice Mode:**
   ```bash
   # Start Claude Code
   claude
   
   # In Claude, try:
   # "Let's have a voice conversation"
   # "Can you hear me?"
   ```

3. **Verify MCP Connection:**
   ```bash
   # Check MCP server status
   claude mcp status voice-mode
   ```

## Usage Examples

### Basic Voice Conversation
```bash
# Start Claude Code
claude

# Then in Claude:
"Let's talk about this code"
"Can you explain what this function does?"
"Help me refactor this class"
```

### Voice-Enabled Coding Session
```bash
# Navigate to your project
cd my-project

# Start Claude with voice
claude

# Voice commands:
"Can you help me debug this error?"
"Let's write a test for this function"
"What's the best way to optimize this?"
```

## Troubleshooting

### Voice Mode Not Available
- Run `claude mcp list` to verify Voice Mode is installed
- Check `claude mcp status voice-mode` for errors
- Ensure your OPENAI_API_KEY is set: `echo $OPENAI_API_KEY`

### No Audio Input/Output
- Check terminal has microphone permissions (macOS System Preferences)
- Run audio diagnostics: `python scripts/diagnose-audio.py`
- Try setting `VOICEMODE_DEBUG=true` for detailed logs

### MCP Server Errors
- Update Claude Code: `npm update -g @anthropic-ai/claude-code`
- Reinstall Voice Mode: `claude mcp remove voice-mode && claude mcp add voice-mode uvx voice-mode`
- Check logs: `claude --debug`

## Platform-Specific Notes

### macOS
- Grant terminal microphone access in System Preferences > Privacy & Security
- May need to restart terminal after granting permissions

### Linux
- Ensure PulseAudio or PipeWire is running
- May need to add user to `audio` group: `sudo usermod -a -G audio $USER`

### Windows
- Native Windows support requires WSL2
- Follow [WSL2 audio setup guide](../../troubleshooting/wsl2-microphone-access.md)

## Advanced Configuration

### Using Local STT/TTS Services

To use local services for complete privacy:

1. **Start Kokoro TTS:**
   ```bash
   # Using Claude Code
   claude "start kokoro"
   
   # Or manually
   uvx kokoro-tts serve
   ```

2. **Configure Voice Mode:**
   ```bash
   claude mcp add voice-mode \
     --env VOICEMODE_TTS_BASE_URL=http://127.0.0.1:8880/v1 \
     --env VOICEMODE_STT_BASE_URL=http://127.0.0.1:2022/v1 \
     uvx voice-mode
   ```

### LiveKit Integration

For room-based voice conversations:

1. Set up LiveKit credentials
2. Configure in Claude Code:
   ```bash
   claude mcp add voice-mode \
     --env LIVEKIT_URL=wss://your-app.livekit.cloud \
     --env LIVEKIT_API_KEY=your-key \
     --env LIVEKIT_API_SECRET=your-secret \
     uvx voice-mode
   ```

## See Also

- 📚 [Voice Mode Documentation](../../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Local STT/TTS Setup](../../whisper.md)
- 🏠 [LiveKit Integration](../../livekit/README.md)
- 💬 [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)
- 💻 [Claude Code GitHub](https://github.com/anthropics/claude-code)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check the [FAQ](../../../README.md#troubleshooting)