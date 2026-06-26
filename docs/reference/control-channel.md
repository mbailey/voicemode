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
voicemode control stop --hint switch-to-text            # cut + tell the agent to go to text
voicemode control pause                                 # hold playback
voicemode control resume                                # resume after a pause
```

> **What the agent sees is server-controlled.** `--hint` names an *intent* from a
> fixed allowlist; the server owns the exact sentence the agent reads. Free-form
> caller text is **never** surfaced to the agent — see [Security](#security).

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
| `VOICEMODE_CONTROL_PAUSE_TIMEOUT` | Seconds before a never-resumed `pause` self-heals (0 disables) | `30` |
| `VOICEMODE_CONTROL_PAUSE_TIMEOUT_ACTION` | What a timed-out pause does: `stop` or `resume` | `stop` |

The channel is **off by default**: enabling it binds a Unix socket that any
*same-user* local process (enforced by a peer-credential check) can drive, so it
stays opt-in. When disabled, the listener is never started and the CLI has
nothing to talk to. See [Security](#security) for the full model.

## Socket

- **Type:** `AF_UNIX` / `SOCK_STREAM` (no TCP port — every trigger runs on the
  same machine as the server).
- **Path:** `~/.voicemode/control.sock` by default (override with
  `VOICEMODE_CONTROL_SOCKET`), beside the conch under `~/.voicemode/`.
- **Permissions:** parent dir `0700` and socket bound under `umask(0o077)`; the
  authoritative gate is the **peer-credential check** (same-UID only) on connect,
  since socket-file mode isn't reliably enforced on macOS/BSD.
- **Pause safety:** a `pause` that is never resumed auto-resolves after
  `VOICEMODE_CONTROL_PAUSE_TIMEOUT` seconds (default 30) so it can't wedge the
  audio subsystem.
- **Lifecycle:** bound only while the server is speaking; unlinked on exit. A
  stale socket left by a crashed server is cleared with unlink-then-bind.

## Command schema

Commands are **newline-delimited JSON**, one command per line. Send as many lines
as you like down a single connection.

```json
{"command": "pause"}
{"command": "resume"}
{"command": "stop"}
{"command": "stop", "hint": "switch-to-text"}
```

| Field | Type | Required | Applies to | Meaning |
|-------|------|----------|------------|---------|
| `command` | string | yes | all | One of `pause`, `resume`, `stop`. |
| `hint` | string | no | `stop` | A **named intent** from the allowlist (below). Selects the fixed, server-authored sentence surfaced in the converse return. An unknown hint is **rejected**. |
| `message` | string | no | `stop` | Free-text note recorded in the **server log only**. It is **never** surfaced to the agent (security: prompt-injection, VM-1691). ≤256 chars. |

**Named intents** (the only values `hint` accepts — the server controls the
words the model sees, not the caller):

| Intent | Sentence the agent receives |
|--------|------------------------------|
| `switch-to-text` | user switched to text mode — continue in text, don't speak |
| `brevity` | user asked you to be brief — keep replies short |
| `quiet` | user asked you to stop talking for now |

**Limits.** A control line is capped at 8 KiB and `message` at 256 chars; both
are rejected over the cap. Anything malformed (bad JSON, unknown command, unknown
hint, non-string or over-long fields) is logged and ignored — a bad line never
crashes the server.

> **`volume` is a documented stretch goal**, not implemented in v1. The schema
> reserves `{"command": "volume", "level": 0..100}`; sending it today is rejected
> as an unknown command.

### Commands

- **`pause`** — hold playback. Audio stops writing and waits (no busy-spin) until
  `resume` or `stop`. No-op once stopped.
- **`resume`** — resume playback after a `pause`. No-op once stopped.
- **`stop`** — cut the in-flight utterance cleanly. Sticky and terminal until the
  next utterance resets it; the first `stop`'s `hint` wins. This is the primary,
  load-bearing command.

### Stop behaviour

A `stop` is **not** ESC. When it arrives, `converse` returns **normally**
(success), with a control marker prepended to a **server-authored** sentence
chosen by the `hint` intent (never the caller's free text):

```
[control: stop] user switched to text mode — continue in text, don't speak | Timing: ...
```

With no `hint`, the detail is the generic `playback stopped via control channel`.

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
| `--hint` | Named intent (`switch-to-text`, `brevity`, `quiet`); selects the server's sentence on `stop`. Unknown values are rejected. |
| `--message`, `-m` | Free-text note for the **server log only** — not shown to the agent. |
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
# "Text mode" button — cut the assistant off and tell the agent to continue in text
voicemode control stop --hint switch-to-text
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

control("stop", hint="switch-to-text")
```

`hint` must be one of the named intents (`switch-to-text`, `brevity`, `quiet`);
an unknown hint is rejected. VoiceMode's own client (what the CLI calls) is
`voice_mode.control_socket.send_control_command(command, message=None, hint=None,
socket_path=None)`, if you are importing the package — it validates against the
same schema before anything goes on the wire.

## Security

Enabling the channel lets **any local process that passes the access check
influence the agent's current turn**. Treat that as the real model — the points
below are honest about what is and isn't guaranteed (security review, VM-1688).

- **Off by default — the strongest mitigation.** Nothing binds or listens until
  `VOICEMODE_CONTROL_CHANNEL_ENABLED=true`. Leave it off unless you want it.
- **Same-user only (enforced by a peer-credential check).** On every connection
  the server checks the peer's UID (`SO_PEERCRED` on Linux, `LOCAL_PEERCRED` on
  macOS/BSD) and rejects anyone who isn't you. This — not the file mode — is the
  real access control. Socket-file `0600` is **not** reliably enforced on
  macOS/BSD (access is governed by the directory), so the parent dir is created
  `0700` and the socket is bound under `umask(0o077)` as defence in depth.
- **No free-form text reaches the agent.** A `stop`'s `hint` is a **named intent**
  from a fixed allowlist; the server owns the exact sentence the model reads. A
  free-form `message` is logged on the server only, never surfaced. This closes
  the prompt-injection path (a local process can't put instructions into an agent
  that holds shell/file tools). Input is length-capped (8 KiB line, 256-char
  message) to bound cost and memory.
- **Bounded blast radius — but not zero for an agentic client.** The only verbs
  are pause / resume / stop; the channel itself runs no code and changes no
  config. The realistic worst case is *influencing* an agent's turn via the
  intent set, which is why intents are server-authored and the peer check gates
  who can send them.
- **"Local" is about the socket, not the system.** The socket has no network
  surface. But the triggers this feature invites — media keys, Bluetooth
  play/pause, a spoken-keyword/wake-word path — can extend the reach to *radio*
  and *room audio*. If you wire those, anything that can drive them can drive the
  channel; scope them accordingly.
- **Stale-socket safety.** The listener refuses to unlink anything at the socket
  path that isn't a socket it owns, so a squatted file can't be clobbered or used
  to intercept commands.

## See also

- [Environment Variables](environment.md) — `VOICEMODE_CONTROL_CHANNEL_ENABLED`,
  `VOICEMODE_CONTROL_SOCKET`.
- [CLI Commands](cli.md) — the full `voicemode` command surface.
- [Architecture](../concepts/architecture.md) — the conch and the TTS path.
