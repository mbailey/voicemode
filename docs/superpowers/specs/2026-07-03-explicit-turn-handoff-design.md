# Explicit Turn Handoff & Silence Observability — Design

**Status:** Approved design, ready for implementation planning
**Branch:** `feat/explicit-turn-handoff`
**Scope:** Personal customization of the VoiceMode `converse` tool. Not tracked
in the upstream issue tracker; do not link to GitHub issues or open a PR against
upstream.

---

## Problem

In a VoiceMode voice conversation, when the user pauses mid-sentence to think or
hesitates before answering, WebRTC VAD reads the silence as end-of-turn and the
assistant takes the floor prematurely. The user is cut off.

Two distinct needs follow from this:

1. **Turn control** — let the user (via the assistant) keep the floor through
   hesitation, without forcing a manual key-press on every turn.
2. **Silence observability** — let the assistant *perceive* how much the user
   hesitated or fell silent, so it can respond empathetically ("you seem to be
   mulling this over — where are you stuck?"). This is wanted in *all*
   conversations, not only when turn control is active.

These are two independent axes and are specified separately below.

---

## Terms

Inlined so this spec is self-contained.

- **Turn** — one party's contiguous span of holding the conversation (user
  speaking, or assistant speaking). Ends when the floor passes.
- **Floor** — the right to speak; exactly one party holds it at a time.
- **Explicit turn handoff** — the user deliberately ending their turn,
  independent of silence, via the existing `skip_forward` control-channel /
  media-key signal ("I'm done, go now").
- **Silence release** — ending the user's turn because silence has lasted a
  configured number of seconds (the `silence_release_sec` scalar below).
- **Patient listening** — the use-case of a large silence tolerance (canonically
  60s) so a thinking user is not cut off. A named point on the
  `silence_release_sec` scale, not a separate parameter.
- **Hesitation** — user silence that is *not* end-of-turn (a mid-sentence think,
  or a delay before starting). The thing this design must stop misreading.
- **Silence profile** — per-turn metadata: pre-speech delay, longest speech gap,
  total silence, speech-active time.
- **Pre-speech delay** — silence between the assistant finishing and the user
  starting to speak.
- **Speech gap** — silence *between* the user's own words within one turn.
- **Speech-active time** — the portion of a turn the user was actually speaking
  (silence removed).
- **Significant silence** — a pre-speech delay or speech gap meeting the
  significance threshold (2.0s).
- **Silence marker** — an inline transcript annotation at the position of a
  significant silence: `⟨pause 5.1s⟩` (speech gap) or `⟨pre-speech 3.2s⟩`
  (pre-speech delay).

---

## Current behavior (baseline)

- `voice_mode/tools/converse.py::record_audio_with_silence_detection()` runs a
  VAD state machine (`WAITING_FOR_SPEECH` → `SPEECH_ACTIVE` →
  `SILENCE_AFTER_SPEECH`). It accumulates `silence_duration_ms` and stops when
  `recording_duration >= effective_min_duration and silence_duration_ms >=
  SILENCE_THRESHOLD_MS`.
- The function returns only `(full_recording, speech_detected)`. All silence
  timing is discarded.
- Config defaults (`voice_mode/config.py`): `SILENCE_THRESHOLD_MS=1000`,
  `MIN_RECORDING_DURATION=0.5`, `VAD_AGGRESSIVENESS=3`,
  `DEFAULT_LISTEN_DURATION=120.0`, `INITIAL_SILENCE_GRACE_PERIOD=1.0`.
- `converse()` params today include `listen_duration_max` (default 120s),
  `listen_duration_min` (2.0), `disable_silence_detection` (bool),
  `vad_aggressiveness`.
- `disable_silence_detection=true` disables VAD ending entirely: the turn ends
  only at `listen_duration_max` or on `skip_forward`. This makes it impractical
  to leave on (mic stays open to the max on every quick answer).
- `skip_forward` (VM-1754) already provides explicit handoff: ends the record
  turn immediately, transcribes what was captured.
- STT: main path (`speech_to_text` → `simple_stt_failover`) returns text only.
  A word/segment-timestamp capable path already exists under
  `voice_mode/tools/transcription/` (`verbose_json`, `timestamp_granularities`).
- The final result string is assembled at ~`converse.py:2958-2982`:
  `Voice response: {text}{stt_info} | Timing: {timing_str}` (summary), a verbose
  variant, and `No speech detected` when empty.

