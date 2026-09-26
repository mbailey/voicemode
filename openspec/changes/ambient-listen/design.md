<!-- PROPOSED. Cora 7, 03:25-03:45 Thu 2026-09-24. Measurements are marked
     with where they were taken; anything else is design. -->

## The shape, in one picture

```
  microphone ─┐                       ┌─> hook: lines past the cursor,
  Delta call ─┤  (kin writes the      │   printed on the next tool call
              │   same lines)         │   [heard] ...        (busy agent)
              ▼                       │
   listen ──> conversation log ───────┤
   (long-lived,   JSONL, append-only, │
    backgrounded) one line per        └─> listen returns: "a turn, aged"
                  partial/turn/event      (idle agent wakes)
```

Two readers, one file. A busy agent gets the words on the tool calls it is
already making. An idle agent makes no tool calls, so the only thing that
can reach it is a tool result: `listen` returning. That is exactly `pager
listen`'s split (ride-along for the busy, a page for the idle), and it is
why `listen` is a tool and not only a daemon: a daemon cannot wake a Claude
Code session; a returning tool call can.

## Components

### The writer: `listen`

- An MCP tool in the VoiceMode server, beside `converse`, with its own
  small capture loop (Mike, 03:32: a freshie). Voice activity by Silero or
  a plain silence timer; transcription behind one interface with two
  backends to start, whisper (today's server) and Apple's on-device
  recogniser. The ground-truth comparison is
  `~/.cora/apple-fm/research/streaming-eval.md` (19 Sep, m5): Apple
  SpeechTranscriber 1.5-1.9% WER, tied with Parakeet v3; whisper large-v2
  13.6% on 33 s turns. For previews, a Parakeet re-decode every 0.5 s beat
  Apple's fast results (3.9% against 13% at the moment speech stops), so
  the spike should try both for the `partial` line.
  Whether it can run beside a `converse` on the same device is measured
  in the spike, not assumed.
- Backgrounded by the harness. On m5 `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS`
  is 1000, so it leaves the foreground after one second; elsewhere the
  default is 120 s (Claude Code 2.1.270, `var V=120000`), which is still
  fine: `listen` returns nothing useful in its first two minutes anyway.
- Loop: capture, VAD, chunk, STT, append a `partial` line; on a detected
  end of turn append a `turn` line with the chunks joined; if the newest
  turn is older than `age` and nothing newer is being spoken, return.
- Returns on: an aged turn; an end word; the ceiling; a stop request; an
  error. The return names its reason and carries the cursor.
- Re-arm is the caller's job, as with `pager listen`: the boot letter's
  line is "arm it, and re-arm every time it fires".

### The log

- `~/.voicemode/logs/conversations/heard_YYYY-MM-DD.jsonl` (Q6; a sibling
  of `exchanges_*.jsonl`, same directory, same date rollover).
- One JSON object per line, append-only, never edited:

  ```
  {"ts":"2026-09-24T03:31:02.410+10:00","seq":418,"kind":"partial",
   "text":"so the bot will post what I say into","source":"mic",
   "device":"airpods","session":"927210d2-…","agent":"cora","final":false}
  {"ts":"…","seq":419,"kind":"turn","text":"so the bot will post what I say
   into the group","source":"mic","device":"airpods","final":true,
   "detector":"vad-silence","age_at_return":8.2}
  {"ts":"…","seq":420,"kind":"event","event":"wake-word","word":"hey
   claude","source":"mic","device":"airpods"}
  ```

- `kind` is `partial`, `turn` or `event`. `event` covers wake word, end
  word, barge-in, call started, call ended, device changed, listen
  started, listen stopped.
- `source` is `mic` or `call`; `device` is the OS device name for `mic`
  (measured 03:06: `sounddevice` reports `airpods`), or the account plus
  chat for `call`. kin's bridge writes `source: "call"` lines into the same
  file so the hook needs no second reader.
- `seq` is monotonic per file. The cursor is a `seq`.

### The cursor

- `~/.voicemode/state/heard-cursor/<session-id>` holds the last `seq` the
  hook has printed for that session. One file per session, so two agents
  reading one log do not advance each other.
- The hook advances it after printing; `listen`'s return advances it past
  the turn it returned, so the next hook does not repeat it.

### The hook

- Installed by the existing `voicemode claude hooks add` path
  (`voice_mode/cli_commands/claude.py`), so a user with VoiceMode and no
  sessionmail gets it. It runs on `PostToolUse` (and `PostToolBatch` where
  the harness offers it, so one print per batch, as sessionmail's pager
  does).
- Prints the lines past the cursor, oldest first, as `[heard mic/airpods
  03:31:02] …`, collapsing a run of partials into their turn when the turn
  has landed. Capped by a token budget (Q8), with `+k more, seq a-b` when
  it cuts.
- Silent when nothing is past the cursor. Never blocks; never claims.

### What `converse` does now

Nothing new. It keeps its contract: say, listen, return the reply. When
`listen` is armed, the agent speaks with `converse(wait_for_response:
false)`, which exists today, so there is no new speaking tool (Mike, 03:27:
*"it just speaks, and the listener is feeding it"*). Two
small courtesies: it writes its own listen window into the same log (as
`turn` lines with `via: "converse"`), so the record is one file; and it
reports the input device in its result (VM-1010), which costs one lookup.

### Wake on partial (Q3)

Off by default. When on, `listen` returns on a `partial` too, subject to
the same age. With a wake word configured, only a partial that follows the
wake word counts. The turn detector is unchanged; the wake word is a
string match on recognised text, not a separate acoustic model, for this
change.

## Measured tonight (03:06-03:24, m5)

- `sounddevice.default.device` in VoiceMode's own venv resolves to input
  `airpods`, output `airpods`, Core Audio; `query_devices()` lists 11
  devices. The device name is in hand and not surfaced.
- The conch is one lock file, `~/.voicemode/conch`, shared by every CLI and
  MCP process on the machine (`conch.py:102`, `conch_queue.py:159`); only
  the holder may speak (`config.py:601-602`). It says nothing about
  listening.
- `voicemode exchanges tail` follows `exchanges_YYYY-MM-DD.jsonl` via
  `tail -f` (`exchanges/reader.py:117`); the writer is
  `conversation_logger.py:125`. Two days of files exist.
- VoiceMode installs hooks into Claude Code settings but none reads a file
  back into context (`cli_commands/claude.py`, 0 hits for ride-along).
  VM-1282 (May) designed a Pre/PostToolUse pair around `converse` and was
  never built.
- kin's call path closes a chunk on 0.35 s of quiet and sends it to whisper
  as it closes (`calls.py:124`, `:766-770`), which is the `partial` line
  from the call side, already running.

## Unmeasured, on purpose

- **The ceiling on one backgrounded MCP call** (Mike: "about 29 minutes,
  I'm not sure"). Task 8 measures it. Until then `listen` re-arms on any
  ceiling, so the number is a restart, not a gap.
- **Two capture consumers on one microphone** when `listen` and `converse`
  run in the same session. The design says share; whether PortAudio on
  macOS lets the same process open the device twice is not tested.
- **Whisper under a long listen.** Chunked STT every few seconds for an
  hour has not been run locally. kin's calls do it for the length of a
  call.

## Risks

- **Context.** A busy agent that gets every partial on every tool call is
  the failure 1040 was designed against (a preview, "no extra turns"). The
  budget and the partial-collapse are the guard; the number is Q8.
- **Two ears.** If `listen` copies rather than shares the capture path,
  VoiceMode grows the second pipeline Pip warned about in kin (02:20). The
  spec makes sharing a requirement.
- **A stuck listener.** A `listen` that never returns and never writes is
  indistinguishable from silence. It SHALL write a `listen started` event
  at once and a heartbeat event on a period, so "nothing since 03:40" is
  visible in the log.
