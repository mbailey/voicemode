# Voice Mode Configuration

This directory contains configuration documentation for Voice Mode.

## Quick Links

- **[Environment Variables Example](voicemode.env.example)** - Environment variable reference showing defaults and examples
- **[Voice Preferences](voice-preferences.md)** - File-based voice selection system
- **[MCP Environment Precedence](mcp-env-precedence.md)** - How MCP handles environment variables
- **[Integration Guides](../integrations/README.md)** - How to add Voice Mode MCP to your code editor

## Getting Started

Voice Mode MCP has sensible defaults and only needs either:

- An OpenAI API Key (easy)

or

- Local voice services with the following base urls:

  - Whisper: http://localhost:2022/v1
  - TTS:     http://localhost:8880/v1

### Minimal Configuration

The easiest way to get started using Voice Mode MCP is with an [OpenAI API Key](platform.openai.com) for Speech recognitions and Text to Speech:

```bash
export OPENAI_API_KEY="your-api-key"
```

For local-only setups (Kokoro + Whisper), no API key is required however:

- You need to setup and run these services
- It's worth having an OpenAI API Key as a fallback when things fail.

### Common Configurations

**Enable all data saving:**
```bash
export VOICEMODE_SAVE_ALL=true
```

**Debug mode (auto-saves everything):**
```bash
export VOICEMODE_DEBUG=true
```

**Use only local services:**
```bash
export VOICEMODE_TTS_BASE_URLS="http://127.0.0.1:8880/v1"
export VOICEMODE_STT_BASE_URLS="http://127.0.0.1:2022/v1"
```

**Configure Whisper for faster performance:**
```bash
export VOICEMODE_WHISPER_MODEL=base  # Smaller, faster model
export VOICEMODE_WHISPER_LANGUAGE=en  # Skip language detection
```

**Configure Kokoro with custom voice:**
```bash
export VOICEMODE_KOKORO_DEFAULT_VOICE=am_adam  # Male voice
export VOICEMODE_KOKORO_PORT=8888  # Custom port
```

## Directory Structure

Voice Mode stores all data under `~/.voicemode/` by default:

```
~/.voicemode/
├── audio/          # Saved audio recordings
├── transcriptions/ # Saved transcriptions
├── logs/           # Event and debug logs
├── config/         # Configuration files
├── models/         # Model storage
│   ├── whisper/    # Whisper models
│   └── kokoro/     # Kokoro models
└── cache/          # Service caches
    └── kokoro/     # Kokoro cache
```

## Viewing Configuration

Voice Mode provides MCP resources to view current configuration:

- `voice://config/all` - Complete configuration overview
- `voice://config/whisper` - Whisper-specific settings
- `voice://config/kokoro` - Kokoro-specific settings
- `voice://config/env-template` - Environment variable template

## Privacy

By default, Voice Mode prioritizes privacy:
- Audio recordings are NOT saved unless explicitly enabled
- Transcriptions are NOT saved unless explicitly enabled
- Only event logs are saved by default for debugging

To change this behavior, see the [Environment Variables Example](voicemode.env.example) file.

## Using the Environment File

1. Copy the example file to your home directory:
   ```bash
   cp voicemode.env.example ~/.voicemode.env
   ```

2. Edit the file and uncomment/modify the variables you need:
   ```bash
   vim ~/.voicemode.env  # or your preferred editor
   ```

3. Source the file in your shell:
   ```bash
   source ~/.voicemode.env
   ```

4. Or add it to your shell RC file for persistence:
   ```bash
   echo "source ~/.voicemode.env" >> ~/.bashrc  # or ~/.zshrc
   ```
