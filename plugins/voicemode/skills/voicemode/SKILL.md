---
name: voicemode
description: This skill provides voice interaction capabilities for AI assistants. This skill should be used when users mention "voice mode", "voicemode", "speak to me", "talk to me", "have a voice conversation", "converse", ask to "check voice service status", "start Whisper", "start Kokoro", ask about "voice configuration", mention "STT", "TTS", "speech-to-text", "text-to-speech", or need help with "voice setup", "voice troubleshooting", or "voice preferences".
---

# VoiceMode

Voice interaction capabilities for Claude Code - enabling natural conversations through speech-to-text (STT) and text-to-speech (TTS) services.

## Naming Clarification

There are two related names to be aware of:

| Name | What it is | Example usage |
|------|------------|---------------|
| `voicemode` | CLI command (no hyphen) | `voicemode whisper service status` |
| `voice-mode` | Python package on PyPI (with hyphen) | `uvx voice-mode-install` |

**Check if CLI is installed:**
```bash
which voicemode       # Should show path like ~/.local/bin/voicemode
voicemode --version   # Should show version number
```

**If not installed:**
```bash
# Option 1: Install permanently
uv tool install voice-mode

# Option 2: Run without installing (uses uvx)
uvx voice-mode <command>   # Equivalent to: voicemode <command>
```

## When to Use MCP Tools vs CLI

| Use Case | Recommended | Why |
|----------|-------------|-----|
| Voice conversations | MCP (`voicemode:converse`) | Faster - MCP server already running |
| Service management | CLI (`voicemode service`) | Works without MCP server |
| Installation | CLI (`voice-mode-install`) | One-time setup |
| Model management | CLI (`voicemode whisper model`) | Administrative task |
| Configuration | CLI (`voicemode config`) | Edit settings directly |

## Claude Code Plugin

VoiceMode is available as a Claude Code plugin from the marketplace:

```bash
# Install from marketplace
/plugin marketplace add mbailey/voicemode
/plugin install voicemode
```

The plugin provides:
- **MCP Server** - Full voice capabilities via `voicemode-mcp`
- **Slash Commands** - `/voicemode:converse`, `/voicemode:status`, etc.
- **Hooks** - Sound feedback during tool execution

After installing the plugin, install voice services:
```bash
/voicemode:install
```

For detailed plugin documentation, see `docs/guides/claude-code-plugin.md` in the voicemode repo.

## Quick Start

When a user wants to use voice mode for the first time, guide them through these steps:

### 1. Check Service Status

First, check if voice services are already running:

```python
# Check STT service (Whisper)
voicemode:service("whisper", "status")

# Check TTS service (Kokoro)
voicemode:service("kokoro", "status")
```

### 2. Install Services if Needed

If services aren't installed, guide the user to install them:

**Prerequisites:**
- FFmpeg (required for audio processing)
- Python 3.11+ (for VoiceMode installation)

**Installation:**

```bash
# Install VoiceMode with UV (recommended)
uvx voice-mode-install --yes
```

This installs the VoiceMode package and CLI. It does NOT install local speech services.

#### Local Voice Services (Apple Silicon Recommended)

**When to offer local services:**
- On Apple Silicon Macs, local services are highly recommended - they provide privacy, speed, and work offline
- Check architecture with: `uname -m` (arm64 = Apple Silicon)
- If Apple Silicon, ask the user: "Would you like to install local voice services? This provides faster, private, offline voice capabilities."

**Get informed consent before installing:**

Tell the user what will be downloaded:

| Service | Download Size | Disk Space | First Start Time |
|---------|---------------|------------|------------------|
| Whisper (tiny) | ~75MB | ~150MB | 30 seconds |
| Whisper (base) | ~150MB | ~300MB | 1-2 minutes |
| Whisper (small) | ~460MB | ~1GB | 2-3 minutes |
| Kokoro TTS | ~350MB | ~700MB | 2-3 minutes |

**Recommended setup for most users:** Whisper base + Kokoro = ~500MB download, ~1GB disk space.

After user consents, install services:

```bash
# Install Whisper for local STT (base model recommended)
voicemode whisper service install

# Install Kokoro for local TTS
voicemode kokoro install
```

Services auto-start after installation and are configured to start on login.

**First Run - Model Downloads:**

When services start for the first time, they download AI models. The first `converse` call may be slow while models load. Subsequent starts are instant.

**Check Model Download Progress:**

