## ADDED Requirements

### Requirement: What is heard is written as one JSON line per partial, turn or event, the same shape from every source

VoiceMode SHALL keep an append-only JSON-lines log of what it hears,
written as it is recognised, in `~/.voicemode/logs/conversations/` beside
the existing exchange log and rolling by date the same way. Each line
SHALL be one object with at least: `ts` (ISO 8601 with offset), `seq`
(monotonic within the file), `kind` (`partial`, `turn` or `event`),
`text` for partials and turns, `source` (`mic` or `call`), `device` (see
*every line names its device*), `session` and `agent` where known, and
`final` (false for a partial that a later turn will subsume). A `turn`
line SHALL carry the joined text of its partials and the name of the
detector that ended it. An `event` line SHALL name its event: wake word,
end word, barge-in, call started, call ended, device changed, listen
started, listen stopped, heartbeat. Lines MUST NOT be edited or removed;
a correction is a new line. A writer other than VoiceMode (kin's Delta
bridge, for a call) SHALL write lines of this same shape into this same
file, so that one reader serves every source. RULED in substance by Mike,
voice 03:19 Thu 2026-09-24: *"the ride-along comes off the conversation
log ... it's already JSONL"* and 03:07: *"writing JSONL to a file, which
we already do with the conversation logs"*. The sibling-file choice is
PROPOSED (Q6).

#### Scenario: A turn subsumes its partials

- GIVEN three partial lines for one utterance, `final: false`
- WHEN the end of turn is detected
- THEN one `turn` line is appended with the joined text and `final: true`
- AND the three partial lines remain, unedited

#### Scenario: A call writes the same shape

- GIVEN a Delta Chat call handled by kin's bridge
- WHEN the caller speaks
- THEN kin appends `partial` and `turn` lines with `source: "call"` and
  the account and chat as `device`
- AND the same hook shows them with no change

### Requirement: A per-session cursor marks what the agent has been shown, and the hook shows only what is past it, within a budget

VoiceMode SHALL keep, per Claude Code session, a cursor holding the
highest `seq` that has been shown to that session, in a file under
`~/.voicemode/state/`. The ride-along hook SHALL print the lines with
`seq` greater than the cursor, oldest first, collapsing a run of partials
into their turn when the turn is present, and SHALL then advance the
cursor. The output SHALL be bounded by a configured token budget; when it
cuts, it SHALL say how many lines it left and their `seq` range, and it
MUST NOT advance the cursor past what it printed. When `listen` returns a
turn to wake an idle session, it SHALL advance the cursor past that turn
so the next hook does not repeat it. Two sessions reading one log SHALL
have two cursors. RULED in substance by Mike, voice 03:19 Thu 2026-09-24:
*"it uses a seen cursor, and we have a hook that provides some of the
stuff. It probably doesn't need to provide all the stuff because we should
be context conservative."* The budget's number is PROPOSED (Q8).

#### Scenario: A busy agent sees the words on its next tool call

- GIVEN `listen` has written six partials and one turn since the cursor
- WHEN the agent's next tool call completes
- THEN the hook prints the turn once, with its device and time
- AND advances the cursor to the turn's `seq`

#### Scenario: The budget cuts without losing lines

- GIVEN forty lines past the cursor and a budget that fits twelve
- WHEN the hook runs
- THEN it prints the oldest twelve and `+28 more, seq 431-458`
- AND the cursor moves to `seq` 430, so the next call shows from 431

#### Scenario: Two agents, two cursors

- GIVEN Cora's and Pip's sessions both read one log
- WHEN Cora's hook advances Cora's cursor
- THEN Pip's cursor is unchanged and Pip's next hook shows the same lines

### Requirement: The hook is VoiceMode's own and needs nothing else installed; mail is a second consumer, not the first

The ride-along hook SHALL be installed by VoiceMode's existing hook
installer (`voicemode claude hooks add`) and SHALL depend on nothing
outside VoiceMode: no sessionmail, no postfix, no pager. It SHALL be
silent when nothing is past the cursor, SHALL never block, and MUST NOT
delete, move or claim log lines. Delivering the same lines as mail SHALL
be an optional, separately enabled consumer of the same log, and the hook
SHALL read whichever consumer is configured. RULED by Mike, voice 03:22
Thu 2026-09-24: *"files would be the quickest thing, because then we don't
need to have session mail ready and people don't need to use it ... files
with the hook as the default, simple, VoiceMode-only, and then we could
add mail as a simple option."* Whether the mail consumer is in this change
is PROPOSED (Q9: the next).

#### Scenario: A user with VoiceMode alone gets the ride-along

- GIVEN a machine with VoiceMode installed and no sessionmail
- WHEN the user runs `voicemode claude hooks add heard`
- THEN the hook is in their Claude Code settings
- AND their agent sees heard lines on its next tool call after speech

#### Scenario: The hook never claims a line

- GIVEN the hook has printed lines 400-412
- WHEN a second reader (`voicemode exchanges tail`, or mail) reads the log
- THEN lines 400-412 are still there, unchanged

### Requirement: Every line names its device, and device identity is not person identity

Every `partial`, `turn` and `event` line SHALL carry the device it came
from: for `source: "mic"`, the operating system's name for the input
device as the audio library reports it (for example `airpods`, `MacBook
Pro Microphone`); for `source: "call"`, the account and chat of the call.
When the input device changes during a listen, VoiceMode SHALL write a
`device changed` event before the first line from the new device.
`converse` SHALL report the input device in its result as well. A device
label SHALL be treated as evidence of WHERE the words came from and MUST
NOT be treated as evidence of WHO spoke: the headphones prove the
headphones are paired, not who wears them. RULED by Mike, voice
03:04-03:06 Thu 2026-09-24: *"it would label it with what the input was,
that it was my headphones, the speaker on my Mac, my car speaker, or
coming in from this Delta account ... VoiceMode doesn't tell you that it
came in on the headphones from the M5 Mac"* and *"you don't know for sure
that I'm in them"*. This is VM-1010 (April, todo), measured 03:06: the name
is already in hand from `sounddevice`.

#### Scenario: The label is the OS device name

- GIVEN the Mac's default input is AirPods
- WHEN a partial is written
- THEN its `device` is the name the audio library reports for that input

#### Scenario: A device change is an event

- GIVEN a listen on AirPods
- WHEN the AirPods disconnect and the Mac's microphone becomes the input
- THEN a `device changed` event line is written
- AND later lines carry the new device name
