# VoiceMode

Voice interaction for AI assistants over MCP: speech-to-text (STT) and
text-to-speech (TTS) wired into a turn-based conversation loop. This glossary
defines the language of voice turn-taking and silence observability.

## Turn-taking

**Turn**:
One party's contiguous span of holding the conversation — the user speaking, or
the assistant speaking. A turn ends when the floor passes to the other party.
_Avoid_: round, exchange (an exchange is a user turn + assistant turn).

**Floor**:
The right to speak. At any moment exactly one party holds the floor. The user
holds the floor while recording; the assistant holds it while playing TTS.
_Avoid_: mic ownership, control.

**Turn handoff**:
The transition of the floor from the user to the assistant. Can be *implicit*
(silence detected as end-of-turn) or *explicit* (user gives a deliberate signal).

**Explicit turn handoff**:
The user deliberately ending their turn, independent of silence — via
`skip_forward` (a control-channel/media-key signal). The user says "I'm done,
go now" rather than letting silence decide.
_Avoid_: manual advance, force-next.

**Silence release**:
Ending the user's turn because silence has lasted a configured number of
seconds. Governed by `silence_release_sec`. The value `0` means "release on the
normal VAD threshold" (current behavior); a positive `N` means "tolerate silence
up to N seconds, then release"; `-1` means "never release on silence" (the turn
ends only at `listen_duration_max` or on explicit handoff).
_Avoid_: auto-release (use only as an adjective: "auto-release timeout"),
timeout.

**Patient listening**:
The use-case of setting `silence_release_sec` to a large tolerance (canonically
60s) so a hesitating or thinking user is not cut off mid-turn. Not a separate
parameter — a named point on the `silence_release_sec` scale.
_Avoid_: floor hold, push-to-talk, hold.

**Hesitation**:
User silence that is *not* end-of-turn — a pause to think mid-sentence, or a
delay before starting to speak. The problem this design addresses: hesitation
being misread as a turn handoff.
_Avoid_: stall, lag.

## Silence observability

**Silence profile**:
Per-turn metadata describing how the user's silence and speech were distributed
within one recording. Reported to the assistant independently of turn control,
so the assistant can respond empathetically to hesitation.
_Avoid_: silence stats, timing.

**Pre-speech delay**:
The silence between the assistant finishing its turn and the user starting to
speak. A large pre-speech delay signals hesitation or being caught off guard.
_Avoid_: lead-in, ramp.

**Speech gap**:
A silence *between* the user's own words within a single turn — the user started
speaking, paused, then continued. The canonical "spoke, then hesitated" signal.
_Avoid_: mid-turn pause, break.

**Speech-active time**:
The portion of a turn during which the user was actually speaking, with silence
removed. Distinguishes "5s of silence then one word" from "5s then a long
answer."
_Avoid_: talk time, voiced duration.

**Significant silence**:
A pre-speech delay or speech gap whose duration meets the significance threshold
(canonically 2.0s, above the VAD end-of-turn threshold). Only significant
silences are surfaced as markers.
_Avoid_: long pause, notable silence.

**Silence marker**:
An inline annotation inserted into the transcript at the position of a
significant silence, so the assistant sees *where* in the utterance the user
hesitated. Written in angle brackets: `⟨pause 5.1s⟩` for a speech gap,
`⟨pre-speech 3.2s⟩` for a pre-speech delay.
_Avoid_: silence tag, pause token.
