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

The namespace is **the same in remote mode** (`VOICEMODE_MCP_URL` set) —
still `mcp__voicemode__*`. There is one server either way. See
[Transport Modes](#transport-modes-local-stdio-vs-remote-http).

### Converse Tool Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `message` | (required) | Text for Claude to speak |
| `wait_for_response` | true | Listen for user response after speaking |
| `listen_duration_max` | 120 | Maximum recording time (seconds) |
| `voice` | auto | TTS voice name |
| `vad_aggressiveness` | 3 | Voice detection strictness (0-3) |

## Transport Modes: Local stdio vs Remote HTTP

The plugin ships **one** checked-in `.mcp.json` entry — a single `type: stdio`
server, `voicemode`, whose command is a first-party smart launcher
(`voicemode-mcp-launcher`, shipped in the package). The *launcher* selects the
transport from one environment variable, `VOICEMODE_MCP_URL`:

| Mode | `VOICEMODE_MCP_URL` | What runs | Tool namespace |
|------|---------------------|-----------|----------------|
| **Local (default)** | unset | launcher runs the bundled `voicemode` stdio server in-process | `mcp__voicemode__*` |
| **Remote** | set to a serve URL | launcher acts as a native stdio↔Streamable-HTTP bridge to `voicemode serve` | `mcp__voicemode__*` |

There is always exactly **one** `voicemode` server and **one**
`mcp__voicemode__*` namespace. No second `voicemode-remote` entry, and **no
`disabledMcpjsonServers` step is ever required** — remote mode means *only*
remote because the launcher itself does not start the local server.

When `VOICEMODE_MCP_URL` is **unset**, behaviour is byte-for-byte the pre-VM-1314
local stdio default — the launcher is a thin in-process `exec` of the same
server, no proxy hop and no added failure surface.

> **Why a launcher?** Claude Code's `.mcp.json` cannot switch transport from an
> env var (the `type` field is not env-expandable; the `${VAR:-default}` form
> only works for value fields like `url`). VM-1292 worked around this with two
> entries, which left the local stdio server always spawning. VM-1314 moves the
> switch into our own process, where it is trivial — one entry, fully
> env-configurable, no manual settings edit.

### Remote Mode (Plugin-Only Install)

Remote mode lets you install **only the plugin** on a machine (laptop, VM,
container) and point its MCP at a full `voicemode` running somewhere with a
microphone and speakers (the "audio host"). No local `voicemode` install, no
`uv tool install voice-mode`, no Whisper/Kokoro on the plugin machine.

1. Install the plugin (skills, commands, hooks, and the single `voicemode`
   MCP entry):

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
   `/mcp/<secret>` if the serve has `VOICEMODE_SERVE_SECRET` set). Either
   location works — the launcher reads its own process env and also loads
   `~/.voicemode/voicemode.env` (a real exported env var wins over the file).
   See the [Serve Configuration guide](serve-configuration.md) for standing
   up the audio host.

3. Use voice as normal. The tools are `mcp__voicemode__converse` /
   `mcp__voicemode__service` — **the same namespace as local mode**. Nothing
   to disable: remote mode runs *only* the remote bridge, the local stdio
   server is never started.

There is no per-mode `disabledMcpjsonServers` table any more, and no
"failed server" cosmetic note: there is only ever the one `voicemode` entry,
and it connects whichever way `VOICEMODE_MCP_URL` says.

### Authentication

Remote mode reuses the existing `voicemode serve` auth surface — no new
serve-side config:

- **Secret in path (zero extra config):** put the secret in the URL —
  `VOICEMODE_MCP_URL=https://host/mcp/<secret>` — matched by
  `VOICEMODE_SERVE_SECRET` on the serve side.
- **Bearer token (optional):** set `VOICEMODE_MCP_TOKEN`. The launcher's
  native bridge sends `Authorization: Bearer <token>` automatically (matched
  by `VOICEMODE_SERVE_TOKEN`). No `.mcp.json` edit, no `headers` block — set
  it in `voicemode.env` or the environment. Secret-in-path is the
  recommended default.
- **IP allowlist:** enforced at the serve side
  (`--allow-tailscale` / `--allow-ip`); nothing on the plugin side.

If the endpoint is unreachable or unauthorized, the bridge surfaces the
connection error on stderr and the `voicemode` server shows as failed in
`claude mcp list`. Re-check `VOICEMODE_MCP_URL`, the secret, and that
`voicemode serve` is running and allows your IP. See the
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
  launcher with no extra steps.
- To run *only* a separately-configured voicemode, disable the bundled one:
  `disabledMcpjsonServers: ["voicemode"]`.
- The plugin no longer ships a second `voicemode-remote` entry; remote vs
  local is selected by `VOICEMODE_MCP_URL` on the single bundled entry.

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
