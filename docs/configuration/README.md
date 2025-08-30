# Voice Mode Configuration

This directory contains configuration documentation for Voice Mode.

## Quick Links

- **[Configuration Reference](configuration-reference.md)** - Comprehensive list of all configuration options
- **[Environment Variables Example](voicemode.env.example)** - Shell export format for sourcing in bash
- **[Voice Preferences](voice-preferences.md)** - Unified .voicemode.env configuration system
- **[Selecting Voices Guide](../guides/selecting-voices.md)** - How to choose and configure voices
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

**Configure voice preferences:**
```bash
export VOICEMODE_VOICES="af_sky,nova,alloy"  # Try Kokoro first, fallback to OpenAI
```

**Enable simple failover (recommended):**
```bash
export VOICEMODE_SIMPLE_FAILOVER=true  # Try endpoints in order without health checks
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

To change this behavior, see the [Configuration Reference](configuration-reference.md).

## Configuration System

Voice Mode uses a cascading configuration system that searches for `.voicemode.env` files similar to how Claude Code searches for CLAUDE.md files.

### File Discovery Order

Voice Mode searches for configuration files in this order:

1. **Project-level** (walks up from current directory):
   - `.voicemode.env` (in project root)
   - `.voicemode/voicemode.env` (in .voicemode directory)
2. **Global** (in user's home directory):
   - `~/.voicemode/voicemode.env` (primary global configuration)

Configuration cascades with earlier files taking precedence. Environment variables always take highest priority.

### Configuration File Format

Configuration files use simple `KEY=value` format (not shell exports):

```bash
# Voice preferences
VOICEMODE_VOICES=af_sky,nova,alloy
VOICEMODE_DEBUG=true
VOICEMODE_SAVE_AUDIO=false
```

### Using the Configuration System

1. **Global setup** - Voice Mode automatically creates `~/.voicemode/voicemode.env` on first run:
   ```bash
   uvx voice-mode  # Creates ~/.voicemode/voicemode.env
   ```

2. **Project-specific setup** - Create `.voicemode.env` in your project:
   ```bash
   # In your project directory
   echo "VOICEMODE_VOICES=af_sky,shimmer" > .voicemode.env
   ```

3. **Configuration precedence** - Earlier files override later ones:
   - Environment variables (highest priority)
   - Project `.voicemode.env` files (searched up directory tree)  
   - Global `~/.voicemode/voicemode.env`
   - Built-in defaults (lowest priority)

### Managing Configuration

Use the MCP configuration tools for runtime management:
- `config_reload()` - Reload configuration from all files
- `show_config_files()` - View which files are being loaded  
- `update_config()` - Update specific settings

### Legacy Configuration Support

1. Run Voice Mode once to generate the default configuration:
   ```bash
   uvx voice-mode
   ```

2. Edit the generated configuration file:
   ```bash
   vim ~/.voicemode/.voicemode.env  # or your preferred editor
   ```

3. The file will be automatically loaded on next run. Environment variables always take precedence over file settings.

### Using Environment Variables

You can also set configuration via environment variables:

1. Set variables in your current shell:
   ```bash
   export OPENAI_API_KEY="your-key"
   export VOICEMODE_DEBUG=true
   ```

2. Or use the shell export example file:
   ```bash
   cp docs/configuration/voicemode.env.example ~/.voicemode.env.sh
   source ~/.voicemode.env.sh
   ```

3. Or add to your shell RC file for persistence:
   ```bash
   echo "export OPENAI_API_KEY='your-key'" >> ~/.bashrc  # or ~/.zshrc
   ```
