# Control Channel Reference

The **control channel** is a side channel into the *running* VoiceMode server. It
lets an external trigger — a Stream Deck button, a media key, a spoken keyword,
or any local process — **pause, resume, stop, or skip back** through the
assistant's speech *without* going through the agent and *without* pressing ESC.

The headline idea is **"barge-in with a key"**: the value of cutting the
assistant off when it's talking too long or off-topic, but **deterministically**
(an explicit button or keyword) rather than via voice-activity guessing. Stopping
through this channel makes the `converse` tool return **normally** with a control
marker, so the agent reads a clean tool result and continues in text — no MCP
teardown, no `/mcp` reconnect.

Two transport styles share the one socket. **Cassette transport** —
pause / resume / stop — acts on the single in-flight utterance (VM-1676).
**CD transport** — `skip_back` — replays *already-spoken* audio from a small
history buffer: first press restarts the current/most-recent utterance, each
further press steps to the one before (VM-1685). A `status` query reads back
what's playing and where you are in the buffer. Replaying cached audio never
starts a new agent turn, so — like pause/resume/stop — it stays on the **safe**
side of the danger line.

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
voicemode control skip-back                             # replay the previous utterance (press again to step further back)
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
 (Unix socket)       (in the server)    (pause/stop/skip)      (cuts within ~one chunk)
                                              ▲                        │
                                              │ skip_back reads        ▼ every utterance
                                         history buffer  ◄──────  captured here
                                      (last N utterances)        (regardless of SAVE_AUDIO)
```

- The running server binds a **Unix domain socket** while it is speaking and
  listens for newline-delimited JSON commands.
- Each command flips a thread-safe in-process control state.
- The TTS playback loop polls that state every audio chunk (~85 ms), so a `stop`
  lands well under ~200 ms. A pending `skip_back` is read on the same poll. Both
  Kokoro and mlx-audio go through the same streaming path, so one mechanism
  covers both backends.
- As each utterance finishes, its decoded audio + text are captured into a small
  process-wide **history buffer** (regardless of `SAVE_AUDIO`). `skip_back`
  replays from that buffer — see [History buffer and CD-style skip-back](#history-buffer-and-cd-style-skip-back).
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
| `VOICEMODE_HISTORY_BUFFER_SIZE` | How many recent utterances `skip_back` can replay (ring-buffer depth, ≥1) | `8` |

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
{"command": "skip_back"}
```

| Field | Type | Required | Applies to | Meaning |
|-------|------|----------|------------|---------|
| `command` | string | yes | all | One of `pause`, `resume`, `stop`, `skip_back`. |
| `hint` | string | no | `stop` | A **named intent** from the allowlist (below). Selects the fixed, server-authored sentence surfaced in the converse return. An unknown hint is **rejected**. |
| `message` | string | no | `stop` | Free-text note recorded in the **server log only**. It is **never** surfaced to the agent (security: prompt-injection, VM-1691). ≤256 chars. |

