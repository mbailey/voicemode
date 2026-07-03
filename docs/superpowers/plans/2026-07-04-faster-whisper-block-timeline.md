# faster-whisper Backend & Block-Timeline Measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `measure_blocks` mode to `converse` that renders a user turn as a VAD-timed sequence of speech blocks and gaps, backed by a local faster-whisper (speaches) STT service for accurate word timestamps.

**Architecture:** Block/gap durations come from the existing VAD record loop (single source of truth); word timestamps only assign transcript words to blocks. A new `block_timeline` module builds the render string from the `SilenceProfile` (extended with block boundaries) plus words. When `measure_blocks=true`, the timeline replaces the existing significant-silence markers/`Silence:` field for that turn. faster-whisper is added as a separate OpenAI-compatible STT backend mirroring the mlx-audio integration.

**Tech Stack:** Python 3.10+, pytest, WebRTC VAD, FastMCP, speaches (faster-whisper/CTranslate2) as an OpenAI-compatible HTTP server.

## Global Constraints

- Package manager is `uv`; run tests with `uv run pytest tests/ -v --tb=short`.
- Follow Keep-a-Changelog: user-facing changes go in `CHANGELOG.md` `## [Unreleased]`.
- Never edit `voice_mode/__version__.py` by hand.
- Marker/log convention is English in angle brackets; block render uses ASCII `(gap Ns)` / `text (Ns)`, durations to one decimal place (`f"{s:.1f}s"`).
- `measure_blocks` is a per-call `converse` parameter only — **no env default**.
- Time source for all block/gap durations is VAD, never STT. Durations must sum to the recording length.
- Fillers ("음","그...") are never identified or timed separately; no `⟨filler⟩` markers.
- The system emits durations only — no disfluency/deliberation score.

---

### Task 1: Extend SilenceProfile with block boundaries

**Files:**
- Modify: `voice_mode/tools/silence_profile.py`
- Test: `tests/test_silence_profile_blocks.py`

**Interfaces:**
- Consumes: existing `SilenceProfile(pre_speech_delay, longest_gap, total_silence, speech_active, gaps: List[(start,end)])`.
- Produces: `SilenceProfile.first_speech_start: float` (new field, default `0.0`), `SilenceProfile.recording_end: float` (new field, default `0.0`), and method `SilenceProfile.blocks() -> List[Tuple[str, float, float]]` returning ordered `(kind, start, end)` where `kind` is `"speech"` or `"gap"`. A leading gap is emitted when `first_speech_start > 0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_silence_profile_blocks.py
from voice_mode.tools.silence_profile import SilenceProfile


def test_blocks_alternate_speech_and_gap():
    # pre-speech 0.7s, speech to 6.0, gap 6.0-11.3, speech to 12.9
    p = SilenceProfile(
        pre_speech_delay=0.7, longest_gap=5.3, total_silence=6.0,
        speech_active=6.9, gaps=[(6.0, 11.3)],
        first_speech_start=0.7, recording_end=12.9,
    )
    assert p.blocks() == [
        ("gap", 0.0, 0.7),
        ("speech", 0.7, 6.0),
        ("gap", 6.0, 11.3),
        ("speech", 11.3, 12.9),
    ]


def test_blocks_no_pre_speech_no_gap_single_block():
    p = SilenceProfile(
        pre_speech_delay=0.0, longest_gap=0.0, total_silence=0.0,
        speech_active=3.0, gaps=[], first_speech_start=0.0, recording_end=3.0,
    )
    assert p.blocks() == [("speech", 0.0, 3.0)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_silence_profile_blocks.py -v`
Expected: FAIL — `TypeError` (unexpected `first_speech_start`) or `AttributeError: blocks`.

- [ ] **Step 3: Write minimal implementation**

