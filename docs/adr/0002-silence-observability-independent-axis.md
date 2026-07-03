# Silence observability is an axis independent of turn control

**Context:** Personal customization on branch `feat/explicit-turn-handoff` (not
tracked in the upstream issue tracker). Beyond keeping users from being cut off, the assistant must be able to *perceive* how much a user
hesitated or fell silent while answering — not to decide turn handoff, but to
respond empathetically ("you seem to be mulling this over — where are you
stuck?"). The recording loop already computes silence durations internally but
discards them, returning only `speech_detected` (bool).

**Decision:** Treat the **silence profile** (pre-speech delay, longest speech
gap, total silence, speech-active time) as a first-class output computed on
*every* turn, independent of `silence_release_sec`. When a pre-speech delay or
speech gap exceeds the significance threshold (2.0s), insert an inline
**silence marker** (`⟨pause 5.1s⟩` / `⟨pre-speech 3.2s⟩`) into the transcript at
its aligned position, and attach the profile to the converse result string only
when a significant silence occurred. Marker alignment uses word-timestamp STT,
requested only on turns that actually contain a significant gap.

**Why:** Turn control (a *policy* for ending the turn) and silence observability
(a *measurement* of what happened) are separate concerns; coupling them would
make hesitation invisible in ordinary (non-patient) conversations, defeating the
empathy goal. The recording loop already tracks the needed silence durations, so
exposing them is nearly free; word timestamps are the only added cost and are
gated to significant-gap turns to keep the common case (immediate answers) on the
existing STT path.

**Considered alternatives:** (a) Expose silence only when patient listening is on
— rejected: empathy is wanted in normal conversation too. (b) Always request
word-timestamp STT — rejected: needless `verbose_json` overhead on immediate
answers. (c) Position-less gap numbers ("longest gap 5.1s") — rejected: the user
needs to know *which* words the hesitation fell between, which requires transcript
alignment.
