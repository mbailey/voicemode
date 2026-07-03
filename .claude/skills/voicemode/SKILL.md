---
name: voicemode
description: Voice interaction for Claude Code. Use when users mention voice mode, speak, talk, converse, voice status, or voice troubleshooting.
---

## First-Time Setup

If VoiceMode isn't working or MCP fails to connect, run:

```
/voicemode:install
```

After install, reconnect MCP: `/mcp` → select voicemode → "Reconnect" (or restart Claude Code).

If Claude Code prompts you for permission on `voicemode:converse` or `voicemode:service`, see [references/permissions.md](references/permissions.md) for the one-time allow-list setup.

---

# VoiceMode

Natural voice conversations with Claude Code using speech-to-text (STT) and text-to-speech (TTS).

**Note:** The Python package is `voice-mode` (hyphen), but the CLI command is `voicemode` (no hyphen).

## When to Use MCP vs CLI

| Task                | Use                      | Why                             |
| ------------------- | ------------------------ | ------------------------------- |
| Voice conversations | MCP `voicemode:converse` | Faster - server already running |
| Service start/stop  | MCP `voicemode:service`  | Works within Claude Code        |
| Installation        | CLI `voice-mode-install` | One-time setup                  |
| Configuration       | CLI `voicemode config`   | Edit settings directly          |
| Diagnostics         | CLI `voicemode diag`     | Administrative tasks            |

## Usage

Use the `converse` MCP tool to speak to users and hear their responses:

```python
# Speak and listen for response (most common usage)
voicemode:converse("Hello! What would you like to work on?")

# Speak without waiting (for narration while working)
voicemode:converse("Searching the codebase now...", wait_for_response=False)
```

For most conversations, just pass your message - defaults handle everything else.
Use default converse tool parameters unless there's a good reason not to. Timing parameters (`listen_duration_max`, `listen_duration_min`) use smart defaults with silence detection - don't override unless the user requests it or you see a clear need. Defaults are configurable by the user via `~/.voicemode/voicemode.env`.

| Parameter           | Default  | Description                                                          |
| ------------------- | -------- | -------------------------------------------------------------------- |
| `message`           | required | Text to speak                                                        |
| `wait_for_response` | true     | Listen after speaking                                                |
| `voice`             | auto     | TTS voice -- **must be lowercase** (e.g. `af_river`, not `AF_River`) |

**Voice name rule:** If you specify a `voice`, it MUST be lowercase with
underscores. Kokoro rejects capitalized names like `AF_River` with a 400
error. Valid examples: `af_river`, `af_sky`, `bm_daniel`, `bf_emma`.
The prefix encodes language+gender: `af_` = American female, `am_` =
American male, `bf_` = British female, `bm_` = British male.

When in doubt, omit `voice` entirely -- auto-select picks a working
default.

**Voice discovery for apps and agents:** read the `voice://voices` MCP
resource for a structured JSON list of available voices (with
`voice://voices/{provider}` for per-backend filtering). The
`voice_registry` tool returns the same data as prose for the LLM
mid-conversation. Both share the underlying enumerator so they never
drift. See [voices resource reference](../../docs/reference/voices-resource.md).

**Persona discovery:** voice IDs from `voice://voices` map to character profiles on disk at `~/.voicemode/voices/<name>/README.md` (grouped voices: `<group>/<name>/README.md`; index at `~/.voicemode/voices/PERSONAS.md`). Read that README before speaking in character — who they are, how they speak, sample lines. Not every voice has one yet; fall back to the bare voice if absent.

For all parameters, see [Converse Parameters](../../docs/reference/converse-parameters.md).

## Best Practices

1. **Narrate without waiting** - Use `wait_for_response=False` when announcing actions
2. **One question at a time** - Don't bundle multiple questions in voice mode
3. **Check status first** - Verify services are running before starting conversations
4. **Let VoiceMode auto-select** - Don't hardcode providers unless user has preference
5. **First run is slow** - Model downloads happen on first start (2-5 min), then instant

## Voicemode echo (default ON)

Some hosts (e.g. newer Claude Code) collapse MCP tool calls — voice turns vanish from the visible transcript. **Unless requested otherwise, default to voicemode echo:** print each `voicemode:converse` exchange as Markdown blockquotes so it stays readable on screen.

```
> **ASSISTANT (voicemode):** <message arg passed to converse>
[voicemode:converse tool call]
> **USER (voicemode):** <captured user message>
```

