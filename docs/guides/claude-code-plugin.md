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

In **remote mode** (`VOICEMODE_MCP_URL` set) the same tools are exposed under
the `voicemode-remote` namespace — `mcp__voicemode-remote__converse` /
`mcp__voicemode-remote__service`. See [Transport Modes](#transport-modes-local-stdio-vs-remote-http).

### Converse Tool Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `message` | (required) | Text for Claude to speak |
| `wait_for_response` | true | Listen for user response after speaking |
| `listen_duration_max` | 120 | Maximum recording time (seconds) |
| `voice` | auto | TTS voice name |
| `vad_aggressiveness` | 3 | Voice detection strictness (0-3) |

## Transport Modes: Local stdio vs Remote HTTP

The plugin ships a single checked-in `.mcp.json` that supports **two
transports**, selected by one environment variable, `VOICEMODE_MCP_URL`:

| Mode | `VOICEMODE_MCP_URL` | What runs | Tool namespace |
|------|---------------------|-----------|----------------|
| **Local (default)** | unset | bundled `voicemode` stdio server (`uv run voicemode`) | `mcp__voicemode__*` |
| **Remote** | set to a serve URL | `voicemode-remote` connects to a streamable-HTTP `voicemode serve` | `mcp__voicemode-remote__*` |

When `VOICEMODE_MCP_URL` is **unset**, behaviour is exactly as before — the
local stdio server runs and there is no remote connection. The remote entry
adds nothing to the default experience.

### Remote Mode (Plugin-Only Install)

Remote mode lets you install **only the plugin** on a machine (laptop, VM,
container) and point its MCP at a full `voicemode` running somewhere with a
microphone and speakers (the "audio host"). No local `voicemode` install, no
`uv tool install voice-mode`, no Whisper/Kokoro on the plugin machine.

1. Install the plugin (skills, commands, hooks, and the dormant remote MCP
   entry):

   ```bash
   claude plugin marketplace add https://github.com/mbailey/claude-plugins
   claude plugin install voicemode@mbailey
   ```

2. Point it at a streamable-HTTP `voicemode serve` (remote **or** a serve on
   this same machine). Add to `~/.voicemode/voicemode.env` or export it:

   ```bash
   export VOICEMODE_MCP_URL=https://audio-host.example/mcp/<secret>
   ```

   The endpoint is the full URL including the `/mcp` path (and
   `/mcp/<secret>` if the serve has `VOICEMODE_SERVE_SECRET` set). See the
   [Serve Configuration guide](serve-configuration.md) for standing up the
   audio host.

3. (Recommended for remote-only) Stop the unused local stdio server by
   disabling the bundled `voicemode` in Claude Code settings:

   ```json
   { "disabledMcpjsonServers": ["voicemode"] }
   ```

4. Use voice as normal. In remote mode the tools are
   `mcp__voicemode-remote__converse` / `mcp__voicemode-remote__service`
   (the namespace differs from local mode — see below).

### What to disable per mode

| Mode | `VOICEMODE_MCP_URL` | Working server | Disable for a clean `claude mcp list` |
|------|---------------------|----------------|----------------------------------------|
| Local (default) | unset | `voicemode` (stdio) | `disabledMcpjsonServers: ["voicemode-remote"]` — optional, cosmetic |
| Remote-only | set | `voicemode-remote` (http) | `disabledMcpjsonServers: ["voicemode"]` — recommended (stops the unused local stdio) |
| Both (advanced) | set | both | nothing |

> **Note on the default install:** with `VOICEMODE_MCP_URL` unset, the
> `voicemode-remote` entry shows as a *failed* server in `claude mcp list`
> (Claude Code does not skip an http entry with an unset URL variable — it
> reports a connection failure). This is **cosmetic only** and never affects
> the working local `voicemode` stdio server. Stdio-only users who want a
> clean list can suppress it with
> `disabledMcpjsonServers: ["voicemode-remote"]`.

### Authentication

Remote mode reuses the existing `voicemode serve` auth surface — no new
serve-side config:

- **Secret in path (zero extra config):** put the secret in the URL —
  `VOICEMODE_MCP_URL=https://host/mcp/<secret>` — matched by
  `VOICEMODE_SERVE_SECRET` on the serve side.
- **Bearer token (optional):** set `VOICEMODE_MCP_TOKEN` and add a `headers`
  block to the plugin `.mcp.json` so the remote entry sends
  `Authorization: Bearer ${VOICEMODE_MCP_TOKEN}` (matched by
  `VOICEMODE_SERVE_TOKEN`). Secret-in-path is the recommended default.
- **IP allowlist:** enforced at the serve side
  (`--allow-tailscale` / `--allow-ip`); nothing on the plugin side.

If the endpoint is unreachable or unauthorized, Claude Code reports the
remote `voicemode-remote` server as failed (with its config-issue hint and
the HTTP status / URL via `/mcp`). Re-check `VOICEMODE_MCP_URL`, the secret,
and that `voicemode serve` is running and allows your IP. See the
[Serve Configuration troubleshooting](serve-configuration.md#troubleshooting).

### Duplicate-MCP precedence (the footgun)

MCP servers are keyed by name and resolved by scope precedence. If you
configure a `voicemode` server yourself (user/project `.mcp.json` or
`claude mcp add … voicemode …`), **your configuration wins** over the
plugin-bundled `voicemode` (same name ⇒ explicit user config takes
precedence; the bundled server is the fallback). There is never a silent
"two voicemode servers" — the same name collapses to yours.

- A user who already ran
  `claude mcp add --transport http voicemode <url>` overrides the bundled
  stdio server with no extra steps.
- To run *only* a separately-configured voicemode, disable the bundled one:
  `disabledMcpjsonServers: ["voicemode"]`.
- The plugin's remote entry uses a **distinct** name (`voicemode-remote`),
  so you can intentionally run bundled-local + plugin-remote side by side
  (advanced).

## Hooks and Soundfonts

The plugin includes a hook receiver that plays sounds during tool execution:

- Sounds play when tools start and complete
- Provides audio feedback during long operations
- Uses configurable soundfonts
- Toggle with `voicemode soundfonts on/off`

Hooks are automatically configured when the plugin is installed.

See the [Soundfonts Guide](soundfonts.md) for customization, sound lookup order, and troubleshooting.

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
