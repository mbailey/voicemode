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

### Requirement: listen shares converse's capture path and never copies it

`listen` SHALL be built on the same microphone capture, voice activity
detection, chunking and speech-to-text client that `converse` uses, in the
same process, so that there is one pipeline in VoiceMode with two callers.
It MUST NOT open a second capture stream on a device that a `converse`
from the same session already has open; it SHALL share that stream. It
MUST NOT take the conch to listen: the conch governs speaking, and a
`listen` that held it would silence every other agent for its whole life.
PROPOSED, from Pip's finding on kin (02:20 Thu 2026-09-24) that `calls.py`
is a second copy of this pipeline and from Mike's aim (02:15) of one
experience; a second copy inside VoiceMode would be the same mistake one
repo over. Mike said at 03:27 that `listen` *"can be written from
scratch"*; this requirement reads that as a fresh tool on shared capture
objects, and the proposal's Q11 asks him whether that is what he meant.

#### Scenario: converse during listen shares the microphone

- GIVEN `listen` is running on the Mac's microphone for session S
- WHEN session S calls `converse`
- THEN `converse` reads from the stream `listen` holds
- AND no second stream is opened on the device

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