These four commands are **fire-and-forget**: the server applies them and writes
nothing back. There is one **request/response** verb — `status` — which is *not*
a command (it mutates nothing) and returns one JSON line; see
[The "now playing" status query](#the-now-playing-status-query).

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
- **`skip_back`** — replay an already-spoken utterance from the history buffer
  (CD transport). First press restarts the current/most-recent utterance; each
  further press steps to the one before. A one-shot, *non-sticky* transport
  request (it never latches like `stop`). Re-plays cached audio only — no new
  agent turn. Full semantics in
  [History buffer and CD-style skip-back](#history-buffer-and-cd-style-skip-back).

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

## History buffer and CD-style skip-back

Where pause/resume/stop are **cassette transport** (they act on the one stream
that's playing *now*), `skip_back` is **CD transport**: it jumps back through the
utterances the assistant *already spoke* and replays the cached audio. That needs
the server to remember what it said, which is the **history buffer**.

### The history buffer

A small, process-wide ring buffer keeps the last **N rendered utterances**. Each
record holds the **decoded PCM audio** (so it can be replayed with no re-render
and no second TTS call), the **text**, and a little metadata
(`sample_rate`, `channels`, `timestamp`, `voice`).

- **Captured regardless of `SAVE_AUDIO`.** The buffer is fed straight from the
  playback path as each utterance plays, so skip-back works even when you aren't
  writing audio files to disk. (`SAVE_AUDIO` still controls the on-disk copy;
  it's independent of this in-memory buffer.)
- **Completed utterances only.** A record is added when an utterance finishes
  naturally. An utterance cut short by `stop` (or aborted by a `skip_back` mid-
  playback) is **not** captured — the buffer holds whole renders, so a replay is
  never a truncated fragment.
- **Bounded.** It's a `deque(maxlen=N)`; appending past N evicts the oldest, so
  memory stays capped. N is `VOICEMODE_HISTORY_BUFFER_SIZE` (default **8**, min 1).
  Raw PCM is large — at the 24 kHz mono 16-bit default, audio costs ~48 KB/s, so
  a 10 s utterance is ~470 KB and a full buffer of 8 such utterances ~3.8 MB.
  Keep N small.
- **Process lifetime.** The buffer lives for the life of the server process; it
  is **not** persisted across restarts. It accumulates across conversation turns
  within the process (it isn't cleared per turn).

### CD-player cursor semantics

`skip_back` walks the buffer from newest to oldest, exactly like pressing ⏮ on a
CD player:

- **First press** — restart the **current / most-recent** utterance from its
  start ("the bit from just before").
- **Each further press** — step back one more utterance: the one before that,
  then the one before that …
- **Clamped at the oldest.** Once you reach the oldest record still in the
  buffer, further presses just keep replaying it (a CD stays on track 1; it
  doesn't wrap or error).

> **Mid-playback nuance (worth knowing).** If you press `skip_back` *while* an
> utterance is still streaming, the server aborts that in-flight stream
> immediately (a responsive barge-in) and replays the most-recent **completed**
> utterance — *not* a from-the-top restart of the one that was mid-flight. That
> utterance isn't in the buffer until it finishes (and replaying a half-spoken
> fragment would drop the part you hadn't heard yet), so "replay the previous
> completed utterance" is the consistent rule. In practice that matches the
> intent — *replay the bit from just before* — but it's a deliberate divergence
> from a literal "restart the current utterance from its start" for the
> mid-stream case.

### Composing with pause, and stop's precedence

- **Composes with `pause`.** Pause the assistant, then `skip_back` to re-hear the
  bit from just before: the replay lifts the hold and plays the cached audio from
  its start — it does **not** un-pause forward into the *next* utterance. Pausing
  *during* a replay holds the replay, like any other playback.
- **`stop` wins.** If a `stop` and a `skip_back` are both pending, `stop` takes
  precedence — a late `skip_back` can't revive an utterance you just cut into a
  replay. The transport request is non-sticky and one-shot (consumed when read,
  dropped on the next turn's reset); the `stop` latch is unaffected by it.

### Safe by construction

Replay is a **playback-layer** operation. It re-plays audio the server already
produced — **no STT, no model call, no new agent turn**. So, like
pause/resume/stop, `skip_back` stays on the **safe** side of the danger line and
needs no dangerous-channels flag. The worst a `skip_back` can do is make the
assistant repeat itself.

## The "now playing" status query

Alongside the fire-and-forget commands, the socket answers one **request/response**
query: send `{"command":"status"}` and the server writes back **one JSON line**
describing what's playing and where you are in the history buffer. It's modelled
on the local-IPC "now playing" conventions of MPV (`--input-ipc-server`), Neovim
(`--listen`), and tmux — an explicit `ok` flag and an echoed `request_id` for
correlation.

`status` is **not** in `VALID_COMMANDS`: it mutates nothing, so it's a read-side
query, kept cleanly separate from the command schema. The fire-and-forget path
for pause/resume/stop/skip_back is untouched — those still write nothing back.

```jsonc
// → request
{"command": "status", "request_id": 1}

// ← response (one line)
{
  "ok": true,
  "action": "status",
  "request_id": 1,
  "state": "running",                 // running | paused | stopped
  "pending_transport": null,          // "skip_back" if a press is queued, else null
  "buffer": {"depth": 3, "capacity": 8},
  "now_playing": {                    // null when the buffer is empty
    "index": 2,                       // position in the buffer (0 = oldest)
    "text": "Here's the summary you asked for.",
    "duration": 3.42,                 // seconds, derived from the PCM length
    "sample_rate": 24000,
    "channels": 1,
    "timestamp": 1750000000.0,        // epoch seconds, when it was captured
    "voice": "af_sky"
  }
}
```

Two things to read precisely:

- **`now_playing` is the most-recent *completed* utterance** (the newest buffer
  entry — exactly what a first `skip_back` would replay). Because the buffer only
  captures an utterance once it finishes, *during* live playback `now_playing` is
  the **previous** completed utterance while `state` reflects the live transport.
  `now_playing.index` is therefore always `depth − 1` (the replay anchor), not a
  live skip-back cursor — the cursor is ephemeral and isn't shared state.
- **The query never consumes a `skip_back`.** `pending_transport` is a
  non-destructive *peek*; a status query reports a queued press without eating it,
  so the playback loop still sees and acts on the real press.

There is **no `voicemode control status` CLI verb** in v1 — the status read-side
is for programmatic clients (a Stream Deck "now playing" display, a status pane).
Query it from the raw socket, or from Python via
`voice_mode.control_socket.query_status(socket_path=None, timeout=2.0,
request_id=None)`, which returns the parsed dict above (and raises
`FileNotFoundError` when nothing is listening). See
[Raw socket](#raw-socket-no-cli) for a shell one-liner.

## The `voicemode control` CLI

The CLI is the reference client — the "second local process" that proves the
channel is reusable. It writes exactly one JSON line to the socket and exits.

```
voicemode control pause      [--message TEXT] [--hint TEXT] [--socket PATH]
voicemode control resume     [--message TEXT] [--hint TEXT] [--socket PATH]
voicemode control stop       [--message TEXT] [--hint TEXT] [--socket PATH]
voicemode control skip-back  [--message TEXT] [--hint TEXT] [--socket PATH]
```

> **CLI verb is hyphenated, wire word is underscored.** `voicemode control
> skip-back` sends `{"command":"skip_back"}` — the exact word the Stream Deck
> `deck.py` and other triggers put on the wire. (`--hint` / `--message` are
> accepted for surface symmetry but only `stop` acts on them.)

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

```bash
# "Skip back" button — replay the previous utterance (press again to step further back)
voicemode control skip-back
```

If your Stream Deck plugin needs an absolute path, find it with `which voicemode`
(or use `uvx voice-mode control stop`).

> **Deck `SKIP_ENABLED` flip — cross-repo follow-up (gated on VM-1739).** The
> Stream Deck integration `skills/streamdeck/scripts/deck.py` (in the **skillbox**
> repo, *outside* this one — SKB-854) already sends `control_send("skip_back")`
> and `control_send("skip_forward")`, but its skip buttons are dim placeholders
> behind a single `SKIP_ENABLED = False` flag that lights **both** at once. VM-1685
> makes `skip_back` work server-side; `skip_forward` is its sibling task
> [VM-1739](https://github.com/mbailey/voicemode). Because one flag lights both
> buttons, flipping `SKIP_ENABLED = True` in `deck.py` is deferred until VM-1739
> also lands — otherwise the skip-forward button would light but do nothing.
> Until then, drive skip-back from a plain *System → Open* button (above), which
> works today.

### Media keys

The keyboard's transport keys (▶❙❙ / ⏭ / ⏮ — and a Bluetooth headset's
play/pause) make a natural control surface. There are two ways to wire them,
depending on how much you want VoiceMode to share the keys with your music.

#### Hammerspoon — ownership-aware (recommended on macOS)

macOS routes the media keys (NSSystemDefined events) straight to Music/Spotify,
so to use them for VoiceMode you need an interceptor that wins *first* — but you
almost certainly don't want VoiceMode stealing play/pause during normal
listening. [Hammerspoon](https://www.hammerspoon.org/) handles both: its
`hs.eventtap` can pass an event through to the media app *or* swallow it,
**per-event**, based on whether a converse is live.

The reusable config ships in the repo:
[`scripts/hammerspoon/voicemode-media-keys.lua`](https://github.com/mbailey/voicemode/blob/master/scripts/hammerspoon/voicemode-media-keys.lua).

**Ownership model — "polite spot-instance".** VoiceMode only grabs the media keys
while a converse is *live*; otherwise every key passes straight through to your
media app, unchanged:

| Key | No converse live | Converse live (VoiceMode owns) |
|-----|------------------|--------------------------------|
| **Play/Pause** | toggles music (pass-through) | pauses/resumes **VoiceMode only** — key swallowed, media untouched *(default)*; set `pauseEverything = true` to also toggle music |
| **Next** | next track | **barge** — cuts the utterance (`control stop`); music does **not** skip |
| **Previous** | previous track | replay last utterance — server side now works (`control skip-back`, VM-1685); the **shipped Hammerspoon binding is still a stub** (no-op + notice) pending a wire-up |

**Play/Pause scope (`pauseEverything`).** By default, while a converse is live
Play/Pause controls **only VoiceMode** and the key is *swallowed*, so your media
app is left alone (it won't start a paused track). Set `pauseEverything = true`
to restore "pause everything" — the key also passes through so the media app
toggles too (one press quiets both). Either way, when no converse is live
Play/Pause passes straight through to your media app. Next/Previous *do* conflict
(barge vs skip-track), so they route to whichever side owns the keys.

**Manual override.** A menubar item (`VM⌨︎:auto`) and a hotkey
(<kbd>⌘</kbd><kbd>⌥</kbd><kbd>⌃</kbd><kbd>M</kbd>) cycle ownership
`auto → always-me → always-music`. `always-me` forces VoiceMode to own
Next/Previous even when no converse is live; `always-music` forces pass-through
even mid-utterance. (The override governs Next/Previous; Play/Pause scope is set
by `pauseEverything`.)

**Setup:**

1. **Enable the channel** (server side, once): `VOICEMODE_CONTROL_CHANNEL_ENABLED=true`
   in `~/.voicemode/voicemode.env`. Without it the socket is never bound and the
   config can never see a converse as "live".
2. **Install Hammerspoon:** `brew install --cask hammerspoon`.
3. **Load the config** from `~/.hammerspoon/init.lua` (point the path at your
   checkout):

    ```lua
    -- ~/.hammerspoon/init.lua
    -- Optional config (all keys have sane defaults):
    -- _G.voicemodeMediaKeys = {
    --   voicemodePath   = "/opt/homebrew/bin/voicemode",
    --   pauseEverything = true,   -- Play/Pause also toggles your media app (default false)
    -- }
    dofile(os.getenv("HOME") .. "/Code/voicemode/scripts/hammerspoon/voicemode-media-keys.lua")
    ```

    Then **Reload Config** from the Hammerspoon menubar (or run `hs.reload()`).
4. **Grant Accessibility** — this is the load-bearing permission. System Settings
   → **Privacy & Security → Accessibility** → enable **Hammerspoon**. The event
   tap cannot see (or swallow) key events until you do; Hammerspoon prompts on
   first run. Some setups also need **Input Monitoring**.

The config resolves an absolute `voicemode` path at load (media-key handlers
don't inherit your shell `PATH`) and shells out non-blocking, so a keypress is
never delayed by the control command.

> **Music/Spotify pre-emption gotcha (`pauseEverything = true` only).** With
> `pauseEverything` enabled, Play/Pause is *passed through* to the frontmost media
> app, which toggles regardless of its own state — so if music is **paused** and
> you press Play to quiet a VoiceMode utterance, the music will **start** (a single
> toggle can't know which direction you meant). The **default**
> (`pauseEverything = false`) avoids this: while a converse is live the key is
> *swallowed* and only VoiceMode pauses. Next/Previous never have this problem —
> when VoiceMode owns them the event is fully swallowed, so the media app never
> skips. If a key still reaches the media app when VoiceMode should own it,
> re-check that Accessibility is granted and the menubar shows `VM⌨︎`.

> **Keyboard key names vary.** Some keyboards — notably the **Logitech MX Keys
> Mini** — report the next/previous-track keys as `FAST`/`REWIND` rather than
> `NEXT`/`PREVIOUS`. The config normalises both, so next-track barges and
> previous-track replays regardless of which name your keyboard emits (verified
> live on an MX Keys Mini, VM-1724). If a media key seems to do nothing, open the
> Hammerspoon Console and check the `systemKey` name it reports.

**Verify:**

- The Hammerspoon Console logs `[voicemode-media-keys] started (...)` on load and
  a line for each action (`barge`, `pause`, `resume`).
- **No converse running:** media keys behave exactly as before — music only.
- **Converse live** (start one, let VoiceMode speak): **Next** cuts it (barge),
  **Play/Pause** pauses VoiceMode (and your media app too if `pauseEverything =
  true`), **Previous** shows the replay-not-yet stub.
- Offline logic test (no Hammerspoon needed):
  `luajit scripts/hammerspoon/test_voicemode_media_keys.lua`.

> **Liveness signal.** "Is a converse live?" is answered by the presence of the
> control socket `~/.voicemode/control.sock`, which the server binds for the whole
> converse turn (speaking *and* listening). The config stats it on each key event
> — cheap, no subprocess. A socket left stale by a server that crashed
> mid-utterance is the only false-positive; it clears on the next converse.

#### Simple, unconditional bindings (skhd / xbindkeys / Karabiner)

If you want a key wired *straight* to one command (no ownership logic, no
pass-through to music), bind it to the CLI with any key-binding tool. For example
with [`skhd`](https://github.com/koekeishiya/skhd) on macOS:

```
# ~/.skhdrc — F8 stops, F7 pauses, F9 resumes
0x64 : voicemode control stop --hint switch-to-text
0x65 : voicemode control pause
0x67 : voicemode control resume
```

The same idea works with `xbindkeys` on Linux, Karabiner-Elements, or any tool
that can bind a key to a shell command. Note these bind a *dedicated* key — they
don't share the transport keys with your music the way the Hammerspoon recipe
does.

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

# skip back to replay the previous utterance
printf '%s\n' '{"command":"skip_back"}' | nc -U ~/.voicemode/control.sock

# query "now playing" — this one writes a JSON line back
printf '%s\n' '{"command":"status"}' | nc -U ~/.voicemode/control.sock
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
control("skip_back")
```

`hint` must be one of the named intents (`switch-to-text`, `brevity`, `quiet`);
an unknown hint is rejected. VoiceMode's own clients (what the CLI calls) are
`voice_mode.control_socket.send_control_command(command, message=None, hint=None,
socket_path=None)` for the fire-and-forget commands and
`voice_mode.control_socket.query_status(socket_path=None, timeout=2.0,
request_id=None)` for the now-playing read — both validate / frame against the
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
- **Bounded blast radius — but not zero for an agentic client.** The verbs are
  pause / resume / stop / skip_back; the channel itself runs no code and changes
  no config. The realistic worst case is *influencing* an agent's turn via the
  intent set, which is why intents are server-authored and the peer check gates
  who can send them.
- **`skip_back` adds no new agent surface.** It replays TTS the server already
  produced — no new agent turn, no STT, no model call — so it can't inject
  anything into the agent; the worst it can do is make the assistant repeat
  itself. The `status` read-side only *exposes* our own rendered text to a
  same-uid local client (the reverse of the injection direction) and rides the
  same peer-credential gate, so it adds no foreign-access surface either.
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
  `VOICEMODE_CONTROL_SOCKET`, `VOICEMODE_HISTORY_BUFFER_SIZE`.
- [CLI Commands](cli.md) — the full `voicemode` command surface.
- [Architecture](../concepts/architecture.md) — the conch and the TTS path.
