# faster-whisper Backend & Block-Timeline Measurement — Design

**Status:** Approved design, ready for implementation planning
**Branch:** `feat/explicit-turn-handoff`
**Scope:** Personal customization of the VoiceMode `converse` tool. Not tracked
in the upstream issue tracker; do not link to GitHub issues or open a PR against
upstream.

This design builds on the already-implemented silence-observability work on this
branch (the `⟨pause Ns⟩` / `⟨pre-speech Ns⟩` markers and `Silence:` field). It
adds two things: a **faster-whisper** local STT backend for accurate word
timestamps, and an opt-in **block timeline** that renders a user turn as an
explicit sequence of timed speech blocks and gaps. When the block timeline is
active it **replaces** the marker model for that turn.

---

## Problem

In a VoiceMode voice conversation the assistant wants to *perceive the timing
shape* of a user's turn — not just whether a notable silence occurred, but the
full picture: how long each stretch of speech took, where the silences fell and
how long they lasted, and therefore how much the user is stumbling ("어…",
"그…") or thinking. The existing marker model only flags *significant silences*;
a slow, filled, stumbling block with little content is invisible to it because
nothing was *silent*.

Two needs follow:

1. **Accurate word timestamps.** To render a turn as timed blocks, transcript
   text must be assigned to the block it belongs to. That requires reliable
   word-level timestamps. The current local backend (whisper.cpp) has uncertain
   `verbose_json` / word-timestamp support.
2. **Block-timeline measurement.** Express the whole turn as an ordered sequence
   of timed blocks so the assistant can read the timing shape directly.

---

## Terms

Inlined so this spec is self-contained.

- **Turn** — one party's contiguous span of holding the conversation (user
  speaking, or assistant speaking). Ends when the floor passes.
- **VAD** — WebRTC voice-activity detection running in the record loop, deciding
  per audio frame whether the frame is speech or silence.
- **Word timestamp** — per-word `(start, end)` wall-clock times relative to the
  start of the recording, obtained from STT `verbose_json` with
  `timestamp_granularities=["word"]`.
- **Block timeline** — a user turn expressed as a time-ordered sequence of
  blocks, each carrying its duration in seconds. Two block kinds alternate:
  speech blocks and gaps. Example render:
  `모델은 (0.7s) (gap 5.3s) 음 잘모르겠어요. 그... (6.3s) (gap 10.2s) 그러니까 (1.6s)`.
- **Speech block** — a contiguous run of the user actually speaking, bounded on
  each side by a gap (or the turn start/end). Rendered `text (Ns)` where N is the
  block's duration. Fillers stay inside the block as ordinary text.
- **Gap** — a silence (unfilled pause) *between* speech blocks; the only thing
  that breaks one speech block from the next. Rendered `(gap Ns)`. A pre-speech
  silence before the first speech block is also a gap.
- **Block boundary** — the rule for where one speech block ends and the next
  begins: **only a gap (silence) breaks a block.** A filler never does.
- **Filler** — a filled pause the user voices rather than falling silent ("어",
  "음", "그", "저", "uh", "um"). Because it is voiced, VAD counts it as speech, so
  it lives inside a speech block as plain text. VoiceMode does **not** identify
  or time fillers separately.
