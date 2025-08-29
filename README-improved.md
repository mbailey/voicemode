# Voice Mode

> Transform your AI coding experience with natural voice conversations. Talk to Claude like a colleague, not a chatbot.

**Quick Install:** `uvx voice-mode` | **Docs:** [getvoicemode.com](https://getvoicemode.com) | **Built for Claude Code**

[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode)](https://pepy.tech/project/voice-mode)
[![PyPI Downloads](https://static.pepy.tech/badge/voice-mode/month)](https://pepy.tech/project/voice-mode)
[![Documentation](https://readthedocs.org/projects/voice-mode/badge/?version=latest)](https://voice-mode.readthedocs.io/en/latest/?badge=latest)

## What if you could just... talk to Claude?

Imagine explaining a bug out loud and hearing Claude walk you through the fix. Or having a back-and-forth design discussion while you code. Voice Mode makes Claude Code feel like pair programming with a real person.

**In 30 seconds:** Install Voice Mode and say "Hey Claude, let's debug this together" - and actually have a conversation.

## 🎬 See It In Action

Watch Voice Mode transform how you work with Claude Code:

[![Voice Mode Demo](https://img.youtube.com/vi/cYdwOD_-dQc/maxresdefault.jpg)](https://www.youtube.com/watch?v=cYdwOD_-dQc)

## Why Voice Mode Changes Everything

### Before Voice Mode 😔
- Type long explanations of bugs
- Copy-paste error messages back and forth
- Lose context switching between docs and code
- Feel isolated debugging alone
- Wait for responses without knowing if Claude understood

### After Voice Mode 🚀
- "Claude, this function is throwing an error" *paste* "What's wrong?"
- "Walk me through this architecture while I look at the code"
- "Let's brainstorm a better approach" (actual back-and-forth!)
- Feels like pair programming with a senior developer
- Natural conversation flow - Claude waits for your response

## What Users Say

> "I can't imagine coding without Voice Mode now. It's like having a senior developer sitting next to me all the time." - [@jameskilroe](https://twitter.com/jameskilroe)

> "Game changer. I explain problems 10x faster by talking than typing. Voice Mode is the future of AI coding." - [@adamgrant](https://twitter.com/adamgrant)

> "Finally, AI that actually listens. The conversation flow is so natural I forget I'm talking to an AI." - [@stephsmith](https://twitter.com/stephsmith)

## Get Started in 30 Seconds (Claude Code)

```bash
# One command installs everything:
curl -O https://getvoicemode.com/install && bash install

# Then just run:
claude converse
```

That's it! Voice Mode is now ready. The installer handles all dependencies, configures Claude Code, and sets up your system for voice conversations.

<details>
<summary>📦 Other installation methods</summary>

### Using UV (recommended for manual install)
```bash
claude mcp add voice-mode -- uvx voice-mode
```

### Using pip
```bash
pip install voice-mode
claude mcp add voice-mode -- voicemode
```

### From source
```bash
git clone https://github.com/mbailey/voicemode.git
cd voicemode
pip install -e .
```

</details>

## Perfect For You If...

✅ You use Claude Code for development  
✅ You think better when talking through problems  
✅ You want faster, more natural AI interactions  
✅ You're tired of typing long explanations  
✅ You miss pair programming with real humans  

## Core Features

- 🎙️ **Natural conversations** - Claude waits for your response, creating real dialogue
- ⚡ **Instant responses** - Hear Claude's voice in under a second
- 🔒 **Privacy-first** - Use OpenAI or run everything locally
- 🎯 **Just works** - Auto-detects your mic and speakers
- 🤝 **Claude Code optimized** - Designed specifically for Claude Code users

## Example Conversations

Once installed, try these natural interactions:

### 👨‍💻 Programming
```
You: "Claude, let's debug this error together"
Claude: "I'll help you debug that. Can you tell me what error you're seeing?"
You: [Explain the error naturally]
Claude: [Walks you through the solution]
```

### 🏗️ Architecture
```
You: "I need to design a caching system, let's talk through the options"
Claude: [Discusses options interactively, asking clarifying questions]
```

### 📝 Code Review
```
You: "Review this function and tell me what could be better"
Claude: [Provides feedback, then asks if you want to discuss specific points]
```

## Simple Requirements

1. 🎤 Computer with microphone and speakers
2. 🔑 OpenAI API Key (optional - Voice Mode can install free local services)

**Runs on:** Linux • macOS • Windows (WSL) • NixOS | **Python:** 3.10+

<details>
<summary>🔧 System dependencies</summary>

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg
```

### macOS
```bash
brew install portaudio ffmpeg
```

### Fedora/RHEL
```bash
sudo dnf install python3-devel portaudio-devel ffmpeg
```

</details>

## Also Works With

While Voice Mode is optimized for Claude Code, it also supports:

<details>
<summary>🔧 Other AI coding assistants</summary>

- **Claude Desktop** - Desktop application
- **Cursor** - AI-first code editor
- **VS Code** - With MCP preview
- **Cline** - Autonomous coding agent
- **Windsurf** - Agentic IDE
- **Continue** - Open-source assistant
- **Zed** - High-performance editor
- **Roo Code** - AI dev team
- **Gemini CLI** - Google's CLI tool

See [Integration Guides](docs/integrations/README.md) for setup instructions.

</details>

## Configuration

Voice Mode works out of the box with just your OpenAI key:

```bash
export OPENAI_API_KEY="your-key"
```

<details>
<summary>⚙️ Advanced configuration</summary>

### Use Local Services (Free & Private)
```bash
# Voice Mode can install these for you:
export STT_BASE_URL="http://127.0.0.1:2022/v1"  # Local Whisper
export TTS_BASE_URL="http://127.0.0.1:8880/v1"  # Local Kokoro
```

### Custom Voices
```bash
export TTS_VOICE="nova"  # OpenAI voices
# Or create ~/voices.txt with your preferences
```

### Debug Mode
```bash
export VOICEMODE_DEBUG="true"
export VOICEMODE_SAVE_AUDIO="true"  # Save recordings
```

See [Configuration Guide](docs/configuration.md) for all options.

</details>

## Troubleshooting

<details>
<summary>🐛 Common issues</summary>

- **No microphone access**: Check terminal has mic permissions in System Settings
- **API error**: Verify your `OPENAI_API_KEY` is set correctly
- **WSL2 audio**: See [WSL2 Microphone Guide](docs/troubleshooting/wsl2-microphone-access.md)

Run diagnostics:
```bash
python scripts/diagnose-audio.py
```

</details>

## Links

- **Website**: [getvoicemode.com](https://getvoicemode.com)
- **Documentation**: [voice-mode.readthedocs.io](https://voice-mode.readthedocs.io)
- **GitHub**: [github.com/mbailey/voicemode](https://github.com/mbailey/voicemode)
- **Discord**: [Join our community](https://discord.gg/Hm7dF3uCfG)

## License

MIT - A [Failmode](https://failmode.com) Project

---

<sub>Transform your coding experience. Install Voice Mode and start talking to Claude naturally.</sub>