```python
# voice_mode/tools/silence_profile.py — add two fields and a method
@dataclass
class SilenceProfile:
    pre_speech_delay: float
    longest_gap: float
    total_silence: float
    speech_active: float
    gaps: List[Tuple[float, float]] = field(default_factory=list)
    first_speech_start: float = 0.0
    recording_end: float = 0.0

    @classmethod
    def empty(cls) -> "SilenceProfile":
        return cls(0.0, 0.0, 0.0, 0.0, [], 0.0, 0.0)

    # ... keep existing significant_gaps / pre_speech_significant ...

    def blocks(self) -> List[Tuple[str, float, float]]:
        """Ordered (kind, start, end) blocks; only gaps break speech blocks."""
        out: List[Tuple[str, float, float]] = []
        cursor = 0.0
        if self.first_speech_start > 1e-9:
            out.append(("gap", 0.0, self.first_speech_start))
            cursor = self.first_speech_start
        for (gs, ge) in self.gaps:
            if gs > cursor + 1e-9:
                out.append(("speech", cursor, gs))
            out.append(("gap", gs, ge))
            cursor = ge
        if self.recording_end > cursor + 1e-9:
            out.append(("speech", cursor, self.recording_end))
        return out
```

Note: update `empty()` to pass the two new positional args as shown.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_silence_profile_blocks.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/silence_profile.py tests/test_silence_profile_blocks.py
git commit -m "feat: SilenceProfile block boundaries (first_speech_start, recording_end, blocks())"
```

---

### Task 2: Populate block boundaries in the record loop

**Files:**
- Modify: `voice_mode/tools/converse.py:1339-1343` (trackers), `:1470-1472` (first speech), `:1518-1530` (profile build)
- Test: `tests/test_record_loop_profile_blocks.py`

**Interfaces:**
- Consumes: `SilenceProfile` with `first_speech_start` / `recording_end` from Task 1.
- Produces: `record_audio_with_silence_detection(...)` returns a profile whose `first_speech_start` equals the recording time when speech was first detected, and `recording_end` equals total `recording_duration`.

- [ ] **Step 1: Write the failing test** (drives the pure profile-assembly logic by extracting it into a helper)

```python
# tests/test_record_loop_profile_blocks.py
from voice_mode.tools.converse import _build_silence_profile


def test_build_profile_sets_boundaries():
    prof = _build_silence_profile(
        pre_speech_delay_s=0.7, total_silence_s=6.0, speech_active_s=6.9,
        gaps=[(6.0, 11.3)], first_speech_start=0.7, recording_end=12.9,
    )
    assert prof.first_speech_start == 0.7
    assert prof.recording_end == 12.9
    assert prof.blocks()[0] == ("gap", 0.0, 0.7)
    assert prof.longest_gap == 5.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_record_loop_profile_blocks.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_silence_profile'`.

- [ ] **Step 3: Write minimal implementation**

Add a module-level helper in `converse.py` (near `_needs_word_timestamps`, ~line 1272) and call it from the record loop:

```python
def _build_silence_profile(pre_speech_delay_s, total_silence_s, speech_active_s,
                           gaps, first_speech_start, recording_end):
    longest_gap = max((e - s for (s, e) in gaps), default=0.0)
    return SilenceProfile(
        pre_speech_delay=pre_speech_delay_s,
        longest_gap=longest_gap,
        total_silence=total_silence_s,
        speech_active=speech_active_s,
        gaps=gaps,
        first_speech_start=first_speech_start,
        recording_end=recording_end,
    )
```

In the record loop, add a tracker beside the others at `:1339-1343`:

```python
        first_speech_start = None    # recording_duration when speech first detected
```

At the first-speech transition (`:1470`, inside `if is_speech:` under `if not speech_detected:`), capture it:

```python
                                speech_detected = True
                                first_speech_start = recording_duration
                                silence_duration_ms = 0
                                speech_active_s += chunk_duration_s
```

Replace the inline profile construction at `:1521-1530` with:

```python
                if current_gap_start is not None:
                    gaps.append((current_gap_start, recording_duration))
                profile = _build_silence_profile(
                    pre_speech_delay_s=pre_speech_delay_s,
                    total_silence_s=total_silence_s,
                    speech_active_s=speech_active_s,
                    gaps=gaps,
                    first_speech_start=(first_speech_start or 0.0),
                    recording_end=recording_duration,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_record_loop_profile_blocks.py tests/test_silence_profile_blocks.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_record_loop_profile_blocks.py
git commit -m "feat: record loop populates block boundaries (first_speech_start, recording_end)"
```

---

### Task 3: Block-timeline render module

**Files:**
- Create: `voice_mode/tools/block_timeline.py`
- Test: `tests/test_block_timeline.py`

**Interfaces:**
- Consumes: `SilenceProfile.blocks()` from Task 1; a `words: Optional[List[Dict]]` list of `{word, start, end}` (STT word timestamps, seconds relative to record start).
- Produces: `render_block_timeline(profile: SilenceProfile, words: Optional[List[Dict]], full_text: str) -> str`. Assigns each word to the speech block whose `[start, end]` contains the word's midpoint; renders `text (Ns)` per speech block and `(gap Ns)` per gap, joined by single spaces. With no words (or a single gapless speech block), the whole `full_text` is one block: `full_text (Ns)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_block_timeline.py
from voice_mode.tools.silence_profile import SilenceProfile
from voice_mode.tools.block_timeline import render_block_timeline


def _profile():
    return SilenceProfile(
        pre_speech_delay=0.7, longest_gap=5.3, total_silence=6.0,
        speech_active=6.9, gaps=[(6.0, 11.3)],
        first_speech_start=0.7, recording_end=12.9,
    )


def test_render_assigns_words_to_blocks():
    words = [
        {"word": "모델은", "start": 0.9, "end": 5.9},
        {"word": "그러니까", "start": 11.4, "end": 12.7},
    ]
    out = render_block_timeline(_profile(), words, "모델은 그러니까")
    assert out == "(gap 0.7s) 모델은 (5.3s) (gap 5.3s) 그러니까 (1.6s)"


def test_render_gapless_single_block_uses_full_text():
    p = SilenceProfile(0.0, 0.0, 0.0, 3.0, [], 0.0, 3.0)
    assert render_block_timeline(p, None, "네 그렇게 해주세요") == "네 그렇게 해주세요 (3.0s)"