- **Block time source** — block and gap durations come from the **VAD** (the
  record loop's frame-level wall-clock), never from STT. VAD is the single source
  of truth for time; word timestamps only assign text to blocks.
- **Deliberation / disfluency** — assistant-side *interpretations* of the timing
  ("how much the user is thinking / stumbling"), **not** system outputs. The
  system reports seconds; the assistant judges.
- **speaches** — an OpenAI-compatible HTTP server built on faster-whisper /
  CTranslate2, supporting `verbose_json` word timestamps natively.

---

## Current behavior (baseline)

- **STT backends.** Local whisper.cpp exposed as an OpenAI-compatible HTTP server
  on port 2022, plus OpenAI cloud. Configured via `VOICEMODE_STT_BASE_URLS`
  (default `http://127.0.0.1:2022/v1,https://api.openai.com/v1`). Discovery and
  failover in `voice_mode/provider_discovery.py` and
  `voice_mode/simple_failover.py`. There is a precedent for a *second* local
  backend: **mlx-audio** (installed via `uv tool install`, run as an
  OpenAI-compatible server on port 8890, detected by `detect_provider_type()`).
- **Word timestamps.** `simple_stt_failover(..., word_timestamps=True)` sends
  `response_format=verbose_json` + `timestamp_granularities=["word"]` to *all*
  endpoints and extracts a `words` list of `{word, start, end}` if present,
  "handling gracefully if words are absent." whisper.cpp support is uncertain.
- **Silence profile.** `record_audio_with_silence_detection()` runs a VAD state
  machine (`WAITING_FOR_SPEECH → SPEECH_ACTIVE → SILENCE_AFTER_SPEECH`) and
  returns `(full_recording, speech_detected, profile)` where `profile` is a
  `SilenceProfile(pre_speech_delay, longest_gap, total_silence, speech_active,
  gaps: List[(start, end)])`. It already tracks per-gap `(start, end)` wall-clock
  times.
- **Marker model (already implemented on this branch).** When a pre-speech delay
  or speech gap is *significant* (≥ `VOICEMODE_SILENCE_SIGNIFICANCE_SEC`, default
  2.0s), an inline marker (`⟨pause Ns⟩` / `⟨pre-speech Ns⟩`) is inserted into the
  transcript via `insert_markers()`, and a `Silence:` field is appended to the
  result **only** on turns with a significant silence. Word-timestamp STT is
  requested only on significant-silence turns (`_needs_word_timestamps()`).
- **converse result assembly.** The result string is
  `Voice response: {text}{stt_info} | Timing: {timing_str}` (plus a `Silence:`
  field when significant).

---

## Axis 1 — faster-whisper backend (accurate word timestamps)

### Decision

Add **faster-whisper** as a local STT backend by running **speaches** (a
faster-whisper / CTranslate2 OpenAI-compatible server) as its own service on a
dedicated port, mirroring the existing **mlx-audio** integration pattern.
speaches supports `response_format=verbose_json` with
`timestamp_granularities=["word"]` natively, giving reliable word timestamps for
block assignment.

### Integration shape

- **Service.** New install tool under `voice_mode/tools/` (mirroring
  `voice_mode/tools/mlx_audio/install.py`): install speaches (e.g. via
  `uv tool install`/pipx or its documented runner), a start script template, and
  launchd (macOS) / systemd (Linux) registration. Runs an OpenAI-compatible HTTP
  server on a dedicated port (e.g. `VOICEMODE_FASTER_WHISPER_PORT`, default
  `2023`).
- **Provider registration.** Add the endpoint (`http://127.0.0.1:2023/v1`) to the
  STT base-URL set. Extend `detect_provider_type()` to recognize the port /
  provider as `"faster-whisper"`. No changes to failover logic — it already
  iterates `STT_BASE_URLS`.
- **Model management.** faster-whisper uses CTranslate2 model artifacts (not
  whisper.cpp `ggml-*.bin`); model download/selection is handled by speaches'
  own model management (do not reuse the whisper.cpp `ggml` registry).
- **No change to whisper.cpp.** The default STT path is untouched for users who
  do not opt into block measurement.

### Rationale (inlined)

VoiceMode's STT layer is already "any OpenAI-compatible endpoint," and mlx-audio
proves a second local backend drops in with no failover changes. A dedicated
speaches service isolates the accurate-timestamp path without destabilizing
whisper.cpp. In-process faster-whisper was rejected (breaks the uniform
endpoint abstraction, duplicates model management); "fix whisper.cpp word
timestamps" was rejected (uncertain feasibility, entangles the default path).

---

## Axis 2 — block-timeline measurement (opt-in)

### Decision

Add an opt-in **block timeline**, enabled by a new `converse` parameter
`measure_blocks` (default off; **no env default** — set per call by the
assistant). When on, the turn is rendered as a time-ordered sequence of speech
blocks and gaps. When on, the block timeline **replaces** the significant-silence
markers and `Silence:` field for that turn. When off, behavior is exactly the
current baseline (marker model unchanged).

### Block construction

1. **Time source is VAD.** Block and gap durations are computed from the record
   loop's per-frame wall-clock — the same source the `SilenceProfile` already
   uses. Durations always sum to the recording length.
2. **Block boundary.** A speech block runs from the end of one gap to the start
   of the next. **Only a gap (silence) breaks a block.** The gap boundaries are
   exactly the VAD-detected silences already tracked as `profile.gaps`
   `(start, end)`, plus the pre-speech silence before the first block.
3. **Fillers are inline.** Fillers ("음", "그...") are voiced, so VAD keeps them
   inside the speech block. They are **not** identified or timed separately. A
   long block with little content is what signals stumbling — the assistant
   infers it.
4. **Text assignment via word timestamps.** On a turn that has at least one gap,
   STT is requested with word timestamps; each word is assigned to the block
   whose `[start, end]` VAD interval contains the word's midpoint (or nearest
   block). The block's rendered text is the concatenation of its assigned words.

### Render format

- Speech block: `text (Ns)` — text then its VAD duration to one decimal place.
- Gap: `(gap Ns)` — including a leading pre-speech gap.
- Example:
  `모델은 (0.7s) (gap 5.3s) 음 잘모르겠어요. 그... (6.3s) (gap 10.2s) 그러니까 (1.6s)`
- The block timeline is the transcript body for that turn (it carries the words),
  so it appears wherever the transcript is shown, including saved transcriptions.

### Word-timestamp scope (optimization)

- `measure_blocks` off → no word timestamps (baseline path).
- `measure_blocks` on **and the turn has ≥1 gap** → request word timestamps
  (needed to split text across blocks).
- `measure_blocks` on **and the turn has no gap** (a single fluent speech block)
  → **skip** word timestamps; there is nothing to split, so the whole transcript
  is one block with its VAD duration. This preserves the "immediate answer stays
  cheap" optimization even with the flag on.