```bash
# Whisper model location - check if download complete
ls -lh ~/.voicemode/services/whisper/models/

# Kokoro model location
ls -lh ~/.voicemode/services/kokoro/models/

# Watch service logs during download
voicemode whisper service logs -f
voicemode kokoro logs -f
```

**Choose a Different Whisper Model:**

```bash
# Smaller/faster (good for testing)
voicemode whisper install --model tiny    # ~75MB

# Larger/more accurate
voicemode whisper install --model small   # ~460MB
voicemode whisper install --model medium  # ~1.5GB
```

### 3. Start Your First Conversation

Once services are running, start a voice conversation:

```python
# Simple greeting
voicemode:converse("Hello! I'm ready to talk. What would you like to discuss?")

# The tool will:
# - Speak the message using TTS
# - Listen for the user's response
# - Return the transcribed text
```

That's it! You're now in a voice conversation.

## Core Capabilities

### Voice Conversations

The `converse` tool is your primary interface for voice interactions:

```python
# Basic usage - speak and listen
voicemode:converse("How can I help you today?")

# Speak without waiting for response (for narration)
voicemode:converse("Let me search for that information", wait_for_response=False)

# With specific voice
voicemode:converse(
    message="I found the answer",
    voice="nova",
    tts_provider="openai"
)
```

**Key Parameters:**
- `message` (required): Text to speak
- `wait_for_response` (default: true): Whether to listen for user response
- `voice`: TTS voice name (auto-selected if not specified)
- `tts_provider`: "openai" or "kokoro" (auto-selected based on availability)
- `listen_duration_max`: Maximum listening time in seconds (default: 120)

### Service Management

Manage voice services using the `service` tool:

```python
# Check status
voicemode:service("whisper", "status")
voicemode:service("kokoro", "status")

# Start/stop services
voicemode:service("whisper", "start")
voicemode:service("kokoro", "stop")
voicemode:service("whisper", "restart")

# View logs for troubleshooting
voicemode:service("whisper", "logs", lines=50)
```

**Available Services:**
- `whisper`: Local STT using Whisper.cpp
- `kokoro`: Local TTS with multiple voices
- `livekit`: Room-based real-time communication (advanced)

**Service Actions:**
- `status`: Check if running and resource usage
- `start`: Start the service
- `stop`: Stop the service
- `restart`: Restart the service
- `logs`: View recent logs
- `enable`: Configure to start at boot/login
- `disable`: Remove from startup

## Common Workflows

### Having a Voice Conversation

**Pattern 1: Question and Answer**

```python
# Ask a question
voicemode:converse("What would you like to work on today?")
# User responds via voice
# Response text is returned for you to process

# Continue the conversation
voicemode:converse("Great! Let me help you with that.")
```

**Pattern 2: Narrating Actions (Default Behavior)**

When performing actions, speak without waiting to create natural flow:

```python
# Announce action without waiting
voicemode:converse("Let me search the codebase for that", wait_for_response=False)

# Perform the action in parallel
Grep(pattern="function_name", path="/path/to/code")

# Announce results
voicemode:converse("I found 5 matches. Would you like me to show them?")
```

**Pattern 3: Step-by-Step Guidance**

When asking questions in voice mode:
- Ask one question at a time
- Wait for the answer before proceeding
- Keep questions clear and concise

```python
# Good - one question at a time
voicemode:converse("Would you like to use local or cloud TTS?", wait_for_response=True)
# Wait for answer...
voicemode:converse("Should I install Kokoro for you?", wait_for_response=True)

# Avoid - multiple questions bundled together
# This is overwhelming in voice conversations
```

### Checking and Troubleshooting Setup

**Check if everything is working:**

```python
# Check service status
voicemode:service("whisper", "status")
voicemode:service("kokoro", "status")

# If services aren't running, start them
voicemode:service("whisper", "start")
voicemode:service("kokoro", "start")
```

**Using CLI for diagnostics:**

```bash
# Check all dependencies
voicemode deps

# Diagnostic information
voicemode diag info
voicemode diag devices  # List audio devices
voicemode diag registry # Show provider registry

# View service logs
voicemode whisper service logs
voicemode kokoro logs
```

### Managing Voice Preferences

**Voice Selection:**

Available voices depend on your TTS provider:

**OpenAI Voices:** alloy, echo, fable, onyx, nova, shimmer
**Kokoro Voices:** Multiple voices (check with `voicemode kokoro voices`)

**Configuration:**

```bash
# View current configuration
voicemode config list

# Set default voice
voicemode config set VOICEMODE_TTS_VOICE nova

# Set default provider
voicemode config set VOICEMODE_TTS_PROVIDER kokoro

# Edit full configuration
voicemode config edit
```