---

## Axis 1 — Turn control: the `silence_release_sec` scalar

### Decision

Collapse silence-based turn-ending into a single continuous scalar,
`silence_release_sec`, replacing the two-boolean approach. The feature is
inherently one question — "how many seconds of silence do we tolerate?" —
so a scalar removes the artificial overlap between `disable_silence_detection`
and any `patient_listening` boolean, and removes any need for combination rules.

### Value semantics

| Value | Behavior |
|---|---|
| `0` (default / unset) | End on the normal VAD threshold — **current behavior, unchanged**. |
| `N` > 0 | Tolerate silence up to N seconds within/before the turn, then release (silence release). Canonical patient-listening value: `60`. |
| `-1` | Never release on silence. Turn ends only at `listen_duration_max` or on explicit `skip_forward`. |

- `silence_release_sec` applies to **both** pre-speech delay and mid-turn speech
  gaps: the turn is not ended by silence until the running silence run reaches
  the tolerance.
- **Backward compatibility:** `disable_silence_detection=true` is retained as an
  alias for `silence_release_sec = -1`. If both are supplied, `-1` semantics
  apply. It is documented as deprecated in favor of `silence_release_sec`.

### `listen_duration_max` changes

- Default raised from **120 → 180 seconds** (applies to all turns, regardless of
  `silence_release_sec`).
- Remains adjustable per `converse` call by the assistant.
- **Hard clamp: 300 seconds (5 minutes).** Any requested value (including
  per-call) above 300 is clamped to 300. This bounds the maximum mic-open time
  even when `silence_release_sec = -1`.

### What ends a turn (summary)

A user turn ends on the **first** of:

1. Silence run reaching `silence_release_sec` (when `> 0`).
2. Explicit `skip_forward` signal (always available).
3. `listen_duration_max` reached (default 180s, clamped ≤ 300s).

When `silence_release_sec = 0`, condition 1 is the existing VAD threshold. When
`-1`, condition 1 never fires.

### Assistant-facing trigger

The assistant sets `silence_release_sec` per call. When the user says, in any
phrasing, that they need more time / not to be cut off ("끊지 마", "생각 중이야",
"끝까지 들어", "give me a sec", "let me think"), the assistant sets
`silence_release_sec=60` on subsequent `converse` calls. This is a **skill
behavior change** (see "Skill changes" below) and must be authored under
`superpowers:writing-skills` discipline, not hand-edited into the SKILL body.

A config default (`VOICEMODE_SILENCE_RELEASE_SEC`, default `0`) lets a user who
always wants patient listening set it globally.

---

## Axis 2 — Silence observability (independent, always on)

### Decision

Compute the **silence profile** on every turn, independent of
`silence_release_sec`. Surface it to the assistant so it can react to
hesitation, and align significant silences to the transcript with inline
markers.

### Metrics (per turn)

Extracted from the record state machine, which already tracks the needed timing:

1. **Pre-speech delay** — seconds of silence from record start until first
   detected speech (the `WAITING_FOR_SPEECH` span).
2. **Longest speech gap** — the longest single silence run *after* speech began
   and before the turn ended.
3. **Total silence** — sum of all silence within the recording.
4. **Speech-active time** — recording duration minus total silence.

`record_audio_with_silence_detection()` must return these alongside the audio
(replacing the bare `(audio, speech_detected)` tuple with a structure carrying
the profile).

### Significance threshold

- A pre-speech delay or speech gap is **significant** when its duration ≥ **2.0
  seconds** (above the 1.0s VAD end threshold, so ordinary speech rhythm pauses
  are not flagged).
- Configurable via `VOICEMODE_SILENCE_SIGNIFICANCE_SEC` (default `2.0`).

### Transcript markers

- For each significant silence, insert an inline marker into the transcript at
  its aligned position:
  - Speech gap → `⟨pause 5.1s⟩` between the words that bracket it.
  - Pre-speech delay → `⟨pre-speech 3.2s⟩` at the start of the transcript.