- If word timestamps are unavailable for a provider/turn, fall back to a single
  block containing the whole transcript with the turn's speech duration, plus the
  gap durations rendered without precise text splits (do not fail the turn).

### Rationale (inlined)

The marker model answered "*was there* a notable silence, and where?" The block
timeline answers "what was the whole timing shape?" — which markers cannot,
because a filled/slow block is not a silence. Rendering every block (not only
significant silences) is what makes "long block, few words" legible. The system
stays a pure measurement: it reports seconds; the assistant judges
disfluency/deliberation. Timing comes from VAD (single source of truth) so
durations reconcile; word timestamps only assign text, so a timestamp provider
disagreeing with VAD cannot corrupt the durations.

A separate filler subsystem (dictionary + word-duration threshold,
`⟨filler Ns⟩`) was **rejected**: the target format keeps the filler inline with
no separate number, and block duration already exposes the stumble, so
classifying "그 책" vs "그…" adds risk for no gain. A system-computed
disfluency/deliberation *score* was **rejected**: it crosses from measurement
into policy.

---

## Configuration summary

| Env var | Default | Meaning |
|---|---|---|
| `VOICEMODE_FASTER_WHISPER_PORT` | `2023` | Port for the local speaches (faster-whisper) service. |
| `VOICEMODE_STT_BASE_URLS` | *(existing)* | speaches endpoint added to the set when the service is installed. |
| `VOICEMODE_SILENCE_SIGNIFICANCE_SEC` | `2.0` | *(existing)* Significance threshold; still governs the marker model when `measure_blocks` is off. |

`converse` parameters:

| Param | Default | Meaning |
|---|---|---|
| `measure_blocks` | `false` | When true, render the turn as a block timeline (replaces markers/`Silence:` for that turn). Set per call by the assistant; **no env default**. |

---

## Skill changes

`measure_blocks` changes how `converse` is driven and adds a new output shape the
assistant must read, so the relevant SKILL bodies must teach it:

- **When to set `measure_blocks=true`** — e.g. when the assistant wants detailed
  timing metadata about how the user is speaking (stumbling / thinking) on the
  next turn.
- **How to read a block timeline** — `text (Ns)` is a speech block and its
  duration; `(gap Ns)` is a silence; fillers are inline; a long block with little
  content signals stumbling; a long gap signals thinking. The system reports
  seconds only — the assistant makes the empathy judgment.

**These SKILL edits are governed by `superpowers:writing-skills`** and MUST
follow RED-GREEN-REFACTOR:

- **RED** — a baseline scenario (no skill guidance) showing the assistant fails
  to set `measure_blocks` when detailed timing is wanted, and/or misreads a block
  timeline. Document the verbatim behavior first.
- **GREEN** — minimal SKILL wording addressing those specific failures.
- **REFACTOR** — close loopholes surfaced in testing.

Do **not** hand-edit the SKILL body without a failing baseline first. The
skill's `description` must state only *when to use* (triggering conditions), not
summarize the block-reading workflow.

---

## Out of scope

- Real-time / streaming block measurement mid-turn (blocks are computed at turn
  end).
- Separate identification or timing of fillers (rejected during design).
- A system-computed disfluency or deliberation score (rejected — measurement,
  not policy).
- Changes to the turn-control axis (`silence_release_sec`) — independent, already
  shipped on this branch.
- Replacing whisper.cpp as the default backend — speaches is additive, used for
  the measurement path.
- Persisting block timelines to a separate analytics pipeline (the timeline is
  for the assistant's turn-time response; ordinary transcript logging still
  applies).

---

## Acceptance criteria

1. A local speaches (faster-whisper) service can be installed and run as an
   OpenAI-compatible STT backend on `VOICEMODE_FASTER_WHISPER_PORT` (default
   2023), registered as provider type `"faster-whisper"` and usable via the
   existing failover path.
2. That backend returns word timestamps via `verbose_json` /
   `timestamp_granularities=["word"]`.
3. `measure_blocks=false` (default) reproduces today's behavior exactly,
   including the existing significant-silence marker model.
4. `measure_blocks=true` on a turn with mid-turn silences renders a block
   timeline: alternating `text (Ns)` speech blocks and `(gap Ns)` gaps, with a
   leading `(gap Ns)` for a pre-speech delay, durations to one decimal place.
5. Block and gap durations are computed from VAD and sum to the recording
   length; word timestamps are used only to assign text to blocks.
6. Fillers ("음", "그...") appear inline within a speech block and are not timed
   or annotated separately; no `⟨filler Ns⟩` markers exist.
7. When `measure_blocks=true` produces a timeline, the significant-silence
   markers (`⟨pause⟩` / `⟨pre-speech⟩`) and the `Silence:` field are **not** also
   emitted for that turn (the timeline replaces them).
8. `measure_blocks=true` on a fluent, gapless turn yields a single speech block
   with its duration and requests no word timestamps.
9. The system emits no disfluency/deliberation score — only durations.
10. SKILL edits teaching the assistant to set `measure_blocks` and read the block
    timeline were produced via the `writing-skills` RED-GREEN-REFACTOR cycle
    (baseline documented), with a trigger-only `description`.
