# VoiceMode Configuration Guide

VoiceMode provides flexible configuration through environment variables and configuration files, following standard precedence rules while maintaining sensible defaults.

*Note: The Python package is called `voice-mode` but the preferred command is `voicemode`.*

## Quick Start

VoiceMode works out of the box with minimal configuration:

### With Cloud Voice Services
```bash
# Just need an OpenAI API key
export OPENAI_API_KEY="your-api-key"
```

### With Local Voice Services
```bash
# Install local services
voicemode service install kokoro
voicemode service install whisper

# Enable auto-start at boot/login
voicemode service enable kokoro
voicemode service enable whisper

# VoiceMode auto-detects them!
```

### Hybrid Setup (Recommended)
```bash
# Use local services with cloud fallback
export OPENAI_API_KEY="your-api-key"  # Fallback
# Local services auto-detected when running
```

## Configuration System

### Configuration Precedence

VoiceMode follows standard configuration precedence (highest to lowest):

1. **Command line flags** - Always win
2. **Environment variables** - Override config files
3. **Project config** - `./voicemode.env` in current directory
4. **User config** - `~/.voicemode/voicemode.env`
5. **Auto-discovered services** - Running local services
6. **Built-in defaults** - Sensible fallbacks

### Configuration Files

VoiceMode automatically creates `~/.voicemode/voicemode.env` on first run with basic settings. This file uses shell export format:

```bash
# ~/.voicemode/voicemode.env example
export OPENAI_API_KEY="sk-..."
export VOICEMODE_VOICES="af_sky,nova"
export VOICEMODE_DEBUG=false
```

### MCP Configuration

