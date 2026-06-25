# Control Channel Reference

The **control channel** is a side channel into the *running* VoiceMode server. It
lets an external trigger — a Stream Deck button, a media key, a spoken keyword,
or any local process — **pause, resume, or stop** an in-flight TTS utterance
*without* going through the agent and *without* pressing ESC.

The headline idea is **"barge-in with a key"**: the value of cutting the
assistant off when it's talking too long or off-topic, but **deterministically**
(an explicit button or keyword) rather than via voice-activity guessing. Stopping
through this channel makes the `converse` tool return **normally** with a control
marker, so the agent reads a clean tool result and continues in text — no MCP
teardown, no `/mcp` reconnect.

> The channel is **off by default** and **local-only**. You opt in per server
> with `VOICEMODE_CONTROL_CHANNEL_ENABLED=true` (see [Enabling](#enabling)).

## Quick start

```bash
# 1. Enable the channel on the server (e.g. in ~/.voicemode/voicemode.env)
export VOICEMODE_CONTROL_CHANNEL_ENABLED=true

# 2. While VoiceMode is speaking, from any local shell:
voicemode control stop                                  # cut the current utterance
voicemode control stop --hint switch-to-text -m "can't talk right now"
voicemode control pause                                 # hold playback
voicemode control resume                                # resume after a pause
```

## How it works

```
trigger (Stream Deck / media key / keyword / any process)
      │  writes one JSON line
      ▼
  control.sock  ──►  listener thread  ──►  control state  ──►  TTS playback loop
 (Unix socket)       (in the server)       (pause/stop)        (cuts within ~one chunk)
```

- The running server binds a **Unix domain socket** while it is speaking and
  listens for newline-delimited JSON commands.
- Each command flips a thread-safe in-process control state.
- The TTS playback loop polls that state every audio chunk (~85 ms), so a `stop`
  lands well under ~200 ms. Both Kokoro and mlx-audio go through the same
  streaming path, so one mechanism covers both backends.
- On `stop`, `converse` ends recording/playback cleanly and returns a normal
  result string with a control marker (see [Stop behaviour](#stop-behaviour)).

The socket is only bound **while an audio operation is active**, so only the
currently-speaking server owns the single well-known socket. The
[conch](../concepts/architecture.md) already serializes who-is-speaking across
multiple agent instances.

## Enabling

| Variable | Description | Default |
|----------|-------------|---------|
| `VOICEMODE_CONTROL_CHANNEL_ENABLED` | Bind the control socket while speaking | `false` |
| `VOICEMODE_CONTROL_SOCKET` | Path to the control Unix domain socket | `~/.voicemode/control.sock` |

The channel is **off by default**: enabling it binds a Unix socket that any
*local* process can drive, so it stays opt-in. When disabled, the listener is
never started and the CLI has nothing to talk to.

## Socket

- **Type:** `AF_UNIX` / `SOCK_STREAM` (no TCP port — every trigger runs on the
  same machine as the server).
- **Path:** `~/.voicemode/control.sock` by default (override with
  `VOICEMODE_CONTROL_SOCKET`), beside the conch under `~/.voicemode/`.
- **Permissions:** created `0600` (owner-only) — a local-only side channel.
- **Lifecycle:** bound only while the server is speaking; unlinked on exit. A
  stale socket left by a crashed server is cleared with unlink-then-bind.

## Command schema

Commands are **newline-delimited JSON**, one command per line. Send as many lines
as you like down a single connection.

```json
{"command": "pause"}
{"command": "resume"}
{"command": "stop"}
{"command": "stop", "message": "user can't talk right now", "hint": "switch-to-text"}
```

| Field | Type | Required | Applies to | Meaning |
|-------|------|----------|------------|---------|
| `command` | string | yes | all | One of `pause`, `resume`, `stop`. |
| `message` | string | no | `stop` | Free-text note for the agent, surfaced in the converse return. |
| `hint` | string | no | `stop` | Named hint (e.g. `switch-to-text`), surfaced in the converse return. |

`message` and `hint` are accepted on any command for forward-compatibility, but
today they only surface on `stop`. Anything malformed (bad JSON, unknown command,
non-string fields) is logged and ignored — a bad line never crashes the server.

> **`volume` is a documented stretch goal**, not implemented in v1. The schema
> reserves `{"command": "volume", "level": 0..100}`; sending it today is rejected
> as an unknown command.

### Commands

- **`pause`** — hold playback. Audio stops writing and waits (no busy-spin) until
  `resume` or `stop`. No-op once stopped.
- **`resume`** — resume playback after a `pause`. No-op once stopped.
- **`stop`** — cut the in-flight utterance cleanly. Sticky and terminal until the
  next utterance resets it; the first `stop`'s `message`/`hint` win. This is the
  primary, load-bearing command.

### Stop behaviour

A `stop` is **not** ESC. When it arrives, `converse` returns **normally**
(success), with a control marker prepended to the result string:

```
[control: stop] switch-to-text — user can't talk right now | Timing: ...
```

The agent reads an ordinary tool result and just continues in text. There is no
`asyncio.CancelledError`, no MCP server teardown, and no `/mcp` reconnect. A stop
that arrives while VoiceMode is *listening* (recording) returns cleanly the same
way, skipping transcription.

## The `voicemode control` CLI

The CLI is the reference client — the "second local process" that proves the
channel is reusable. It writes exactly one JSON line to the socket and exits.

```
voicemode control pause   [--message TEXT] [--hint TEXT] [--socket PATH]
voicemode control resume  [--message TEXT] [--hint TEXT] [--socket PATH]
voicemode control stop    [--message TEXT] [--hint TEXT] [--socket PATH]
```

| Option | Description |
|--------|-------------|
| `--message`, `-m` | Free-text message for the agent (surfaces on `stop`). |
| `--hint` | Named hint, e.g. `switch-to-text` (surfaces on `stop`). |
| `--socket` | Socket path override (default `$VOICEMODE_CONTROL_SOCKET` or `~/.voicemode/control.sock`). |

Exit status is `0` on a successful send. If nothing is listening — the server
isn't speaking, or the channel is disabled — the CLI exits non-zero with a clear
message rather than hanging.

## Worked examples

Any trigger that can run a shell command (or open a Unix socket) can drive the
channel. The three below cover the surfaces in Mike's brief.

### Stream Deck

Stream Deck's *System → Open* / *Multi Action* runs a command on a key press.
Point a button at the CLI:

```bash
# "Text mode" button — cut Cora off and tell the agent why
voicemode control stop --hint switch-to-text -m "user switched to text mode"
```

```bash
# "Pause" / "Resume" buttons
voicemode control pause
voicemode control resume
```

If your Stream Deck plugin needs an absolute path, find it with `which voicemode`
(or use `uvx voice-mode control stop`).

### Media keys

Map a media key (or a Bluetooth headset's play/pause) to the CLI with whatever
key-binding tool you use. For example with [`skhd`](https://github.com/koekeishiya/skhd)
on macOS:

```
# ~/.skhdrc — F8 stops, F7 pauses, F9 resumes
0x64 : voicemode control stop --hint switch-to-text
0x65 : voicemode control pause
0x67 : voicemode control resume
```

The same idea works with `xbindkeys` on Linux, Karabiner-Elements, or any tool
that can bind a key to a shell command.

### Spoken keyword

A wake-word / always-listening helper can shell out to the CLI (or open the
socket directly) when it hears a keyword:

```bash
# pseudo-handler: when the local keyword spotter fires "stop talking"
on_keyword "stop talking" -> voicemode control stop --hint switch-to-text
```

### Raw socket (no CLI)

For an integration that would rather not shell out, write one JSON line to the
socket directly. From the shell:

```bash
printf '%s\n' '{"command":"stop","hint":"switch-to-text"}' \
  | nc -U ~/.voicemode/control.sock
```

From Python:

```python
import json, socket, os

def control(command, **fields):
    path = os.path.expanduser("~/.voicemode/control.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(path)
        s.sendall((json.dumps({"command": command, **fields}) + "\n").encode())

control("stop", hint="switch-to-text", message="user can't talk right now")
```

VoiceMode's own client (what the CLI calls) is
`voice_mode.control_socket.send_control_command(command, message=None, hint=None,
socket_path=None)`, if you are importing the package.

## Security

- **Local-only.** The channel is a Unix domain socket, not a network port. There
  is no remote attack surface.
- **Off by default.** It does nothing until `VOICEMODE_CONTROL_CHANNEL_ENABLED=true`.
- **Owner-only.** The socket file is `0600`, so only your user can connect.
- **Low blast radius.** The only commands are pause / resume / stop of the
  current utterance — no code execution, no configuration changes.

## See also

- [Environment Variables](environment.md) — `VOICEMODE_CONTROL_CHANNEL_ENABLED`,
  `VOICEMODE_CONTROL_SOCKET`.
- [CLI Commands](cli.md) — the full `voicemode` command surface.
- [Architecture](../concepts/architecture.md) — the conch and the TTS path.
