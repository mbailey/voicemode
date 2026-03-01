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
Start the MCP server (stdio transport)
```bash
voicemode
```

### serve
Start the MCP server with HTTP transport for remote access

```bash
voicemode serve [OPTIONS]

Options:
  --host TEXT                  Host to bind to (default: 127.0.0.1)
  -p, --port INTEGER           Port to bind to (default: 8765)
  --transport, -t [streamable-http|sse]
                               Transport protocol to use (default: streamable-http)
  --log-level [debug|info|warning|error]
                               Logging level (default: info)
  --allow-anthropic / --no-allow-anthropic
                               Allow Anthropic IP ranges (160.79.104.0/21)
  --allow-tailscale / --no-allow-tailscale
                               Allow Tailscale IP range (100.64.0.0/10)
  --allow-ip CIDR              Add custom CIDR to allowlist (repeatable)
  --allow-local / --no-allow-local
                               Allow localhost connections (default: true)
  --secret SECRET              Require secret path segment for access
  --token TOKEN                Require Bearer token authentication

Examples:
# Local development with streamable-http (default - localhost only)
voicemode serve

# Explicitly specify streamable-http transport
voicemode serve --transport streamable-http

# Use SSE transport (deprecated - for legacy compatibility)
voicemode serve --transport sse

# Allow Anthropic's Claude.ai and Claude Cowork to connect
voicemode serve --allow-anthropic

# Custom IP allowlist
voicemode serve --allow-ip 192.168.1.0/24 --allow-ip 10.0.0.0/8

# Allow all devices on your Tailscale network
voicemode serve --allow-tailscale

# Strict Anthropic-only mode (no localhost)
voicemode serve --allow-anthropic --no-allow-local

# URL secret authentication (recommended for Claude.ai)
voicemode serve --secret my-secret-uuid

# Bearer token authentication
voicemode serve --token my-secret-token

# Defense in depth: combine IP allowlist + token
voicemode serve --allow-anthropic --token my-secret-token

# SSE with secret path segment (deprecated)
voicemode serve --transport sse --secret my-secret-uuid

# Enable debug logging for troubleshooting
voicemode serve --log-level debug
```

#### Transport Options

The `--transport` option selects the HTTP transport protocol for the MCP server.

**Streamable HTTP (Recommended)**

The `streamable-http` transport is the modern, recommended transport for MCP servers:
- Uses `/mcp` as the base endpoint path
- Better performance and reliability
- Supports bidirectional streaming
- Recommended for all new deployments

Example: `voicemode serve --transport streamable-http` creates endpoint at `http://127.0.0.1:8765/mcp`

**SSE (Deprecated)**

The `sse` (Server-Sent Events) transport is maintained for backward compatibility:
- Uses `/sse` as the base endpoint path
- One-way server-to-client streaming only
- Will show a deprecation warning when used
- Consider migrating to streamable-http

Example: `voicemode serve --transport sse` creates endpoint at `http://127.0.0.1:8765/sse`

**Environment Variable**

You can also set the default transport via environment variable:
```bash
export VOICEMODE_SERVE_TRANSPORT=streamable-http  # or 'sse'
voicemode serve
```

The CLI option takes precedence over the environment variable.

#### Migrating from SSE to Streamable HTTP

If you are currently using SSE transport and want to migrate to streamable-http:

1. **Update your serve command**: Change `--transport sse` to `--transport streamable-http` (or remove it entirely since streamable-http is the default)

2. **Update your client endpoint**: Change the URL path from `/sse` to `/mcp`:
   - Before: `http://your-host:8765/sse`
   - After: `http://your-host:8765/mcp`

3. **If using secret paths**, the structure remains the same:
   - Before: `http://your-host:8765/sse/{secret}`
   - After: `http://your-host:8765/mcp/{secret}`

4. **Test your connection** before deploying to production

#### Security Options

**IP Allowlist**

The `--allow-anthropic` flag adds Anthropic's outbound IP ranges to the allowlist, enabling connections from Claude.ai and Claude Cowork. The `--allow-tailscale` flag adds the Tailscale CGNAT range (100.64.0.0/10), allowing any device on your Tailscale network to connect. Use `--allow-ip` to add custom CIDR ranges.

By default, localhost connections are allowed (`--allow-local`). Use `--no-allow-local` to disable this for strict remote-only access.

**Logging**

The `--log-level` option controls the verbosity of server logs. Available levels are `debug`, `info` (default), `warning`, and `error`. Use `--log-level debug` for troubleshooting connection issues.

**URL Secret Authentication**

The `--secret` option adds a secret path segment to the endpoint URL:
- Endpoint becomes `/{base_path}/{secret}` instead of `/{base_path}`
- Acts as a pre-shared key embedded in the URL
- Returns 404 (not 403) for incorrect paths to avoid revealing endpoint existence
- Ideal for Claude.ai which accepts any URL but doesn't support OAuth

Examples:
- Streamable HTTP: `voicemode serve --secret abc123` creates endpoint at `/mcp/abc123`
- SSE: `voicemode serve --transport sse --secret abc123` creates endpoint at `/sse/abc123`

**Bearer Token Authentication**

The `--token` option requires all requests to include a valid Authorization header:
```
Authorization: Bearer <token>
```

Returns 401 Unauthorized for missing or invalid tokens.

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


## Soundfonts

### soundfonts
Toggle soundfont playback for Claude Code hooks

```bash
# Quick toggle (session-scoped)
voicemode soundfonts off          # Disable immediately
voicemode soundfonts on           # Re-enable

# Persistent config change
voicemode soundfonts on --config  # Enable + update voicemode.env
voicemode soundfonts off --config # Disable + update voicemode.env

# Check current state
voicemode soundfonts status       # Shows sentinel file + env var state
```

The `off` command creates a sentinel file (`~/.voicemode/soundfonts-disabled`) that the hook receiver checks before playing sounds. The `--config` flag also updates `VOICEMODE_SOUNDFONTS_ENABLED` in `~/.voicemode/voicemode.env`.

## Claude Code Integration

### claude hooks
Manage Claude Code hook integration

```bash
# Install hooks
voicemode claude hooks add

# Remove hooks
voicemode claude hooks remove

# List installed hooks
voicemode claude hooks list
```

Hooks connect Claude Code's tool events to VoiceMode's soundfont system. The `add` command registers the hook receiver script with Claude Code's settings.

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