When used as an MCP server, add to your Claude or other MCP client configuration:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "uvx",
      "args": ["--refresh", "voice-mode"],
      "env": {
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## Configuration Reference

### API Keys and Authentication

```bash
# OpenAI API Key (for cloud TTS/STT)
OPENAI_API_KEY=sk-...

# LiveKit credentials (for room-based voice)
LIVEKIT_API_KEY=devkey          # Default for local dev
LIVEKIT_API_SECRET=secret        # Default for local dev
```

### Voice Services

#### Text-to-Speech (TTS)

```bash
# TTS Service URLs (comma-separated, tried in order)
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1,https://api.openai.com/v1

# Voice preferences (comma-separated)
# OpenAI: alloy, echo, fable, onyx, nova, shimmer
# Kokoro: af_sky, af_sarah, am_adam, bf_emma, etc.
VOICEMODE_VOICES=af_sky,nova,alloy

# TTS Models (comma-separated)
# OpenAI: tts-1, tts-1-hd, gpt-4o-mini-tts
VOICEMODE_TTS_MODELS=tts-1-hd,tts-1

# Default TTS voice and model
VOICEMODE_TTS_VOICE=nova
VOICEMODE_TTS_MODEL=tts-1-hd

# Speech speed (0.25 to 4.0)
VOICEMODE_TTS_SPEED=1.0
```

#### Speech-to-Text (STT)

```bash
# STT Service URLs
VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1,https://api.openai.com/v1

# Whisper configuration
VOICEMODE_WHISPER_MODEL=large-v2    # Model size
VOICEMODE_WHISPER_LANGUAGE=auto     # Language detection
VOICEMODE_WHISPER_PORT=2022         # Server port
```

### Audio Configuration

```bash
# Audio formats
VOICEMODE_AUDIO_FORMAT=pcm          # Global default
VOICEMODE_TTS_AUDIO_FORMAT=pcm      # TTS-specific
VOICEMODE_STT_AUDIO_FORMAT=mp3      # STT-specific

# Supported formats: pcm, opus, mp3, wav, flac, aac

# Quality settings
VOICEMODE_OPUS_BITRATE=32000        # Opus bitrate (bps)
VOICEMODE_MP3_BITRATE=64k           # MP3 bitrate
VOICEMODE_AAC_BITRATE=64k           # AAC bitrate
VOICEMODE_SAMPLE_RATE=24000         # Sample rate (Hz)
```

### Audio Feedback

```bash
# Chimes when recording starts/stops
VOICEMODE_AUDIO_FEEDBACK=true
VOICEMODE_FEEDBACK_STYLE=whisper    # or "shout"

# Silence around chimes (for Bluetooth)
VOICEMODE_CHIME_PRE_DELAY=1.0   # Seconds before
VOICEMODE_CHIME_POST_DELAY=0.5  # Seconds after
```

### Voice Activity Detection

```bash
# VAD Aggressiveness (0-3)
# 0: Least aggressive (captures more)
# 3: Most aggressive (filters more)
VOICEMODE_VAD_AGGRESSIVENESS=3

# Silence detection
VOICEMODE_SILENCE_THRESHOLD=3.0     # Seconds of silence
VOICEMODE_MIN_RECORDING_TIME=0.5    # Minimum recording
VOICEMODE_MAX_RECORDING_TIME=120.0  # Maximum recording
```

### Multi-Agent Voice

When running multiple voice agents (e.g. separate Claude Code sessions in
different tmux panes), the "conch" mechanism serialises speech so only one
agent talks at a time, and `VOICEMODE_AUTO_FOCUS_PANE` can visually follow
the speaker.

```bash
# Auto-focus tmux pane when an agent starts speaking (default: false)
# Switches tmux focus to the speaking agent's pane *after* conch acquisition,
# so agents waiting on the conch never steal focus. Respects the focus-hold
# sentinel written by show-me (~/.voicemode/focus-hold) so a shown file is
# not yanked away. Silent no-op outside tmux.
VOICEMODE_AUTO_FOCUS_PANE=false

# Override the default focus-hold duration if the sentinel file has no
# explicit value (default: 30 seconds)
VOICEMODE_FOCUS_HOLD_SECONDS=30

# Conch coordination (serialises speech across agents)
VOICEMODE_CONCH_ENABLED=true
VOICEMODE_CONCH_TIMEOUT=60           # Seconds to wait for the conch
VOICEMODE_CONCH_CHECK_INTERVAL=0.5   # Polling interval
VOICEMODE_CONCH_LOCK_EXPIRY=300      # Stale-lock expiry (0 disables)
VOICEMODE_CONCH_REMOTE_TTL=90        # Heartbeat TTL (s) for a REMOTE MCP waiter
VOICEMODE_CONCH_MCP_WAIT_CAP=25      # Hard cap (s) on a blocking MCP conch wait
```

#### The waiter queue: visibility, fairness, and overrides

When `converse` finds the conch busy, what happens next is controlled by two
independent knobs:

- **`wait_for_conch`** is the *gate*. Left at its default (`false`), a busy
  `converse` returns **immediately** with a status that names the holder and
  notes you are *not* queued — it never silently blocks a caller who didn't opt
  in. Set it `true` (or to a number of seconds) to join the queue and block
  until your turn.

There is no separate "delivery mode" to choose any more (**VM-2078** removed
`conch_mode`/`VOICEMODE_CONCH_MODE` and the `callback` mode they selected —
see "Removed: callback mode" below). Every `converse` waiter now blocks and
polls the same way; if you don't want to hold your turn open, **background**
the call instead — that gives you callback's one real advantage (not tying up
a turn) without discarding your message or depending on a fragile tmux nudge.

Two properties the queue buys you over the old blind poll-and-block:

- **Visibility** — a waiting `converse` shows up in `voicemode conch status`
  as a queued waiter (with its mode and position), instead of polling silently
  where no one can see it.
- **Fairness** — the floor is handed out in FIFO order via a *grant hint*: when
  the holder releases, only the next-in-line is allowed to acquire, so several
  waiters can't thunder in and race for it. WAIT honours the grant; it does not
  steal ahead of the head.

The deliberate counterweight to fairness is **operator override**:
`voicemode conch give <session>` hands the floor to a chosen waiter (jumping the
line), and `voicemode conch bump` drops the current holder and promotes the
head. These are the intentional "line-cutting" escape hatches — godmode for when
strict FIFO is the wrong answer. (A grantee can even `give` onward to another
waiter, chaining the hand-off.)

#### Remote agents: the MCP `conch` tool

Agents on a **streamable-HTTP** voicemode server have no access to the host's
`~/.voicemode/` conch files, so they reach the same queue through the MCP
`conch` tool — the second of two equal front ends alongside the CLI (both share
one implementation in `voice_mode/conch_ops.py`, so `give`/`bump`/`release`
issued over MCP mutate the *same* state the CLI does). One composite tool with
an `action` arg mirrors the CLI verbs:

