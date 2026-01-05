# Claude Code Plugin

VoiceMode provides an official plugin for Claude Code that enables voice conversations directly within the CLI.

## What the Plugin Provides

The VoiceMode plugin includes:

- **MCP Server** - Full voice capabilities via the `voicemode-mcp` server
- **Slash Commands** - Quick access to common operations
- **Skill File** - Documentation and usage patterns for Claude
- **Hooks** - Sound feedback during tool execution

## Installation

### From the Plugin Marketplace

The plugin is published to the Claude Code plugin marketplace:

```bash
# Add the marketplace
claude plugin marketplace add https://github.com/mbailey/claude-plugins

# Install the plugin
claude plugin install voicemode@mbailey
```

## Prerequisites

The plugin requires VoiceMode services to be installed and running. After installing the plugin, use the install command:

```bash
/voicemode:install
```

This runs the VoiceMode installer which sets up:

- **Whisper.cpp** - Local speech-to-text
- **Kokoro** - Local text-to-speech
- **FFmpeg** - Audio processing (via Homebrew on macOS)

Or install VoiceMode directly using uv:

```bash
uv tool install voice-mode
voicemode whisper service install
voicemode kokoro install
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/voicemode:install` | Install VoiceMode and dependencies |
| `/voicemode:converse` | Start a voice conversation |
| `/voicemode:status` | Check service status |
| `/voicemode:start` | Start voice services |
| `/voicemode:stop` | Stop voice services |

### Starting a Conversation

```bash
# Start with a greeting
/voicemode:converse Hello, how can I help you today?

# Just start listening
/voicemode:converse
```

### Checking Status

```bash
/voicemode:status
```

Shows whether Whisper (STT) and Kokoro (TTS) services are running and healthy.

## MCP Tools

Once installed, Claude has access to these MCP tools:

- `mcp__voicemode__converse` - Speak and listen for responses
- `mcp__voicemode__service` - Manage voice services

### Converse Tool Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `message` | (required) | Text for Claude to speak |
| `wait_for_response` | true | Listen for user response after speaking |
| `listen_duration_max` | 120 | Maximum recording time (seconds) |
| `voice` | auto | TTS voice name |
| `vad_aggressiveness` | 2 | Voice detection strictness (0-3) |

## Hooks and Soundfonts

The plugin includes a hook receiver that plays sounds during tool execution:

- Sounds play when tools start and complete
- Provides audio feedback during long operations
- Uses configurable soundfonts

Hooks are automatically configured when the plugin is installed.

## Troubleshooting

### Services Not Starting

Check individual service status:

```bash
voicemode whisper service status
voicemode kokoro service status
```

View logs:

```bash
voicemode whisper service logs
voicemode kokoro service logs
```

### No Audio Output

1. Ensure your system audio is working
2. Check that Kokoro service is running
3. Verify FFmpeg is installed: `which ffmpeg`

### Speech Not Recognized

1. Ensure Whisper service is running
2. Check microphone permissions for Terminal/Claude Code
3. Try speaking more clearly or adjusting VAD aggressiveness

## Configuration

VoiceMode respects configuration from `~/.voicemode/voicemode.env`:

```bash
# Default TTS voice
VOICEMODE_TTS_VOICE=nova

# Whisper model (base, small, medium, large)
VOICEMODE_WHISPER_MODEL=base

# Override thread count for Whisper
VOICEMODE_WHISPER_THREADS=4
```

Edit configuration:

```bash
voicemode config edit
```

## Resources

- [VoiceMode Documentation](https://voicemode.ai/docs)
- [GitHub Repository](https://github.com/mbailey/voicemode)
- [Plugin Source](https://github.com/mbailey/voicemode)

## Development

For local development, add the plugin from your local clone:

```bash
# Add plugin from local path
claude plugin marketplace add /path/to/voicemode

# Install the plugin
claude plugin install voicemode@mbailey
```