def test_render_without_words_falls_back_to_gap_shape():
    # gap present but no word timestamps: whole text in first speech block.
    out = render_block_timeline(_profile(), None, "모델은 그러니까")
    assert out == "(gap 0.7s) 모델은 그러니까 (5.3s) (gap 5.3s)  (1.6s)".replace("  ", " ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_block_timeline.py -v`
Expected: FAIL — `ModuleNotFoundError: voice_mode.tools.block_timeline`.

- [ ] **Step 3: Write minimal implementation**

```python
# voice_mode/tools/block_timeline.py
"""Render a user turn as a VAD-timed sequence of speech blocks and gaps.

Durations come from the VAD SilenceProfile (single source of truth). Word
timestamps only assign transcript text to the block it belongs to. Pure
functions -- no I/O."""
from __future__ import annotations

from typing import List, Dict, Optional

from voice_mode.tools.silence_profile import SilenceProfile


def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s"


def _assign_words(blocks, words):
    """Return {speech_block_index: 'joined words'} by word midpoint."""
    speech_idx = [i for i, (k, _, _) in enumerate(blocks) if k == "speech"]
    text_by_block: Dict[int, List[str]] = {i: [] for i in speech_idx}
    for w in words:
        mid = (float(w["start"]) + float(w["end"])) / 2.0
        target = None
        for i in speech_idx:
            _, s, e = blocks[i]
            if s - 1e-6 <= mid <= e + 1e-6:
                target = i
                break
        if target is None and speech_idx:
            # nearest speech block by distance to its interval
            target = min(speech_idx, key=lambda i: min(abs(mid - blocks[i][1]), abs(mid - blocks[i][2])))
        if target is not None:
            text_by_block[target].append(w["word"])
    return {i: " ".join(ws) for i, ws in text_by_block.items()}


def render_block_timeline(profile: SilenceProfile, words: Optional[List[Dict]],
                          full_text: str) -> str:
    blocks = profile.blocks()
    speech_blocks = [i for i, (k, _, _) in enumerate(blocks) if k == "speech"]

    # Single speech block (gapless) OR no word timestamps: whole text in the
    # first speech block; other speech blocks (if any) render empty text.
    if words and len(speech_blocks) > 1:
        text_by_block = _assign_words(blocks, words)
    else:
        text_by_block = {}
        if speech_blocks:
            text_by_block[speech_blocks[0]] = full_text

    pieces: List[str] = []
    for i, (kind, s, e) in enumerate(blocks):
        dur = _fmt(e - s)
        if kind == "gap":
            pieces.append(f"(gap {dur})")
        else:
            txt = text_by_block.get(i, "")
            pieces.append(f"{txt} ({dur})".strip() if txt else f"({dur})")
    return " ".join(pieces)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_block_timeline.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/block_timeline.py tests/test_block_timeline.py
git commit -m "feat: block_timeline render module (VAD durations + word assignment)"
```

---

### Task 4: Add `measure_blocks` converse param + wire word-timestamp gating

**Files:**
- Modify: `voice_mode/tools/converse.py` — signature (~`:1786-1790`), word-timestamp decision (`:2705`), result assembly call (`:3052-3054`)
- Test: `tests/test_measure_blocks_gating.py`

**Interfaces:**
- Consumes: `_needs_word_timestamps` (existing), `render_block_timeline` (Task 3), `_assemble_voice_result` (Task 5 extends it).
- Produces: `converse(..., measure_blocks: Union[bool, str] = False, ...)`. New helper `_want_words_for_turn(profile, measure_blocks: bool, threshold: float) -> bool` = when `measure_blocks` is on, request words iff the turn has ≥1 gap (`profile.gaps` non-empty) OR a pre-speech gap; when off, fall back to existing `_needs_word_timestamps`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_measure_blocks_gating.py
from voice_mode.tools.converse import _want_words_for_turn
from voice_mode.tools.silence_profile import SilenceProfile


def _gapless():
    return SilenceProfile(0.0, 0.0, 0.0, 3.0, [], 0.0, 3.0)


def _withgap():
    return SilenceProfile(0.7, 5.3, 6.0, 6.9, [(6.0, 11.3)], 0.7, 12.9)


def test_measure_blocks_off_uses_significance():
    # off + no significant gap -> no words
    assert _want_words_for_turn(_gapless(), measure_blocks=False, threshold=2.0) is False


def test_measure_blocks_on_gapless_skips_words():
    assert _want_words_for_turn(_gapless(), measure_blocks=True, threshold=2.0) is False


def test_measure_blocks_on_with_gap_requests_words():
    assert _want_words_for_turn(_withgap(), measure_blocks=True, threshold=2.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_measure_blocks_gating.py -v`
Expected: FAIL — `ImportError: cannot import name '_want_words_for_turn'`.

- [ ] **Step 3: Write minimal implementation**

Add helper near `_needs_word_timestamps` (`:1272`):

```python
def _want_words_for_turn(profile, measure_blocks: bool, threshold: float) -> bool:
    """When measure_blocks is on, words are needed to split text across blocks --
    but only if there is at least one gap (pre-speech or speech-internal).
    When off, defer to the significance-based marker path."""
    if profile is None:
        return False
    if measure_blocks:
        return bool(profile.gaps) or profile.first_speech_start > 1e-9
    return _needs_word_timestamps(profile, threshold)
```

Add the parameter to the `converse` signature (after `silence_release_sec`, `:1787`):

```python
    measure_blocks: Union[bool, str] = False,
```

Coerce string/env-style truthiness using the **inline pattern this file already uses** for `disable_silence_detection` at `:1947-1948` (there is no `_coerce_bool` helper). Add this beside those coercions (~`:1948`):

```python
    if isinstance(measure_blocks, str):
        measure_blocks = measure_blocks.lower() in ('true', '1', 'yes', 'on')
    effective_measure_blocks = bool(measure_blocks)
```

Replace the word decision at `:2705`:

```python
                    want_words = _want_words_for_turn(silence_prof, effective_measure_blocks, SIGNIFICANCE_THRESHOLD_SEC)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_measure_blocks_gating.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_measure_blocks_gating.py
git commit -m "feat: measure_blocks converse param + word-timestamp gating"
```

---

### Task 5: Timeline replaces markers in result assembly

**Files:**
- Modify: `voice_mode/tools/converse.py:1749-1768` (`_assemble_voice_result`), call site `:3052-3054`
- Test: `tests/test_assemble_measure_blocks.py`

**Interfaces:**
- Consumes: `render_block_timeline` (Task 3), `effective_measure_blocks` (Task 4).
- Produces: `_assemble_voice_result(response_text, stt_info, timing_str, metrics_level, profile, words, threshold, measure_blocks: bool = False)`. When `measure_blocks` is true and `profile` is not None, the transcript body is the block timeline and **no** `⟨pause⟩`/`⟨pre-speech⟩` markers and **no** `Silence:` field are emitted (summary form). Verbose still appends the full numeric profile line.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assemble_measure_blocks.py
from voice_mode.tools.converse import _assemble_voice_result
from voice_mode.tools.silence_profile import SilenceProfile


def _withgap():
    return SilenceProfile(0.7, 5.3, 6.0, 6.9, [(6.0, 11.3)], 0.7, 12.9)


def test_measure_blocks_summary_uses_timeline_and_drops_silence_field():
    words = [
        {"word": "모델은", "start": 0.9, "end": 5.9},
        {"word": "그러니까", "start": 11.4, "end": 12.7},
    ]
    out = _assemble_voice_result(
        "모델은 그러니까", "", "1.2s", "summary", _withgap(), words, 2.0,
        measure_blocks=True,
    )
    assert "(gap 0.7s) 모델은 (5.3s) (gap 5.3s) 그러니까 (1.6s)" in out
    assert "Silence:" not in out
    assert "⟨" not in out
    assert out.endswith("Timing: 1.2s")


def test_measure_blocks_off_unchanged_marker_path():
    words = [{"word": "네", "start": 0.1, "end": 0.4}]
    out = _assemble_voice_result(
        "네", "", "0.5s", "summary", SilenceProfile(0.0, 0.0, 0.0, 0.4, [], 0.0, 0.4),
        words, 2.0, measure_blocks=False,
    )
    assert out == "Voice response: 네 | Timing: 0.5s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_assemble_measure_blocks.py -v`
Expected: FAIL — `TypeError: _assemble_voice_result() got an unexpected keyword argument 'measure_blocks'`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `_assemble_voice_result` (`:1749`):

```python
def _assemble_voice_result(response_text, stt_info, timing_str, metrics_level, profile, words, threshold, measure_blocks: bool = False):
    """Assemble the result string for a voice turn.

    measure_blocks on: transcript body is the VAD block timeline; the
    significant-silence markers and Silence: field are suppressed (the timeline
    replaces them). measure_blocks off: existing marker/Silence path."""
    from voice_mode.tools.silence_markers import insert_markers, format_silence_field
    if measure_blocks and profile is not None:
        from voice_mode.tools.block_timeline import render_block_timeline
        text = render_block_timeline(profile, words, response_text)
        silence_field = None
    else:
        text = insert_markers(response_text, words, profile, threshold) if profile is not None else response_text
        silence_field = format_silence_field(profile, threshold) if profile is not None else None

    if metrics_level == "minimal":
        return f"Voice response: {text}"
    if metrics_level == "verbose":
        parts = [f"Voice response: {text}{stt_info}"]
        if profile is not None:
            parts.append(f"Silence: pre {profile.pre_speech_delay:.1f}s, gap {profile.longest_gap:.1f}s, "
                         f"total {profile.total_silence:.1f}s, speech {profile.speech_active:.1f}s")
        parts.append(f"Timing: {timing_str}")
        return " | ".join(parts)
    seg = f"Voice response: {text}{stt_info}"
    if silence_field:
        seg += f" | Silence: {silence_field}"
    seg += f" | Timing: {timing_str}"
    return seg
```

Update the call site (`:3052-3054`) to pass the flag:

```python
                    result = _assemble_voice_result(
                        response_text, stt_info, timing_str, effective_metrics_level,
                        silence_prof, stt_words, SIGNIFICANCE_THRESHOLD_SEC,
                        measure_blocks=effective_measure_blocks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_assemble_measure_blocks.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_assemble_measure_blocks.py
git commit -m "feat: block timeline replaces markers when measure_blocks is on"
```

---

### Task 6: faster-whisper (speaches) STT service — install tool

**Files:**
- Create: `voice_mode/tools/faster_whisper/__init__.py`
- Create: `voice_mode/tools/faster_whisper/install.py`
- Create: `voice_mode/templates/scripts/start-faster-whisper-server.sh`
- Modify: `voice_mode/config.py` (add `FASTER_WHISPER_PORT`, append endpoint helper)
- Modify: `voice_mode/provider_discovery.py:28-52` (`detect_provider_type`)
- Test: `tests/test_faster_whisper_provider.py`

**Interfaces:**
- Consumes: existing mlx-audio install pattern (`voice_mode/tools/mlx_audio/install.py`) as the template.
- Produces: config `FASTER_WHISPER_PORT` (default `2023`); `detect_provider_type("http://127.0.0.1:2023/v1")` returns `"faster-whisper"`; an MCP install tool `faster_whisper_install()` that installs speaches, writes the start script, and registers a launchd/systemd service exposing `/v1/audio/transcriptions` on the port.

- [ ] **Step 1: Write the failing test** (provider detection is the testable seam; installation is environment-side)

```python
# tests/test_faster_whisper_provider.py
from voice_mode.provider_discovery import detect_provider_type


def test_detect_faster_whisper_by_port():
    assert detect_provider_type("http://127.0.0.1:2023/v1") == "faster-whisper"


def test_detect_whisper_cpp_still_2022():
    assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_faster_whisper_provider.py -v`
Expected: FAIL — first assertion returns `"local"` (falls through to localhost), not `"faster-whisper"`.

- [ ] **Step 3: Write minimal implementation**

Add to `config.py` beside `WHISPER_PORT` (~`:793`):

```python
FASTER_WHISPER_PORT = int(os.getenv("VOICEMODE_FASTER_WHISPER_PORT", "2023"))
```

In `provider_discovery.py` `detect_provider_type()` (`:28-52`), add a branch **before** the generic localhost fallback:

```python
    elif ":2023" in base_url:
        return "faster-whisper"
```

Create `voice_mode/tools/faster_whisper/__init__.py` (empty) and `install.py` modeled on `voice_mode/tools/mlx_audio/install.py`: an `@mcp.tool()`-decorated async `faster_whisper_install()` that (a) `uv tool install`s speaches (pin a version range, per the speaches docs), (b) renders `start-faster-whisper-server.sh` from the template into `~/.voicemode/services/faster-whisper/bin/`, (c) registers a launchd plist (macOS) / systemd unit (Linux) named `com.voicemode.faster-whisper` / `voicemode-faster-whisper`, and (d) appends `http://127.0.0.1:{FASTER_WHISPER_PORT}/v1` to `VOICEMODE_STT_BASE_URLS` in `~/.voicemode/voicemode.env` if not present. Copy the structure, logging, and error handling of the mlx_audio tool verbatim, substituting names/port.

Create `voice_mode/templates/scripts/start-faster-whisper-server.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
PORT="${VOICEMODE_FASTER_WHISPER_PORT:-2023}"
# speaches serves an OpenAI-compatible API (verbose_json + word timestamps).
exec speaches serve --host 127.0.0.1 --port "$PORT"
```

(Adjust the `speaches serve` invocation to match the installed speaches CLI; consult `speaches --help` during implementation. The contract that matters: an OpenAI-compatible `/v1/audio/transcriptions` on `$PORT`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_faster_whisper_provider.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/faster_whisper/ voice_mode/templates/scripts/start-faster-whisper-server.sh voice_mode/config.py voice_mode/provider_discovery.py tests/test_faster_whisper_provider.py
git commit -m "feat: faster-whisper (speaches) STT service install tool + provider detection"
```

---

### Task 7: Register faster-whisper in the service manager

**Files:**
- Modify: `voice_mode/tools/service.py` (service-name map ~`:30-33`, and any `_SERVICE_FILE_NAMES` / status branches)
- Test: `tests/test_service_faster_whisper.py`

**Interfaces:**
- Consumes: the launchd/systemd unit names from Task 6 (`com.voicemode.faster-whisper` / `voicemode-faster-whisper`).
- Produces: `service("faster_whisper", "status"|"start"|"stop"|...)` resolves to the correct unit, mirroring the whisper/kokoro/mlx_audio entries.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_service_faster_whisper.py
from voice_mode.tools.service import _SERVICE_FILE_NAMES  # adjust to actual symbol


def test_faster_whisper_registered():
    assert "faster_whisper" in _SERVICE_FILE_NAMES
    assert _SERVICE_FILE_NAMES["faster_whisper"] == "faster-whisper"
```

(If the service map symbol differs, read `voice_mode/tools/service.py:30-33` and assert against the real structure — the point is that `faster_whisper` is a known service.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service_faster_whisper.py -v`
Expected: FAIL — `KeyError`/`AssertionError`, key absent.

- [ ] **Step 3: Write minimal implementation**

Add `faster_whisper` to the service name map beside `whisper`/`kokoro`/`mlx_audio` in `service.py:30-33`, and extend any status-path branches that enumerate services (grep `mlx_audio` in `service.py` and add a parallel `faster_whisper` branch at each hit).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_service_faster_whisper.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/service.py tests/test_service_faster_whisper.py
git commit -m "feat: register faster-whisper in service manager"
```

---

### Task 8: converse docstring + CHANGELOG

**Files:**
- Modify: `voice_mode/tools/converse.py` (converse docstring block near `:1862` where params are listed)
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Test: none (docs only) — verify with a grep step.

**Interfaces:** none produced.

- [ ] **Step 1: Add the docstring line**

In the converse docstring parameter list (near the `metrics_level` bullet at `:1862`), add:

```
• measure_blocks (bool): When true, render this turn as a VAD-timed block timeline —
  `text (Ns)` speech blocks and `(gap Ns)` silences (e.g. `모델은 (0.7s) (gap 5.3s) 음 잘모르겠어요 (6.3s)`).
  Replaces the ⟨pause⟩/Silence: markers for the turn. Durations are seconds; you judge
  stumbling/thinking from them. Requires a word-timestamp STT backend (faster-whisper).
```

- [ ] **Step 2: Add CHANGELOG entries**

Under `## [Unreleased]` `### Added`:

```markdown
- `converse` `measure_blocks` parameter: renders a user turn as a VAD-timed block
  timeline (`text (Ns)` speech blocks + `(gap Ns)` silences) so the assistant can
  perceive per-block timing (stumbling vs thinking). Replaces the significant-silence
  markers for that turn when enabled.
- faster-whisper (speaches) local STT backend for accurate word timestamps, installed
  and managed like the existing local services (port 2023).
```

- [ ] **Step 3: Verify**

Run: `grep -n "measure_blocks" voice_mode/tools/converse.py CHANGELOG.md`
Expected: hits in both files.

- [ ] **Step 4: Commit**

```bash
git add voice_mode/tools/converse.py CHANGELOG.md
git commit -m "docs: measure_blocks converse param + changelog"
```

---

### Task 9: SKILL changes via writing-skills (RED-GREEN-REFACTOR)

**Files:**
- Modify: `skills/voicemode/SKILL.md` and/or `.claude/skills/converse/SKILL.md` (whichever drives converse)
- Baseline artifact: `docs/superpowers/skill-baselines/2026-07-04-measure-blocks-baseline.md`

**Interfaces:** none (agent-behavior skill).

**This task MUST be executed under `superpowers:writing-skills`. Do NOT hand-edit the SKILL body without a documented failing baseline first.**

- [ ] **Step 1: Invoke the skill**

Use the Skill tool: `superpowers:writing-skills`. Follow its RED-GREEN-REFACTOR loop.

- [ ] **Step 2: RED — run baseline scenarios (no guidance), document verbatim**

Two scenarios via subagents, capture actual behavior into the baseline artifact:
1. User says something that warrants detailed timing metadata for the next turn; does the assistant set `measure_blocks=true`? (Baseline expectation: it does not — the param is unknown.)
2. Given a converse result containing `모델은 (0.7s) (gap 5.3s) 음 잘모르겠어요. 그... (6.3s)`, does the assistant read it as timing (stumbling/thinking) rather than literal spoken text? (Baseline expectation: it misreads the `(Ns)` as content.)

Write both baselines (verbatim rationalizations) to the baseline artifact and commit it.

- [ ] **Step 3: GREEN — minimal SKILL wording**

Add guidance addressing exactly those two failures:
- *When* to set `measure_blocks=true` (trigger condition — the assistant wants per-block timing of how the user is speaking).
- *How* to read a block timeline (`text (Ns)` = speech block + its duration; `(gap Ns)` = silence; fillers inline; long block/few words = stumbling; long gap = thinking; seconds only — you judge).
- The `description` frontmatter must state only *when to use* (a trigger), never summarize the reading workflow.

- [ ] **Step 4: Re-run scenarios WITH the skill; verify compliance**

Both scenarios now pass (sets the flag; reads the timeline as timing). If a new rationalization appears, add an explicit counter (REFACTOR) and re-test.

- [ ] **Step 5: Commit**

```bash
git add skills/ .claude/skills/ docs/superpowers/skill-baselines/2026-07-04-measure-blocks-baseline.md
git commit -m "docs(skill): guide measure_blocks trigger + block-timeline reading (RED-GREEN-REFACTOR)"
```

---

### Task 10: Full-suite regression check

**Files:** none (verification only).

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: PASS, including pre-existing silence/marker tests (confirms `measure_blocks=false` path is unchanged).

- [ ] **Step 2: Targeted regression on the marker path**

Run: `uv run pytest tests/ -v -k "silence or marker or block or measure"`
Expected: PASS. Confirms AC 3 (default reproduces today's behavior) and AC 7 (timeline replaces markers only when on).

- [ ] **Step 3: Commit any fixes**

If a pre-existing test broke (e.g. `SilenceProfile.empty()` arity), fix inline and:

```bash
git add -A
git commit -m "fix: reconcile SilenceProfile arity with existing callers"
```

---

## Notes for the implementer

- **AC mapping:** Task 6/7 → AC 1,2. Task 4 → AC 8. Task 5 → AC 3,4,7,9. Task 1/2/3 → AC 4,5,6. Task 9 → AC 10. Task 10 guards AC 3.
- **Filler (AC 6):** there is deliberately no filler code anywhere — fillers ride inside a speech block's assigned text. If you find yourself adding a filler dictionary, stop: that was rejected in the spec.
- **VAD is the clock (AC 5):** never compute a block/gap duration from `words`. Words only choose *which* block a token's text lands in.