- `conch(action="status")` — holder + ordered queue (no session needed).
- `conch(action="queue", session_id=…)` — **the recommended way to join when
  busy, and the only timeout-safe way a remote agent can hold a place** (see
  below). Registers and returns your position immediately; you discover your
  grant on your next `heartbeat`/`status` call (register-and-**poll**, not a
  push — see "Removed: callback mode"). *(`action="callback"` was renamed to
  `action="queue"` in VM-2078 — it was never a real callback: nothing rang you
  back, it was register-and-poll all along. The literal string `"callback"`
  still resolves, but only to an error naming `"queue"` as the replacement.)*
- `conch(action="wait", session_id=…, timeout=…)` — block until your turn,
  **hard-capped** by `VOICEMODE_CONCH_MCP_WAIT_CAP` (default 25 s) so it can't
  exceed a client's request timeout. On success the conch is free for you — call
  `converse()` next. On timeout you're deregistered. **Remote-agent posture:**
  because `wait` is capped at 25 s, a remote agent that expects to queue for
  longer than that should use `queue` + `heartbeat` instead of `wait` — `wait`
  is the low-latency path for a short queue, `queue`+`heartbeat` is the one
  that survives an arbitrarily long wait.
- `conch(action="heartbeat", session_id=…)` — refresh your remote-liveness TTL
  while idle (keeps your place). Send roughly every ~30 s while queued, and
  check the response's `granted` field every time — that heartbeat is how a
  `queue`d waiter (no poll loop of its own) discovers its grant.
- `conch(action="leave", session_id=…)` — give up your place.
- `conch(action="give", target=…)` / `bump` / `release` — the same operator
  overrides as the CLI. `give`'s summon path (see "Removed: callback mode"
  below) additionally reports whether its nudge was delivered.

A remote agent has no host PID, so its liveness is the `expires` heartbeat TTL
(`VOICEMODE_CONCH_REMOTE_TTL`, default 90 s) the tool stamps on every
`wait`/`queue`/`heartbeat` call; a waiter past its TTL is auto-pruned so a
dead remote agent never wedges the queue. **`session_id` is required** for the
register/heartbeat/leave actions — it is the remote agent's stable queue and
grant key (there is no `CLAUDE_CODE_SESSION_ID` env over HTTP). Remote *push*
notify-on-give lands with VM-970; until then the grant is discovered on the
agent's next `status`/`heartbeat`/`queue` call (the pull-only path).

The `conch` tool is **not** in the default tool set (which loads only `converse`
and `service` to keep token usage low). Enable it on a server that should expose
queue management to remote agents via `VOICEMODE_TOOLS_ENABLED` (whitelist) or
`VOICEMODE_TOOLS_DISABLED` (blacklist) — e.g.
`VOICEMODE_TOOLS_ENABLED=converse,service,conch`.

#### Removed: callback mode (VM-2078)

`converse(conch_mode="callback")` and `VOICEMODE_CONCH_MODE` are **gone** —
along with `conch(action="callback")`, renamed to `action="queue"` (same
behaviour, an honest name; see above). The old `converse()` tool description
promised a callback-mode caller "returns immediately with your position and
delivers your turn when granted" — **it never delivered the turn.** The
message was discarded at registration, and the "delivery" was a best-effort
tmux pane nudge whose return value no caller checked; for a remote grantee
(no host PID) it delivered nothing at all, ever. Silently unclaimed grants
were also exempted from `CONCH_GRANT_TTL`'s self-heal on the theory that an
out-of-band claim is normal to sit unclaimed — the combination let a single
lost nudge wedge the entire queue indefinitely, with no error anywhere.

**If you used callback mode to avoid holding a turn open**, background a
`wait`-mode `converse()` call instead: you keep the message (nothing is
discarded), the wait is genuinely TTL-covered by the self-heal above, and you
still get the floor back without blocking your own turn.

**If you used `conch(action="callback")` to hold a remote place in line**,
call `conch(action="queue", session_id=…)` — identical register-and-poll
behaviour, just honestly named; see "Remote agents: the MCP `conch` tool"
above for the full remote-agent posture (`queue`+`heartbeat` vs. the
25 s-capped `wait`).

**The one thing that survives:** `voicemode conch give <session>` /
`conch(action="give", target=…)` can still *summon* a running non-waiter that
never queued. That summon nudge is now **operator-path only** (no mode gate —
it fires because an operator asked), and its delivery is **checked and
reported**, never best-effort-and-swallowed: a confirmed-delivered nudge
grants the floor with a bounded claim window; a nudge that fails, or a target
with no local PID to nudge at all, **withholds the grant entirely** and tells
the operator plainly to relay the message themselves. Every grant this
mechanism issues is therefore still covered by a finite TTL — there is no
longer any grant exempt from the self-heal.

