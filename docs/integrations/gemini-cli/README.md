# Voice Mode Integration: Gemini CLI

> 🔗 **Official Repository**: [Gemini CLI on GitHub](https://github.com/google/generative-ai-js/tree/main/packages/gemini-cli)  
> 📦 **Download/Install**: [npm install -g @google/gemini-cli](https://www.npmjs.com/package/@google/gemini-cli)  
> 🏷️ **Version Requirements**: Gemini CLI v0.1.0+

## Overview

Gemini CLI is Google's command-line interface for their Gemini AI models, offering a Claude Code-like experience with generous free tier (1000 requests/day, 1M token context). Voice Mode enhances Gemini CLI by adding natural voice conversation capabilities, allowing you to speak your coding requests and hear Gemini's responses.

## Prerequisites

- [ ] Gemini CLI installed (`npm install -g @google/gemini-cli`) - [See npm setup guide to avoid sudo](../../npm-global-no-sudo.md)
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service for STT/TTS)
- [ ] System audio dependencies installed ([see main README](../../README.md#system-dependencies))

## Quick Start

```bash
# Install Voice Mode
uvx voice-mode

# Set your OpenAI API key (for voice services)
export OPENAI_API_KEY="your-openai-key"

# Configure Gemini CLI with Voice Mode
gemini-cli config set mcp.voice-mode.command "uvx voice-mode"

# Start voice-enabled Gemini CLI
gemini-cli
```

## Installation Steps

### 1. Install Gemini CLI

> **macOS/Linux Users**: To avoid using sudo with npm, see our [npm setup guide](../../npm-global-no-sudo.md)

```bash
# Install globally via npm
npm install -g @google/gemini-cli

# Configure with your Gemini API key
gemini-cli auth login
```

### 2. Add Voice Mode to Gemini CLI

Find Gemini CLI's configuration file:
- **macOS/Linux**: `~/.gemini/settings.json`
- **Windows**: `%USERPROFILE%\.gemini\settings.json`

Add the Voice Mode MCP server to your existing configuration:
```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": [
        "voice-mode"
      ]
    }
  }
}
```

### 3. Environment Variables (Optional)

For advanced configuration:

```bash
# Required for voice services
export OPENAI_API_KEY="your-key"

# Optional - Use local services
export VOICEMODE_TTS_BASE_URL="http://127.0.0.1:8880/v1"
export VOICEMODE_STT_BASE_URL="http://127.0.0.1:2022/v1"

# Optional - Preferred voice
export VOICEMODE_TTS_VOICE="nova"
```

## Verification

1. **Check Installation:**
   ```bash
   # Verify Gemini CLI
   gemini-cli --version
   
   # Test Voice Mode directly
   uvx voice-mode --help
   ```

2. **Test Voice Mode:**
   ```bash
   # Start Gemini CLI
   gemini-cli
   
   # Try voice commands:
   # "Hello, can you hear me?"
   # "Let's have a voice conversation"
   ```

3. **Verify MCP Connection:**
   - Check Gemini CLI logs for MCP server initialization
   - Look for "voice-mode" in active servers list

## Usage Examples

### Basic Voice Conversation
```
# In Gemini CLI:
"Hey Gemini, let's talk about this code"
"Can you explain this error message?"
"What's the best approach for this feature?"
```

### Voice-Enabled Code Review
```
# Navigate to your project
cd my-project

# Start Gemini CLI
gemini-cli

# Voice commands:
"Review this pull request"
"Suggest improvements for this function"
"Help me write tests for this module"
```

## Troubleshooting

### Voice Mode Not Recognized
- Ensure MCP support is enabled in Gemini CLI
- Check configuration file syntax
- Try running `uvx voice-mode` directly to test

### Audio Issues
- Grant terminal microphone permissions
- Check system audio settings
- Run: `VOICEMODE_DEBUG=true gemini-cli` for detailed logs

### Performance Considerations
- Gemini CLI may be slower than Claude Code
- Voice processing adds ~2-3s latency
- Consider using local STT/TTS for better performance

## Platform-Specific Notes

### macOS
- Grant terminal app microphone access in System Preferences
- Gemini CLI config may be in `~/Library/Application Support/gemini-cli/`

### Linux
- Ensure PulseAudio/PipeWire is running
- Check audio permissions: `groups $USER | grep audio`

### Windows
- Best experience with WSL2
- Native Windows support may have audio limitations

## Advanced Configuration

### Using Local STT/TTS Services

For privacy and offline usage:

1. **Start local services:**
   ```bash
   # Kokoro TTS
   docker run -p 8880:8880 kokoro-tts
   
   # Whisper STT
   whisper-cpp-server -p 2022
   ```

2. **Configure endpoints:**
   ```json
   {
     "env": {
       "VOICEMODE_TTS_BASE_URL": "http://127.0.0.1:8880/v1",
       "VOICEMODE_STT_BASE_URL": "http://127.0.0.1:2022/v1",
       "VOICEMODE_PREFER_LOCAL": "true"
     }
   }
   ```

### Optimizing for Gemini's Context Window

Take advantage of Gemini's 1M token context:
```bash
# Enable verbose mode for large codebases
export VOICEMODE_DEBUG="trace"

# Increase audio duration for longer responses
export VOICEMODE_LISTEN_DURATION="30"
```

## See Also

- 📚 [Voice Mode Documentation](../../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Demo: Voice Mode with Gemini CLI](https://www.youtube.com/watch?v=HC6BGxjCVnM)
- 🏠 [LiveKit Integration](../../livekit/README.md)
- 💬 [Gemini CLI Documentation](https://github.com/google/generative-ai-js)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)
- 🌟 [Gemini API Documentation](https://ai.google.dev/gemini-api/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or post in [r/GeminiCLI](https://reddit.com/r/GeminiCLI)