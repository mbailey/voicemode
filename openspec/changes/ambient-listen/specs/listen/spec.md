## ADDED Requirements

### Requirement: listen is a long-lived tool that returns on an aged end of turn, not at the end of a turn

VoiceMode SHALL provide a tool named `listen` that starts capturing speech
on a source and does not return when the speaker pauses or when a turn is
detected. It SHALL return only when one of these is true: a detected end
of turn is older than the configured `age` and nothing newer is being
spoken; an end word was heard; the configured ceiling on one call was
reached; the caller asked it to stop; or it failed. Its return SHALL name
which of those happened and carry the cursor position after the last line
it wrote, so the caller can re-arm without re-reading. `listen` MUST NOT
buffer what it hears until it returns: every partial and every turn is
written to the conversation log as it is recognised (see *conversation
log*). `converse`'s contract is unchanged by this requirement: it still
says, listens once, and returns the reply. RULED in substance by Mike,
voice 03:20 Thu 2026-09-24: *"it gets backgrounded, it doesn't return
unless there's an end of turn detected that's more than a certain age, so
that we're basically getting ride-along"*; and 03:23: *"this is a change
in behaviour, so I do feel like we want to make a new tool"*. The name
`listen` is PROPOSED (Q1).

#### Scenario: A pause does not return

- GIVEN `listen` is running with `age` of 8 s
- WHEN the speaker stops for 3 s and starts again
- THEN `listen` does not return
- AND the words on both sides of the pause are in the log as partials

#### Scenario: An aged turn returns

- GIVEN `listen` is running with `age` of 8 s
- WHEN an end of turn is detected and 8 s pass with no new speech
- THEN `listen` returns with reason `turn`, the turn's text, and the cursor

#### Scenario: An end word returns at once

- GIVEN `listen` is running and "over" is a configured end word
- WHEN the speaker says "over"
- THEN `listen` writes an `event` line for the end word
- AND returns with reason `end-word` without waiting for `age`

#### Scenario: The ceiling is a restart, not a gap

- GIVEN `listen` has run for the configured ceiling
- WHEN the ceiling is reached mid-speech
- THEN `listen` returns with reason `ceiling` and the cursor
- AND the partials written so far are in the log, so the re-armed `listen`
  loses nothing already recognised

### Requirement: listen is a fresh, small listener, built as a spike on a branch, and it never takes the conch

`listen` SHALL be a new, small implementation of its own: capture, voice
activity detection, chunking and transcription chosen for this tool, not
inherited from `converse`'s capture path. It MAY borrow pieces of the
existing code where they are the right pieces, and it MUST NOT depend on
`converse`'s internals in a way that makes either one hard to change. Its
first form SHALL be a spike on a branch: a tool that does not return,
detects an end of turn by silence (the current two seconds, or Silero
VAD), and writes what it hears to the log. Transcription SHALL be
pluggable, with Apple's on-device speech recognition as an option beside
whisper, so that a user of `listen` need not install whisper. `listen`
MUST NOT take the conch: the conch governs speaking, and a `listen` that
held it would silence every other agent for its whole life. RULED by Mike,
voice 03:29-03:32 Thu 2026-09-24: *"why does it have to share the same
ears? This is an opportunity to write a freshie ... quite easy to do as a
spike, on a branch: a listen tool that doesn't return ... we can use
Silero, which is meant to be better ... learn from the old one and maybe
use some of it, but not to save time and energy: make a small, clean,
fresh thing."* Apple transcription: *"you did some experiments on Thursday
and found that it had a much better accuracy rate"*. The measurement is
`~/.cora/apple-fm/research/streaming-eval.md` (m5, Sat 2026-09-19
02:50-04:50, ground truth on read speech): Apple SpeechTranscriber and
Parakeet v3 tie at 1.5-1.9% WER; whisper large-v2, VoiceMode's model
today, gets 2.2% on single sentences and 13.6% on 33 s turns. Apple's
`.fastResults` streams first words 0.8 s in with a final 80 ms after
speech stops; its live preview is 13% WER against 3.9% for a Parakeet
re-decode every 0.5 s. Whether two capture
streams on one device coexist on macOS is unmeasured (tasks 8.3); the
spike measures it before `converse` and `listen` are run together.

#### Scenario: The spike does the least that proves the shape

- GIVEN the spike branch's `listen` on the Mac's microphone
- WHEN the speaker talks, pauses two seconds, and talks again
- THEN partials and one turn are in the log before anything returns
- AND `listen` returns only when that turn is older than `age`

#### Scenario: Transcription is chosen, not assumed

- GIVEN a machine with no whisper installed and Apple speech available
- WHEN `listen` starts with the Apple backend configured
- THEN it transcribes and writes partials
- AND no whisper endpoint is contacted

#### Scenario: listen does not hold the conch

- GIVEN `listen` is running for agent A
- WHEN agent B calls `converse` on the same machine
- THEN B acquires the conch and speaks
- AND A's `listen` keeps writing partials throughout

### Requirement: a partial wakes an idle session only if configured, and then only after the wake word if one is set

By default `listen` SHALL treat only an aged end of turn as a reason to
return; a partial SHALL NOT return. When `wake_on_partial` is enabled,
`listen` MAY return on a partial older than `age`. When a wake word is
configured as well, only a partial that follows a recognised wake word in
the same listen SHALL count; partials before it are written to the log
and do not return. The wake word SHALL be matched as text on the
recognised speech and written as an `event` line; this change adds no
acoustic wake-word model. RULED in substance by Mike, voice 03:21 Thu
2026-09-24: *"whether an idle session gets woken by a partial, that's
configurable ... maybe only if there's a wake word like hey Claude"*. The
default of off is PROPOSED (Q3).

#### Scenario: Default: a partial does not return

- GIVEN `listen` is running with defaults
- WHEN the speaker talks for 40 s without an end of turn
- THEN `listen` does not return
- AND the partials are in the log for the hook to show

#### Scenario: Wake word gates the partial return

- GIVEN `wake_on_partial` is on and the wake word is "hey claude"
- WHEN the speaker says "I'll sort the van later, hey Claude, what's the
  time"
- THEN an `event` line records the wake word
- AND `listen` returns on the partial after it, not on the one before

### Requirement: listen proves it is alive in the log

Within one second of starting, `listen` SHALL write a `listen started`
event line naming its source and device, and while running it SHALL write
a heartbeat event on a configured period (default 60 s) so that a reader
of the log can tell a silent room from a dead listener. On any exit it
SHALL write a `listen stopped` event with the reason. PROPOSED, from Cora's
Charter 2 ("zero is a claim"): a listener that has heard nothing must be
distinguishable from one that is not listening.

#### Scenario: A silent room is visible as heartbeats

- GIVEN `listen` has been running for five minutes in silence
- WHEN the log is read
- THEN it shows the `listen started` line and five heartbeat lines
- AND no partials

#### Scenario: A dead listener is visible as a missing heartbeat

- GIVEN `listen`'s process died at 03:40
- WHEN the log is read at 03:45
- THEN the last heartbeat is at or before 03:40 and there is no `listen
  stopped` line