**Project design rule going forward:** a grant's claim-window TTL is keyed on
the **observable claim mechanism** — is a live holder still blocking the
claim; does the grantee have a local poll loop (short window) or only a
nudge/remote round trip (longer, heartbeat-scaled window) — **never on a
declared mode.** Callback mode's exemption was the last place a *declared*
category, rather than what the system could actually observe, decided how
long a grant could sit unclaimed; that is why closing it required removing
the mode entirely rather than special-casing it further.

### LiveKit Configuration

```bash
# Server settings
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_PORT=7880

# Room settings
VOICEMODE_LIVEKIT_ROOM_PREFIX=voicemode
VOICEMODE_LIVEKIT_AUTO_CREATE=true
```

### HTTP Server Configuration

When running VoiceMode as a remote HTTP service:

```bash
# Server settings
VOICEMODE_SERVE_HOST=127.0.0.1      # Bind address (0.0.0.0 for all interfaces)
VOICEMODE_SERVE_PORT=8765           # Port number
VOICEMODE_SERVE_TRANSPORT=streamable-http  # Transport: streamable-http or sse

# Security: Network access control
VOICEMODE_SERVE_ALLOW_LOCAL=true    # Allow localhost connections
VOICEMODE_SERVE_ALLOW_ANTHROPIC=false  # Allow Anthropic IP ranges
VOICEMODE_SERVE_ALLOW_TAILSCALE=false  # Allow Tailscale IP ranges
VOICEMODE_SERVE_ALLOWED_IPS=        # Custom CIDR ranges (comma-separated)

# Security: Authentication
VOICEMODE_SERVE_SECRET=             # File path containing shared secret
VOICEMODE_SERVE_TOKEN=              # Bearer token for authentication

# Logging
VOICEMODE_SERVE_LOG_LEVEL=info      # Log level: debug, info, warning, error
```

**Quick Start:**
```bash
# Start VoiceMode HTTP server
voicemode service start voicemode

# Enable auto-start at boot/login
voicemode service enable voicemode

# Check status
voicemode service status voicemode
```

### Local Service Paths

```bash
# Kokoro TTS
VOICEMODE_KOKORO_PORT=8880
VOICEMODE_KOKORO_MODELS_DIR=~/Models/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro

# Service directories
VOICEMODE_DATA_DIR=~/.voicemode
VOICEMODE_LOG_DIR=~/.voicemode/logs
VOICEMODE_CACHE_DIR=~/.voicemode/cache
```

### Debugging and Logging

```bash
# Debug mode (verbose logging, saves all files)
VOICEMODE_DEBUG=true

# Logging levels
VOICEMODE_LOG_LEVEL=info           # debug, info, warning, error
VOICEMODE_SAVE_ALL=false           # Save all audio files
VOICEMODE_SAVE_RECORDINGS=false    # Save input recordings
VOICEMODE_SAVE_TTS=false           # Save TTS output

# Event logging
VOICEMODE_EVENT_LOG=false          # Log all events
VOICEMODE_CONVERSATION_LOG=false   # Log conversations
```

### Development Settings

```bash
# Skip TTS for faster development
VOICEMODE_SKIP_TTS=false

# Disable specific features
VOICEMODE_DISABLE_SILENCE_DETECTION=false
VOICEMODE_DISABLE_VAD=false
```

## Voice Preferences System

VoiceMode supports project-specific voice preferences. Create a `.voicemode.env` file in your project root:

```bash
# Project-specific voices for a game
export VOICEMODE_VOICES="onyx,fable"
export VOICEMODE_TTS_SPEED=0.9
```

This allows different projects to have different voice settings without changing global configuration.

## Service Auto-Discovery

VoiceMode automatically discovers running local services:

1. **Whisper STT**: Checks `http://127.0.0.1:2022/v1`
2. **Kokoro TTS**: Checks `http://127.0.0.1:8880/v1`
3. **LiveKit**: Checks `ws://127.0.0.1:7880`

No configuration needed when services run on default ports!

## Configuration Philosophy

VoiceMode balances MCP compliance with user convenience:

- **Host configuration is authoritative** - Environment variables always win
- **Reasonable defaults** - Works without any configuration
- **Progressive disclosure** - Simple configs for basic use, advanced options available
- **File-based convenience** - Edit familiar config files instead of multiple host configs

## Common Configurations

