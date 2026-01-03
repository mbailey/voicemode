# CLI Command Reference

Complete reference for all VoiceMode command-line interface commands.

## Global Options

```bash
voicemode [OPTIONS] COMMAND [ARGS]...

Options:
  --version   Show the version and exit
  -h, --help  Show this message and exit
  --debug     Enable debug mode and show all warnings
```

## Core Commands

### voicemode (default)
Start the MCP server
```bash
voicemode
```

### converse
Have a voice conversation directly from the command line
```bash
voicemode converse [OPTIONS]

Options:
  --voice TEXT          Override TTS voice
  --model TEXT          Override TTS model
  --debug               Enable debug mode
  --skip-tts            Text-only output
  --timeout INTEGER     Recording timeout in seconds
```

### transcribe
Transcribe audio with optional word-level timestamps

```bash
voicemode transcribe [OPTIONS]

Options:
  --timestamps     Include word-level timestamps
  --output TEXT    Output file path (default: stdout)
  --format TEXT    Output format: text, json, vtt, srt

Examples:
echo "Hello" | voicemode transcribe
voicemode transcribe < audio.wav
voicemode transcribe --timestamps < recording.wav
```

## Diagnostic Commands

### diag
Diagnostic tools for voicemode

```bash
voicemode diag [OPTIONS] COMMAND [ARGS]...

Commands:
  dependencies  Check system audio dependencies and provide installation guidance
  devices       List available audio input and output devices  
  info          Show voicemode installation information
  registry      Show voice provider registry with all discovered endpoints
```

## Service Management

### whisper
Manage Whisper STT service

```bash
# Installation and setup
voicemode whisper install [--model MODEL]
voicemode whisper uninstall

# Service control
voicemode whisper start
voicemode whisper stop
voicemode whisper restart
voicemode whisper status

# Service management
voicemode whisper enable    # Start at boot
voicemode whisper disable   # Don't start at boot

# Model management
voicemode whisper models                    # List available models
voicemode whisper model active             # Show active model
voicemode whisper model active MODEL       # Set active model
voicemode whisper model install MODEL      # Install specific model
voicemode whisper model remove MODEL       # Remove model

# Logs and debugging
voicemode whisper logs [--follow]
```

Available models:
- tiny, tiny.en (39 MB)
- base, base.en (142 MB)
- small, small.en (466 MB)
- medium, medium.en (1.5 GB)
- large-v1, large-v2, large-v3 (2.9-3.1 GB)
- large-v3-turbo (1.6 GB)

### kokoro
Manage Kokoro TTS service

```bash
# Installation and setup
voicemode kokoro install
voicemode kokoro uninstall

# Service control
voicemode kokoro start
voicemode kokoro stop
voicemode kokoro restart
voicemode kokoro status

# Service management
voicemode kokoro enable
voicemode kokoro disable

# Information
voicemode kokoro voices     # List available voices
voicemode kokoro logs [--follow]
```

### livekit
Manage LiveKit RTC service

```bash
# Installation and setup
voicemode livekit install
voicemode livekit uninstall [--remove-all-data]

# Service control
voicemode livekit start
voicemode livekit stop
voicemode livekit restart
voicemode livekit status

# Service management
voicemode livekit enable
voicemode livekit disable

# Configuration
voicemode livekit update    # Update service files
voicemode livekit logs [--follow]
```


## Configuration Commands

### config
Manage voicemode configuration

```bash
# Show current configuration
voicemode config show

# Initialize default config
voicemode config init

# Test configuration
voicemode config test

# Edit configuration
voicemode config edit
```

## Conversation Management

### exchanges
Manage and view conversation exchange logs

```bash
# View recent exchanges
voicemode exchanges

# View specific exchange
voicemode exchanges show EXCHANGE_ID

# Clear exchange logs
voicemode exchanges clear
```

## Utility Commands

### version
Show Voice Mode version and check for updates

```bash
voicemode version

# Check for updates
voicemode version --check
```

### update
Update Voice Mode to the latest version

```bash
voicemode update

# Update to specific version
voicemode update --version 2.3.0

# Force update even if up-to-date
voicemode update --force
```

### completions
Generate or install shell completion scripts

```bash
# Install completions for your shell
voicemode completions install

# Generate completion script for specific shell
voicemode completions bash
voicemode completions zsh
voicemode completions fish
```

## Environment Variables

Commands respect environment variables for configuration:

```bash
# Use specific API key
OPENAI_API_KEY=sk-... voicemode converse

# Enable debug mode
VOICEMODE_DEBUG=true voicemode

# Use local services
VOICEMODE_TTS_BASE_URLS=http://localhost:8880/v1 voicemode converse
```

## Exit Codes

- 0: Success
- 1: General error
- 2: Command line syntax error
- 3: Service not running
- 4: Service already running
- 5: Permission denied
- 127: Command not found

## Examples

### Basic Usage
```bash
# Start MCP server
voicemode

# Have a conversation
voicemode converse

# Transcribe audio file
voicemode transcribe < recording.wav
```

### Service Setup
```bash
# Full local setup
voicemode whisper install
voicemode kokoro install
voicemode whisper enable
voicemode kokoro enable
```

### Development
```bash
# Debug mode with all saves
VOICEMODE_DEBUG=true VOICEMODE_SAVE_ALL=true voicemode converse

# Test local changes
uvx --from . voicemode

# Check diagnostics
voicemode diag info
voicemode diag dependencies
```

### Troubleshooting
```bash
# Check what's running
voicemode whisper status
voicemode kokoro status

# View logs
voicemode whisper logs --follow
voicemode kokoro logs --follow

# Check registry and providers
voicemode diag registry

# Restart services
voicemode whisper restart
voicemode kokoro restart
```