- Speaker first in caps; `(voicemode)` is the channel tag.
- **Order matters.** Write the **ASSISTANT** blockquote *before* the `voicemode:converse` tool call, in the same response that issues it — so the user can read along while the audio plays (and recover the message if they miss part of it). Write the **USER** blockquote in your *next* response, after the tool result returns. Don't batch both echoes after the call.
- **ASSISTANT echo: always**, including `wait_for_response=false` (speak-only narration still produces visible content that would otherwise vanish).
- **USER echo: only when a user message was captured** (skip on `wait_for_response=false`, empty result, or transcription failure — there is nothing to echo).
- **Assistant echo: verbatim by default** — the exact string passed to `message`, not paraphrased or reformatted. Reasons: least-surprising for the reader + diagnostic value when comparing printed text to spoken audio.
- **User echo: verbatim and full** — exact words, no truncation; rewriting or shortening risks distorting intent.
- **Visual aids (lists, tables, code) belong AFTER the blockquote, not inside it.** The blockquote stays a clean verbatim copy of what was spoken; richer formatting can follow as separate prose.
- Don't double-echo: if a sentence already appears as visible prose in the same response, don't also blockquote it.
- **Disable on request** — canonical phrase: **"disable voicemode echo"**. Stop echoing for the rest of the session and honour the same phrase if it appears in the user's startup context (some hosts already render voice tool calls inline, where echoes would double up).

## Parallel Tool Calls (Zero Dead Air)

Eliminate dead air by sending voice and action calls in the **same response**:

```
# FAST: speak + act in parallel (all fire concurrently)
voicemode:converse("Checking that now.", wait_for_response=False)
Bash("git status")
Agent(prompt="Research X", run_in_background=True)

# SLOW: sequential — unnecessary delay between speech and action
voicemode:converse("Checking that now.", wait_for_response=False)
# ... waits for TTS to finish ...
Bash("git status")
```

Then report results in the next response:
```
voicemode:converse("Here's what I found: ...", wait_for_response=True)
```

| Scenario                 | Approach       | Why                                                 |
| ------------------------ | -------------- | --------------------------------------------------- |
| Announce + do work       | **Parallel**   | No dependency between speech and action             |
| Announce + spawn agent   | **Parallel**   | Agent runs in background anyway                     |
| Check result then report | **Sequential** | Need result before speaking                         |
| Listen for response      | **Sequential** | `wait_for_response=True` blocks until user speaks   |

**Key insight:** Wall-clock time = longest call, not the sum. All tool types (MCP, Bash, Agent, Read) can be mixed in one response.

## Handling Pauses and Wait Requests

When the user asks you to wait or give them time:

**Short pauses (up to 60 seconds):** If the user says something ending with "wait" (e.g., "hang on", "give me a sec", "wait"), VoiceMode automatically pauses for 60 seconds then resumes listening. This is built-in.

**Longer pauses (2+ minutes):** Use `bash sleep N` where N is seconds. For example, if the user says "give me 5 minutes":

```bash
sleep 300  # Wait 5 minutes
```

Then call converse again when the wait is over:

```python
voicemode:converse("Five minutes is up. Ready when you are.")
```

**Configuration:** The short pause duration is configurable via `VOICEMODE_WAIT_DURATION` (default: 60 seconds).

## Turn Control: Handling Requests for More Time

When the user asks for more time or requests not to be cut off (e.g., "끊지 마", "생각 좀 할게", "let me think", "give me a sec"), set `silence_release_sec=60` on the next `converse` call. This allows the user to pause mid-sentence without the assistant taking the floor prematurely. The user can still end their turn explicitly with a skip-forward control (media key or Stream Deck).

## Interpreting Silence Markers: Recognizing Hesitation

A converse result may contain inline silence markers (e.g. `⟨pause 5.1s⟩` or `⟨pre-speech 3.2s⟩`) within the transcript and a `| Silence:` field in the summary. These markers indicate hesitation or significant thinking time. When you observe them, acknowledge the user's hesitation empathetically and offer to help—for example: "I noticed you paused there—what's on your mind?" or "Take your time, I'm here to help you think through this."

## Transport controls (media keys & Stream Deck)

While a converse is live, VoiceMode exposes a **control channel** — drive it with
`voicemode control pause | resume | stop | skip-forward | skip-back`. You can wire
these to physical buttons so the human can pause/barge/replay without typing:

- **Stream Deck** (or any tool that runs a shell command): bind a button straight
  to `voicemode control skip-forward` etc. No extra dependency — it shells out to
  the CLI directly.