**Project and User Preferences:**
- Project-level: `.voicemode` file in project root
- User-level: `~/.voicemode` file in home directory
- System config: `~/.voicemode/config/config.yaml`

## Provider Options

VoiceMode supports both cloud and local voice services. You can use either or both.

### OpenAI API (Cloud)

If `OPENAI_API_KEY` is set, VoiceMode can use OpenAI's cloud services:
- **STT**: OpenAI Whisper API
- **TTS**: OpenAI voices (alloy, echo, fable, onyx, nova, shimmer)

This works without installing local services - just set the API key.

### Local Services

For privacy, speed, and offline use, install local services:

| Service | Port | Purpose |
|---------|------|---------|
| Whisper | 2022 | Speech-to-text (STT) |
| Kokoro | 8880 | Text-to-speech (TTS) |

### Provider Priority

VoiceMode automatically selects providers based on availability:
1. If local services are running, they're used by default (faster, private)
2. If local services aren't available, falls back to OpenAI API (if key is set)
3. You can override with `tts_provider` and `stt_provider` parameters

### Checking Provider Status

```bash
# Check what providers are available
voicemode diag registry

# Check specific service ports
nc -z localhost 2022 && echo "Whisper running" || echo "Whisper not running"
nc -z localhost 8880 && echo "Kokoro running" || echo "Kokoro not running"
```

## Advanced Topics

### Provider System Details

VoiceMode uses OpenAI-compatible endpoints for all services, enabling seamless switching between providers.

The system automatically:
- Discovers available providers
- Performs health checks
- Fails over to working providers
- Negotiates audio formats

### Audio Processing

**Requirements:**
- FFmpeg for format conversion
- WebRTC VAD for voice activity detection

**Supported Formats:**
- PCM, MP3, WAV, FLAC, AAC, Opus

**Configuration Options:**
- `disable_silence_detection`: Keep listening even during silence
- `vad_aggressiveness`: 0-3 (default: 2) - how strict voice detection is
- `listen_duration_min`: Minimum recording time before silence detection (default: 2.0s)
- `speed`: Speech rate 0.25-4.0 (default: 1.0)
- `chime_enabled`: Enable/disable audio feedback chimes

### Batching Voice Announcements with Audio

When playing audio files, you can batch multiple announcements and playback commands. Tools execute sequentially within the batch:

```python
# Batch announce-play sequences
voicemode:converse("Chapter 1 - Introduction", wait_for_response=False)
Bash(command="mpv --start=00:00 --length=3 song.mp3")
voicemode:converse("Chapter 2 - Main Theme", wait_for_response=False)
Bash(command="mpv --start=00:10 --length=5 song.mp3")
```

This creates natural narration with audio playback.

### Environment Variables

Configure VoiceMode behavior:

- `VOICEMODE_TTS_VOICE`: Default TTS voice
- `VOICEMODE_TTS_PROVIDER`: Default TTS provider (openai, kokoro)
- `VOICEMODE_STT_PROVIDER`: Default STT provider
- `VOICEMODE_AUDIO_FORMAT`: Audio format preference
- `VOICEMODE_DEBUG`: Enable debug logging

### Logging and Debugging

VoiceMode maintains logs in `~/.voicemode/`:

**Log Structure:**
- `logs/conversations/`: Daily conversation transcripts
- `logs/events/`: Operational events and errors
- `audio/`: Saved audio recordings
- `config/`: Configuration files

**Enable Debug Mode:**

```bash
# Via environment variable
export VOICEMODE_DEBUG=true

# Via CLI flag
voicemode converse --debug

# Via MCP parameter
voicemode:converse(message="Test", debug=True)
```

## Quick Reference

### Essential MCP Tool Calls

```python
# Start conversation
voicemode:converse("Hello!")

# Speak without waiting
voicemode:converse("Working on it...", wait_for_response=False)

# Check service status
voicemode:service("whisper", "status")
voicemode:service("kokoro", "status")

# Start services
voicemode:service("whisper", "start")
voicemode:service("kokoro", "start")

# View logs
voicemode:service("whisper", "logs", lines=50)
```

### Common CLI Commands

```bash
# Check status
voicemode whisper service status
voicemode kokoro status

# Start services
voicemode whisper service start
voicemode kokoro start

# View logs
voicemode whisper service logs
voicemode kokoro logs

# Configuration
voicemode config list
voicemode config set VOICEMODE_TTS_VOICE nova
voicemode config edit

# Diagnostics
voicemode deps
voicemode diag info
voicemode diag devices
```