### Privacy-Focused Local Setup
```bash
# No cloud services, everything local
export VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8880/v1
export VOICEMODE_STT_BASE_URLS=http://127.0.0.1:2022/v1
export VOICEMODE_VOICES=af_sky
```

### High-Quality Cloud Setup
```bash
# Best quality with OpenAI
export OPENAI_API_KEY=sk-...
export VOICEMODE_TTS_MODEL=tts-1-hd
export VOICEMODE_VOICES=nova,alloy
```

## Troubleshooting Configuration

### Check Active Configuration
```bash
# List all configuration keys
voicemode config list

# Get specific settings
voicemode config get VOICEMODE_TTS_VOICE
voicemode config get OPENAI_API_KEY
```

### Configuration Not Working?

1. **Check precedence**: Environment variables override files
2. **Verify syntax**: Use `export VAR=value` format in files
3. **Check permissions**: Ensure config files are readable
4. **Test services**: Verify local services are running
5. **Enable debug**: Set `VOICEMODE_DEBUG=true` for details

### Reset Configuration
```bash
# Backup and recreate default config
mv ~/.voicemode/voicemode.env ~/.voicemode/voicemode.env.backup
# Edit the configuration file to reset
voicemode config edit
```

## Claude Code Permissions

When using VoiceMode with Claude Code, you can configure automatic tool approval to skip permission prompts.

### Quick Setup

Add to `.claude/settings.local.json` in your project:

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse"
    ]
  }
}
```

To also allow service management (start/stop/status):

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
```

### Settings File Locations

| File | Scope | Git |
|------|-------|-----|
| `~/.claude/settings.json` | All projects | N/A |
| `.claude/settings.json` | Project (shared) | Commit |
| `.claude/settings.local.json` | Project (personal) | Ignore |

### Allowing All VoiceMode Tools

To allow all tools from the VoiceMode server:

```json
{
  "permissions": {
    "allow": ["mcp__voicemode"]
  }
}
```

> **Note**: Wildcards like `mcp__voicemode__*` are not supported. Use `mcp__voicemode` without a tool suffix.

### Useful Commands

- `/permissions` - View and manage tool permission rules

See the [Claude Code Settings documentation](https://code.claude.com/docs/en/settings) for more details.

## Security Considerations

### General Security

- **Never commit API keys** to version control
- **Use environment variables** for sensitive data in production
- **Restrict file permissions**: `chmod 600 ~/.voicemode/voicemode.env`
- **Rotate keys regularly** if exposed
- **Use local services** for sensitive audio data

### HTTP Server Security

When running VoiceMode as an HTTP service for remote access, follow these best practices:

#### 1. Bind to Localhost by Default

The safest configuration binds only to localhost:

```bash
VOICEMODE_SERVE_HOST=127.0.0.1
```

This prevents network access entirely. Use a secure tunnel (Tailscale, Cloudflare Tunnel) for remote access.

#### 2. Use Network Access Controls

When exposing to a network, restrict access:

```bash
# Allow only Tailscale connections (100.64.0.0/10)
VOICEMODE_SERVE_ALLOW_TAILSCALE=true
VOICEMODE_SERVE_HOST=0.0.0.0

# Or allow specific IP ranges
VOICEMODE_SERVE_ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
```

#### 3. Enable Authentication for Remote Access

Use bearer token authentication when exposing beyond localhost:

```bash
# Generate a secure token
openssl rand -hex 32 > ~/.voicemode/serve.token

# Configure VoiceMode to use it
VOICEMODE_SERVE_TOKEN=$(cat ~/.voicemode/serve.token)
```

Clients must include `Authorization: Bearer <token>` in requests.

#### 4. Use Secure Tunnels for Internet Access

For internet access, use a secure tunnel instead of direct exposure:

- **Tailscale**: Zero-config VPN for secure remote access
- **Cloudflare Tunnel**: Secure tunnel without opening ports
- **ngrok**: Quick tunnels for testing (not recommended for production)

#### 5. Monitor Service Logs

Regularly check logs for unauthorized access attempts:

```bash
# View service logs
voicemode service logs voicemode -n 100

# On macOS, also check:
log show --predicate 'process == "voicemode"' --last 1h
```

#### Security Mode Summary

| Access Level | Host | Security |
|--------------|------|----------|
| Localhost only | `127.0.0.1` | No auth needed |
| Local network | `0.0.0.0` + ALLOWED_IPS | Token recommended |
| Tailscale | `0.0.0.0` + ALLOW_TAILSCALE | Token recommended |
| Internet | Use secure tunnel | Token required |