- **macOS media keys** (▶❙❙ / ⏭ / ⏮): routed through a **Hammerspoon** eventtap
  (`scripts/hammerspoon/voicemode-media-keys.lua`) that only grabs the keys while
  a converse is live, so music is untouched otherwise.

**Enabling:**

1. Set `VOICEMODE_CONTROL_CHANNEL_ENABLED=true` in `~/.voicemode/voicemode.env`
   (server binds `~/.voicemode/control.sock` for the converse turn).
2. For media keys: install Hammerspoon, load the config from `~/.hammerspoon/init.lua`,
   grant **Accessibility**, and **keep Hammerspoon running — make it a login item.**
   The eventtap only exists while Hammerspoon is running; if it's not, the keys
   silently pass through to Music/Spotify and VoiceMode never sees them (no error —
   they just do nothing). A working Stream Deck with dead media keys = Hammerspoon
   isn't running. Quick check: `pgrep -x Hammerspoon`.

Full reference (ownership model, skip-back history buffer, raw-socket protocol):
[docs/reference/control-channel.md](../../docs/reference/control-channel.md).

## STT Recovery - Manual Transcription

If Whisper STT fails but the audio was recorded successfully, you can manually transcribe the saved audio file:

```bash
# Transcribe the most recent recording
whisper-cli ~/.voicemode/audio/latest-STT.wav

# Or check if file exists first (safe for inclusion in automation)
if [ -f ~/.voicemode/audio/latest-STT.wav ]; then
  whisper-cli ~/.voicemode/audio/latest-STT.wav
fi
```

**Requirements:**

- Audio saving must be enabled via one of:
  - `VOICEMODE_SAVE_AUDIO=true` in `~/.voicemode/voicemode.env`
  - `VOICEMODE_SAVE_ALL=true` (saves all audio and transcriptions)
  - `VOICEMODE_DEBUG=true` (enables debug mode with audio saving)

**How it works:**

- VoiceMode saves all STT recordings to `~/.voicemode/audio/` with timestamps
- The `latest-STT.wav` symlink always points to the most recent recording
- If the STT API fails, the recording is still saved for manual recovery
- This lets you recover the user's speech without asking them to repeat

**When to use:**

- STT service timeout or connection failure
- Transcription returned empty but user definitely spoke
- Need to verify what was actually said vs. what was transcribed