### Conversation History Search

VoiceMode logs all exchanges and provides powerful search capabilities to find and replay past conversations.

**Load conversation history into SQLite:**

```bash
# Load all new exchanges since last sync
voicemode history load

# Load all exchanges (ignore last sync)
voicemode history load --all

# Load from specific date
voicemode history load --since 2025-12-01

# Load last 7 days
voicemode history load --days 7
```

**Search conversations:**

```bash
# Full-text search
voicemode history search "minion indirectly"

# Search only agent speech (TTS)
voicemode history search --type tts "hello"

# Search only user speech (STT)
voicemode history search --type stt "hello"

# Search specific date
voicemode history search --date 2025-12-27 "keyword"

# Search and play first result automatically
voicemode history search --play "memorable quote"

# Limit results
voicemode history search --limit 50 "conversation"
```

**Play audio clips:**

```bash
# Play by exchange ID (from search results)
voicemode history play ex_abc123def456
```

**Search Features:**
- Full-text search using SQLite FTS5 (fast, supports complex queries)
- Filter by type (stt/tts), date, or conversation
- Audio files automatically resolved from timestamp
- Incremental loading - won't duplicate already-loaded exchanges
- All conversations stored in `~/.voicemode/cache/conversations.db`

**Use Cases:**
- Find memorable moments or important discussions
- Review what was said in past conversations
- Create clips of agent responses for testing
- Debug conversation issues by reviewing exact exchanges

### Token Efficiency Tip

When using CLI commands directly (not MCP tools), redirect STDERR to save tokens:

```bash
# Suppresses FFmpeg warnings and debug output
voicemode converse -m "Hello" 2>/dev/null

# Omit when debugging
voicemode converse -m "Hello"  # Shows all diagnostic info
```

This only applies to Bash tool calls - MCP tools handle this automatically.

## Best Practices

1. **Use parallel operations**: Speak without waiting when narrating actions
2. **One question at a time**: Don't bundle multiple questions in voice mode
3. **Check status first**: Always verify services are running before starting conversations
4. **Let VoiceMode auto-select**: Don't hardcode providers unless user has preference
5. **Use local services**: Whisper and Kokoro provide privacy and speed
6. **Monitor logs**: Check service logs when troubleshooting issues
7. **Set user preferences**: Configure default voice and provider in `~/.voicemode`

## Integration Notes

- VoiceMode runs as an MCP server via stdio transport
- Compatible with Claude Code and other MCP clients
- Supports concurrent instances with audio playback management
- Works with tmux and terminal multiplexers
- Requires microphone access when listening for responses

## Additional Resources

For detailed documentation:
- VoiceMode README: Installation and overview
- `docs/reference/`: Complete API and parameter documentation
- `docs/tutorials/`: Step-by-step guides
- `docs/services/`: Service-specific documentation
- `docs/testing/installer-testing.md`: Installer testing guide for Tart VMs
- VoiceMode CLAUDE.md: Project-specific Claude guidance

## Troubleshooting

**First conversation is slow or times out:**

This is normal on first run - the services are downloading AI models:
1. Check Whisper logs: `voicemode whisper service logs -f`
2. Check Kokoro logs: `voicemode kokoro logs -f`
3. Wait for downloads to complete (2-5 minutes total)
4. Subsequent starts will be instant

**Model not loading:**
1. Check disk space: Models need ~500MB for base+kokoro
2. Verify model files exist: `ls -lh ~/.voicemode/services/whisper/models/`
3. Try reinstalling: `voicemode whisper install --model base`

**Services won't start:**
1. Check FFmpeg is installed: `ffmpeg -version`
2. View service logs: `voicemode:service("whisper", "logs")`
3. Try restart: `voicemode:service("whisper", "restart")`

**Audio quality issues:**
1. Check audio devices: `voicemode diag devices`
2. Adjust VAD aggressiveness: `vad_aggressiveness=1` (more permissive)
3. Review conversation logs in `~/.voicemode/logs/conversations/`

**Conversations not working:**
1. Verify services are running: `voicemode:service("whisper", "status")`
2. Check provider registry: `voicemode diag registry`
3. Enable debug mode to see detailed logs
4. Ensure microphone permissions are granted

**Configuration issues:**
1. List current config: `voicemode config list`
2. Check for environment variable conflicts
3. Review config file: `~/.voicemode/config/config.yaml`
4. Reset to defaults: Remove config file and restart services