- Marker format is angle-bracket + English unit (matches the codebase's
  English log/marker convention; angle brackets don't occur in normal speech).
- Duration shown to one decimal place.

### Marker alignment via conditional word timestamps

- Alignment needs word timestamps. Because the VAD pass finishes **before** STT,
  the code already knows whether the turn contained a significant gap.
- **Only on turns with a significant silence** does STT run with
  `word_timestamps=True` (using the existing `voice_mode/tools/transcription/`
  path), then each gap's wall-clock interval (relative to record start) is
  matched to the word boundary it falls between, and the marker inserted.
- Turns with no significant silence use the existing STT path unchanged (no
  `verbose_json` overhead).
- If word timestamps are unavailable for a provider/turn, fall back to appending
  a position-less note (see result formatting) rather than failing.

### Result formatting

- The silence profile is attached to the `converse` result string **only when a
  significant silence occurred** (immediate-answer turns stay clean).
- When attached, the summary form becomes:
  `Voice response: {transcript-with-markers}{stt_info} | Silence: pre {p}s, gap {g}s, speech {s}s | Timing: {timing_str}`
  - Omit the `pre`/`gap` sub-fields that were not significant.
- Verbose metrics level always shows the full profile (all four metrics), even
  when not significant, for debugging.
- The inline markers live inside the transcript text itself, so they are present
  wherever the transcript is shown (including saved transcriptions).

---

## Configuration summary

| Env var | Default | Meaning |
|---|---|---|
| `VOICEMODE_SILENCE_RELEASE_SEC` | `0` | Default `silence_release_sec` (0 = current VAD, N = tolerate Ns, -1 = never). |
| `VOICEMODE_DEFAULT_LISTEN_DURATION` | `180.0` | Raised from 120; per-call override allowed, clamped ≤ 300. |
| `VOICEMODE_SILENCE_SIGNIFICANCE_SEC` | `2.0` | Threshold for a significant silence / marker. |
| `VOICEMODE_MAX_LISTEN_DURATION` (hard clamp) | `300.0` | Absolute upper bound on any `listen_duration_max`. |

`converse` parameters:

| Param | Default | Meaning |
|---|---|---|
| `silence_release_sec` | from env (`0`) | Turn-control scalar (see value table). |
| `listen_duration_max` | from env (`180`) | Per-call max, clamped ≤ 300. |
| `disable_silence_detection` | `false` | **Deprecated** alias for `silence_release_sec=-1`. |

---

## Skill changes

The assistant-facing trigger (Axis 1) changes how `converse` is driven, so the
relevant SKILL bodies must teach it:

- `.claude/skills/converse/SKILL.md` (and/or `skills/voicemode/SKILL.md`) gains
  guidance: *when the user asks for more time / not to be cut off, set
  `silence_release_sec=60` on the next `converse` call*; and *the converse result
  may include `⟨pause Ns⟩` / `⟨pre-speech Ns⟩` markers and a `Silence:` field —
  read them as hesitation signals and respond empathetically.*

**These SKILL edits are governed by `superpowers:writing-skills`** — RED (baseline
scenario showing the assistant fails to react to hesitation / fails to set the
scalar), GREEN (minimal SKILL wording), REFACTOR (close loopholes). Do **not**
hand-edit the SKILL body without a failing baseline first.

---

## Out of scope

- Real-time barge-in / interrupting TTS when the user starts speaking
  (separate concern; existing `skip_forward` handles playback interruption).
- Streaming STT / mid-utterance intervention.
- Precise silence event-logging with timestamps for analytics (the profile is
  for empathetic response, not a metrics pipeline).
- Keyword-based turn ending (rejected during design).
- Runtime toggles (control-channel/media-key) for `silence_release_sec` — the
  scalar is set per-call by the assistant and via env default only.

---

## Acceptance criteria

1. `silence_release_sec=0` (default) reproduces today's VAD turn-ending exactly.
2. `silence_release_sec=60` keeps the turn open through a 30s mid-sentence pause,
   then releases after 60s of continuous silence.
3. `silence_release_sec=-1` (and `disable_silence_detection=true`) never end on
   silence; end only at `listen_duration_max` or `skip_forward`.
4. `listen_duration_max` default is 180s; any value > 300 is clamped to 300.
5. Every turn computes the four silence-profile metrics.
6. A turn with a ≥2.0s mid-speech pause yields a transcript containing
   `⟨pause Ns⟩` between the correct words, and a `Silence:` field in the summary
   result.
7. A turn with an immediate, fluent answer yields no markers and no `Silence:`
   field (clean result).
8. Word-timestamp STT is requested only on turns with a significant silence.
9. Verbose metrics level shows the full profile even when not significant.
10. SKILL edits for the assistant trigger were produced via the
    `writing-skills` RED-GREEN-REFACTOR cycle (baseline documented).