See also: [Troubleshooting - No Speech Detected](../../docs/troubleshooting/index.md#1-no-speech-detected)

## Check Status

```bash
voicemode service status          # All services
voicemode service status whisper  # Specific service
```

Shows service status including running state, ports, and health.

## Reconnecting after a mid-session drop

If voice drops mid-session (`-32000 Connection closed`) — or the server failed to
register its tools at launch — the voicemode MCP *tools* vanish, so recovery
can't be an MCP tool. Bash and tmux survive, so heal it in **one Bash call**:

```bash
voicemode reconnect
```

This runs the whole `/mcp` reconnect dance on your own pane (`$TMUX_PANE`): opens
the menu, finds the voicemode server *by name* (not a fragile Down-count),
navigates to it by reading the cursor, hits **Reconnect** only if it's failed,
polls until it's connected, then prints the exact `ToolSearch` line to reload the
converse schema. It fails loud rather than sending blind keystrokes if the screen
isn't what it expects. **Must run inside tmux** (it drives the pane via tmux).

After it prints `RESULT: reconnected`, run the `ToolSearch select:…` line it
echoes to reload the tool schema, then resume conversing.

```
RESULT: reconnected            # exit 0  — was failed, now reconnected
RESULT: already-connected      # exit 10 — nothing to do (benign no-op)
                               # 11 not-found · 12 timeout · 13 not-in-tmux · 1 error
```

Useful flags: `--pane <id>` (drive another pane), `--server <substr>` (default
`voicemode`), `--timeout <s>` (default 75), `--dry-run` (report, send no keys).

**Fallback — drive `/mcp` by hand** (older Claude Code, or if `voicemode
reconnect` ever fails loud on an unfamiliar menu): the step-by-step manual walk
lives in `~/.slipbox/voice-self-reconnect.md` — open `/mcp`, read the list with
`capture-pane`, navigate to voicemode, hit Reconnect, wait ~1 min, reload the
schema.

## Installation

```bash
# Install VoiceMode CLI and configure services
uvx voice-mode-install --yes

# Install local services (Apple Silicon recommended)
voicemode service install whisper
voicemode service install kokoro
```

See [Getting Started](../../docs/tutorials/getting-started.md) for detailed steps.

## Service Management

```python
# Start/stop services
voicemode:service("whisper", "start")
voicemode:service("kokoro", "start")

# View logs for troubleshooting
voicemode:service("whisper", "logs", lines=50)
```

| Service   | Port | Purpose         |
| --------- | ---- | --------------- |
| whisper   | 2022 | Speech-to-text  |
| kokoro    | 8880 | Text-to-speech  |
| voicemode | 8765 | HTTP/SSE server |

**Actions:** status, start, stop, restart, logs, enable, disable

## Configuration

```bash
voicemode config list                           # Show all settings
voicemode config set VOICEMODE_TTS_VOICE nova   # Set default voice
voicemode config edit                           # Edit config file
```

Config file: `~/.voicemode/voicemode.env`

See [Configuration Guide](../../docs/guides/configuration.md) for all options.

## DJ Mode

Background music during VoiceMode sessions with track-level control.

```bash
# Core playback
voicemode dj play /path/to/music.mp3  # Play a file or URL
voicemode dj status                    # What's playing
voicemode dj pause                     # Pause playback
voicemode dj resume                    # Resume playback
voicemode dj stop                      # Stop playback

# Navigation and volume
voicemode dj next                      # Skip to next chapter
voicemode dj prev                      # Go to previous chapter
voicemode dj volume 30                 # Set volume to 30%

# Music For Programming
voicemode dj mfp list                  # List available episodes
voicemode dj mfp play 49               # Play episode 49
voicemode dj mfp sync                  # Convert CUE files to chapters

# Music library
voicemode dj find "daft punk"          # Search library
voicemode dj library scan              # Index ~/Audio/music
voicemode dj library stats             # Show library info

# Play history and favorites
voicemode dj history                   # Show recent plays
voicemode dj favorite                  # Toggle favorite on current track
```

**Configuration:** Set `VOICEMODE_DJ_VOLUME` in `~/.voicemode/voicemode.env` to customize startup volume (default: 50%).

## CLI Cheat Sheet

```bash
# Service management
voicemode service status            # All services
voicemode service start whisper     # Start a service
voicemode service logs kokoro       # View logs

# Diagnostics
voicemode deps                      # Check dependencies
voicemode diag info                 # System info
voicemode diag devices              # Audio devices

# DJ Mode
voicemode dj play <file|url>        # Start playback
voicemode dj status                 # What's playing
voicemode dj next/prev              # Navigate chapters
voicemode dj stop                   # Stop playback
voicemode dj mfp play 49            # Music For Programming
```

## Voice Handoff Between Agents

Transfer voice conversations between Claude Code agents for multi-agent workflows.

**Use cases:**

- Personal assistant routing to project-specific foremen
- Foremen delegating to workers for focused tasks
- Returning control when work is complete

### Quick Reference

```python
# 1. Announce the transfer
voicemode:converse("Transferring you to a project agent.", wait_for_response=False)

# 2. Spawn with voice instructions (mechanism depends on your setup)
spawn_agent(path="/path", prompt="Load voicemode skill, use converse to greet user")

# 3. Go quiet - let new agent take over
```

**Hand-back:**

```python
voicemode:converse("Transferring you back to the assistant.", wait_for_response=False)
# Stop conversing, exit or go idle
```

### Key Principles

1. **Announce transfers**: Always tell the user before transferring
2. **One speaker**: Only one agent should use converse at a time
3. **Distinct voices**: Different voices make handoffs audible
4. **Provide context**: Tell receiving agent why user is being transferred

### Auto-focus tmux pane on speak (opt-in)

When you run multiple voice agents in separate tmux panes, set
`VOICEMODE_AUTO_FOCUS_PANE=true` to make tmux follow the speaker. Focus
switches **after conch acquisition**, so agents waiting on the conch never
steal focus -- only the agent about to speak does. It also respects the
`~/.voicemode/focus-hold` sentinel written by the show-me plugin, so a
file you just opened stays on screen for its hold window.

```bash
# ~/.voicemode/voicemode.env
VOICEMODE_AUTO_FOCUS_PANE=true
```

Off by default. Silent no-op outside tmux.

### Detailed Documentation

See [Call Routing](../../../docs/guides/agents/call-routing/) for comprehensive guides:

- [Handoff Pattern](../../../docs/guides/agents/call-routing/handoff.md) - Complete hand-off and hand-back process
- [Voice Proxy](../../../docs/guides/agents/call-routing/proxy.md) - Relay pattern for agents without voice
- [Call Routing Overview](../../../docs/guides/agents/call-routing/README.md) - All routing patterns

## Sharing Voice Services Over Tailscale

Expose local Whisper (STT) and Kokoro (TTS) to other devices on your Tailnet via HTTPS.

### Why

- Browsers require HTTPS for microphone access (e.g., VoiceMode Connect web app)
- Tailscale serve provides automatic HTTPS with valid Let's Encrypt certificates for `*.ts.net` domains
- Enables using your powerful local machine's GPU from any device on your Tailnet

### Setup

```bash
# Expose TTS (Kokoro on port 8880)
tailscale serve --bg --set-path /v1/audio/speech http://localhost:8880/v1/audio/speech

# Expose STT (Whisper on port 2022)
tailscale serve --bg --set-path /v1/audio/transcriptions http://localhost:2022/v1/audio/transcriptions

# Verify configuration
tailscale serve status

# Reset all serve config
tailscale serve reset
```

### Endpoints

After setup, endpoints are available at:

- **TTS:** `https://<hostname>.<tailnet>.ts.net/v1/audio/speech`
- **STT:** `https://<hostname>.<tailnet>.ts.net/v1/audio/transcriptions`

### Important Notes

- **Path mapping**: Tailscale strips the incoming path before forwarding, so you MUST include the full path in the target URL
- **Same-machine testing**: Traffic doesn't route through Tailscale locally — test from another Tailnet device
- **Multiple paths**: You can configure different paths to different backends on the same or different machines
- **CORS**: Kokoro has CORS configured to allow `https://app.voicemode.dev` origins

### Use with VoiceMode Connect

In the VoiceMode Connect web app settings (app.voicemode.dev/settings), set:

- **TTS Endpoint**: `https://<hostname>.<tailnet>.ts.net`
- **STT Endpoint**: `https://<hostname>.<tailnet>.ts.net`

## Soundfonts

Audio feedback tones that play during Claude Code tool use. Toggle with `voicemode soundfonts on/off`. See [Soundfonts Guide](../../docs/guides/soundfonts.md).

## Remote Voice with VoiceMode Connect

When local voice isn't an option -- no mic/speaker on the machine, can't install local services, or want to use a phone -- **VoiceMode Connect** provides remote voice through a web app or mobile device.

**When to suggest Connect:**
- User can't install Whisper/Kokoro locally (unsupported platform, permissions, corporate machine)
- User wants to talk to their agent from a phone or tablet
- User is on a remote/headless machine without audio hardware
- Local voice services are failing and quick troubleshooting hasn't helped

**How it works:** Add the VoiceMode MCP server to any Claude product, open app.voicemode.dev on a phone or browser, and talk. No local TTS/STT installation needed -- the client device handles audio.

**Setup:** See the [VoiceMode Connect skill](../voicemode-connect/SKILL.md) for MCP configuration and getting started.

## Documentation Index

| Topic               | Link                                                          |
| ------------------- | ------------------------------------------------------------- |
| Converse Parameters | [All Parameters](../../docs/reference/converse-parameters.md) |
| Installation        | [Getting Started](../../docs/tutorials/getting-started.md)    |
| Configuration       | [Configuration Guide](../../docs/guides/configuration.md)     |
| Claude Code Plugin  | [Plugin Guide](../../docs/guides/claude-code-plugin.md)       |
| Whisper STT         | [Whisper Setup](../../docs/guides/whisper-setup.md)           |
| Kokoro TTS          | [Kokoro Setup](../../docs/guides/kokoro-setup.md)             |
| Pronunciation       | [Pronunciation Guide](../../docs/guides/pronunciation.md)     |
| Troubleshooting     | [Troubleshooting](../../docs/troubleshooting/index.md)        |
| Soundfonts          | [Soundfonts Guide](../../docs/guides/soundfonts.md)           |
| CLI Reference       | [CLI Docs](../../docs/reference/cli.md)                       |
| DJ Mode             | [Background Music](docs/dj-mode/README.md)                    |

## Related Skills

- **[VoiceMode Connect](../voicemode-connect/SKILL.md)** - Remote voice via mobile/web clients (no local STT/TTS needed)
- **[Impressions](../impressions/SKILL.md)** - Add custom voices via local mlx-audio (Apple Silicon only, preview). Use when the user wants `voice="<name>"` with a clip-based custom voice rather than a Kokoro voice.
