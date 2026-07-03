# Explicit Turn Handoff & Silence Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop VoiceMode from cutting users off mid-hesitation, and let the assistant perceive how much a user hesitated, via a single `silence_release_sec` turn-control scalar plus an always-on per-turn silence profile with inline transcript markers.

**Architecture:** Two independent axes in `voice_mode/tools/converse.py`. (1) Turn control: replace the `disable_silence_detection` boolean logic in the VAD loop with a `silence_release_sec` scalar (0 = current VAD, N = tolerate Ns then release, -1 = never). (2) Observability: the recording function returns a `SilenceProfile` computed every turn; significant silences (≥2s) become inline `⟨pause Ns⟩` / `⟨pre-speech Ns⟩` markers aligned to the transcript via word-timestamp STT, requested only on turns that had a significant gap.

**Tech Stack:** Python 3.10+, `uv` for deps/tests, `pytest`, WebRTC VAD (`webrtcvad`), existing `voice_mode/tools/transcription/` word-timestamp path, FastMCP.

## Global Constraints

- Test runner: `uv run pytest <path> -v --tb=short`. Never call `pip`/`pytest` directly.
- Do NOT link to GitHub issues or open an upstream PR — personal customization on branch `feat/explicit-turn-handoff`.
- `silence_release_sec` value semantics are fixed: `0` = current VAD threshold behavior; `N>0` = tolerate silence up to N seconds then release; `-1` = never release on silence.
- `disable_silence_detection=true` MUST remain a working alias for `silence_release_sec=-1` (backward compat).
- `listen_duration_max` default = `180.0`; hard clamp = `300.0` (any larger value, from any source, clamps to 300).
- Significance threshold default = `2.0` seconds; applies to both pre-speech delay and speech gaps.
- Silence marker format: `⟨pause 5.1s⟩` (speech gap), `⟨pre-speech 3.2s⟩` (pre-speech delay), duration to one decimal place, using the `⟨` `⟩` angle-bracket characters (U+27E8 / U+27E9).
- Word-timestamp STT is requested ONLY on turns that contain a significant silence.
- The `Silence:` result field and markers appear ONLY when a significant silence occurred; immediate-answer turns stay clean. Verbose metrics level always shows the full profile.
- SKILL body edits (Task 9) MUST go through `superpowers:writing-skills` RED-GREEN-REFACTOR — a failing baseline first, never a hand-edit.

**Key existing locations (verified):**
- `record_audio_with_silence_detection()` — `voice_mode/tools/converse.py:1242` (signature), VAD state machine `:1417-1453`, returns `:1481-1485`, fallbacks `:1526,1538,1553`.
- Early disable check — `converse.py:1267-1273`.
- Record call site — `converse.py:2519-2524`.
- No-speech / STT branch — `converse.py:2598-2675`.
- Result assembly — `converse.py:2958-2982`.
- Config silence block — `voice_mode/config.py:850-864`.
- Word-timestamp STT — `voice_mode/tools/transcription/core.py` (`transcribe(..., word_timestamps=bool)`), `backends.py:45-56`.

---

### Task 1: Config — new silence/turn-control settings

**Files:**
- Modify: `voice_mode/config.py:850-864`
- Test: `tests/test_config_silence.py` (create)

**Interfaces:**
- Produces: module-level constants `SILENCE_RELEASE_SEC: float`, `SIGNIFICANCE_THRESHOLD_SEC: float`, `MAX_LISTEN_DURATION: float`, and changed default `DEFAULT_LISTEN_DURATION == 180.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_silence.py
import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import voice_mode.config as cfg
    return importlib.reload(cfg)


def test_silence_release_sec_default_zero(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.SILENCE_RELEASE_SEC == 0.0


def test_significance_threshold_default(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.SIGNIFICANCE_THRESHOLD_SEC == 2.0


def test_default_listen_duration_is_180(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.DEFAULT_LISTEN_DURATION == 180.0


def test_max_listen_duration_hard_cap(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.MAX_LISTEN_DURATION == 300.0


def test_silence_release_sec_env_override(monkeypatch):
    cfg = _reload_config(monkeypatch, VOICEMODE_SILENCE_RELEASE_SEC="60")
    assert cfg.SILENCE_RELEASE_SEC == 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_silence.py -v --tb=short`
Expected: FAIL — `AttributeError: module 'voice_mode.config' has no attribute 'SILENCE_RELEASE_SEC'` (and the 180 assertion fails: current default is 120.0).

- [ ] **Step 3: Write minimal implementation**

In `voice_mode/config.py`, change line 864 and add new constants right after the silence block:

```python
# Default listen duration for converse tool
DEFAULT_LISTEN_DURATION = float(os.getenv("VOICEMODE_DEFAULT_LISTEN_DURATION", "180.0"))  # Default 180s (3 min) listening time

# Absolute upper bound on any listen duration (per-call values clamp to this)
MAX_LISTEN_DURATION = float(os.getenv("VOICEMODE_MAX_LISTEN_DURATION", "300.0"))  # Hard cap: 5 min

# Silence release scalar: 0 = end on normal VAD threshold (current behavior);
# N>0 = tolerate silence up to N seconds within/before the turn, then release;
# -1 = never release on silence (turn ends only at listen_duration_max or skip_forward).
SILENCE_RELEASE_SEC = float(os.getenv("VOICEMODE_SILENCE_RELEASE_SEC", "0"))

# A pre-speech delay or speech gap is "significant" (surfaced as a marker) at or above this many seconds.
SIGNIFICANCE_THRESHOLD_SEC = float(os.getenv("VOICEMODE_SILENCE_SIGNIFICANCE_SEC", "2.0"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_silence.py -v --tb=short`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add voice_mode/config.py tests/test_config_silence.py
git commit -m "feat: config for silence_release_sec, significance threshold, 180s/300s listen bounds"
```

---

### Task 2: `SilenceProfile` dataclass

**Files:**
- Create: `voice_mode/tools/silence_profile.py`
- Test: `tests/test_silence_profile.py` (create)

**Interfaces:**
- Produces: `SilenceProfile` dataclass with fields `pre_speech_delay: float`, `longest_gap: float`, `total_silence: float`, `speech_active: float`, and gap-position data `gaps: list[tuple[float, float]]` (each `(start_s, end_s)` relative to record start, speech-internal gaps only). Method `significant_gaps(threshold: float) -> list[tuple[float, float]]` and property `pre_speech_significant(threshold) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_silence_profile.py
from voice_mode.tools.silence_profile import SilenceProfile


def test_fields_and_speech_active():
    p = SilenceProfile(pre_speech_delay=3.2, longest_gap=5.1,
                       total_silence=8.3, speech_active=4.0,
                       gaps=[(4.2, 9.3)])
    assert p.pre_speech_delay == 3.2
    assert p.longest_gap == 5.1
    assert p.total_silence == 8.3
    assert p.speech_active == 4.0
    assert p.gaps == [(4.2, 9.3)]


def test_significant_gaps_filters_by_threshold():
    p = SilenceProfile(0.0, 5.1, 6.0, 10.0,
                       gaps=[(1.0, 1.9), (4.2, 9.3)])  # 0.9s and 5.1s
    assert p.significant_gaps(2.0) == [(4.2, 9.3)]


def test_pre_speech_significant():
    p = SilenceProfile(3.2, 0.0, 3.2, 5.0, gaps=[])
    assert p.pre_speech_significant(2.0) is True
    assert p.pre_speech_significant(4.0) is False


def test_empty_profile():
    p = SilenceProfile.empty()
    assert p.pre_speech_delay == 0.0
    assert p.gaps == []
    assert p.significant_gaps(2.0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_silence_profile.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_mode.tools.silence_profile'`

- [ ] **Step 3: Write minimal implementation**

```python
# voice_mode/tools/silence_profile.py
"""Per-turn silence profile for empathetic hesitation signalling.

Computed on every recording, independent of turn-control policy. A gap is a
silence run *between* the user's own words (speech-internal); pre_speech_delay
is the silence before the user starts speaking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SilenceProfile:
    pre_speech_delay: float
    longest_gap: float
    total_silence: float
    speech_active: float
    gaps: List[Tuple[float, float]] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "SilenceProfile":
        return cls(0.0, 0.0, 0.0, 0.0, [])

    def significant_gaps(self, threshold: float) -> List[Tuple[float, float]]:
        return [(s, e) for (s, e) in self.gaps if (e - s) >= threshold]

    def pre_speech_significant(self, threshold: float) -> bool:
        return self.pre_speech_delay >= threshold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_silence_profile.py -v --tb=short`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/silence_profile.py tests/test_silence_profile.py
git commit -m "feat: SilenceProfile dataclass with gap-position data"
```

---

### Task 3: Marker insertion + result-field formatting (pure functions)

**Files:**
- Create: `voice_mode/tools/silence_markers.py`
- Test: `tests/test_silence_markers.py` (create)

**Interfaces:**
- Consumes: `SilenceProfile` (Task 2), word list `list[dict]` with `{"word": str, "start": float, "end": float}` (shape produced by `voice_mode/tools/transcription` word timestamps).
- Produces:
  - `insert_markers(text: str, words: list[dict], profile: SilenceProfile, threshold: float) -> str` — returns transcript with `⟨pre-speech Ns⟩` prepended (if pre-speech significant) and `⟨pause Ns⟩` inserted between the words bracketing each significant gap. If `words` is empty/None, returns `text` unchanged (fallback path).
  - `format_silence_field(profile: SilenceProfile, threshold: float) -> str | None` — returns `"pre {p}s, gap {g}s, speech {s}s"` including only significant `pre`/`gap` sub-fields (speech always shown); returns `None` when nothing significant.
  - `MARKER_OPEN = "⟨"`, `MARKER_CLOSE = "⟩"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_silence_markers.py
from voice_mode.tools.silence_profile import SilenceProfile
from voice_mode.tools.silence_markers import insert_markers, format_silence_field


WORDS = [
    {"word": "결제하려는데", "start": 3.2, "end": 4.2},
    {"word": "카드가", "start": 9.3, "end": 9.9},
    {"word": "안돼요", "start": 9.9, "end": 10.5},
]


def test_insert_pause_between_bracketing_words():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert "결제하려는데 ⟨pause 5.1s⟩ 카드가" in out


def test_insert_pre_speech_prefix():
    prof = SilenceProfile(3.2, 0.0, 3.2, 3.0, gaps=[])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert out.startswith("⟨pre-speech 3.2s⟩ ")


def test_no_significant_no_change():
    prof = SilenceProfile(0.5, 0.8, 1.3, 5.0, gaps=[(4.2, 5.0)])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert out == "결제하려는데 카드가 안돼요"


def test_missing_words_fallback_unchanged():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    assert insert_markers("결제하려는데 카드가", [], prof, 2.0) == "결제하려는데 카드가"


def test_format_field_only_significant():
    prof = SilenceProfile(3.2, 0.8, 4.0, 6.0, gaps=[(1.0, 1.8)])
    # pre 3.2 significant, gap 0.8 not
    assert format_silence_field(prof, 2.0) == "pre 3.2s, speech 6.0s"


def test_format_field_none_when_clean():
    prof = SilenceProfile(0.3, 0.5, 0.8, 4.0, gaps=[])
    assert format_silence_field(prof, 2.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_silence_markers.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_mode.tools.silence_markers'`

- [ ] **Step 3: Write minimal implementation**

```python
# voice_mode/tools/silence_markers.py
"""Align significant silences to a transcript as inline markers, and format
the summary Silence: field. Pure functions — no I/O."""
from __future__ import annotations

from typing import List, Dict, Optional

from voice_mode.tools.silence_profile import SilenceProfile

MARKER_OPEN = "⟨"
MARKER_CLOSE = "⟩"


def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s"


def insert_markers(text: str, words: Optional[List[Dict]], profile: SilenceProfile,
                   threshold: float) -> str:
    if not words:
        # Fallback: no word timestamps -> can't position markers, leave text as-is.
        return text

    # Build the marker for each significant gap keyed by the index of the word it
    # follows (the last word that ends at or before the gap start).
    after_word_marker: Dict[int, str] = {}
    for (gap_start, gap_end) in profile.significant_gaps(threshold):
        follow_idx = 0
        for i, w in enumerate(words):
            if w["end"] <= gap_start + 1e-6:
                follow_idx = i
        after_word_marker[follow_idx] = f"{MARKER_OPEN}pause {_fmt(gap_end - gap_start)}{MARKER_CLOSE}"

    # Rebuild the text from the word list so insertion positions are unambiguous.
    pieces: List[str] = []
    for i, w in enumerate(words):
        pieces.append(w["word"])
        if i in after_word_marker:
            pieces.append(after_word_marker[i])
    rebuilt = " ".join(pieces)

    if profile.pre_speech_significant(threshold):
        rebuilt = f"{MARKER_OPEN}pre-speech {_fmt(profile.pre_speech_delay)}{MARKER_CLOSE} " + rebuilt

    return rebuilt


def format_silence_field(profile: SilenceProfile, threshold: float) -> Optional[str]:
    parts: List[str] = []
    if profile.pre_speech_significant(threshold):
        parts.append(f"pre {_fmt(profile.pre_speech_delay)}")
    if profile.significant_gaps(threshold):
        parts.append(f"gap {_fmt(profile.longest_gap)}")
    if not parts:
        return None
    parts.append(f"speech {_fmt(profile.speech_active)}")
    return ", ".join(parts)
```

Note: `insert_markers` rebuilds the transcript from the word list when markers apply, so the returned text uses the STT word tokenization (acceptable — only happens on significant-silence turns; the `no_significant` case returns the original `text` verbatim because `significant_gaps` is empty and pre-speech is not significant, so the rebuilt branch is skipped). Adjust the `test_no_significant_no_change` expectation only if tokenization differs; here inputs match.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_silence_markers.py -v --tb=short`
Expected: PASS (6 passed)

Wait — `test_no_significant_no_change` expects the original string returned, but the function rebuilds from `words` only when a marker/pre-speech applies. With no significant gap and non-significant pre-speech, no `after_word_marker` entries exist AND `pre_speech_significant` is False, so the function still reaches the rebuilt `" ".join(pieces)`. Fix: early-return `text` when nothing is significant.

- [ ] **Step 5: Apply the early-return fix**

Insert at the top of `insert_markers`, after the `if not words` guard:

```python
    has_gap = bool(profile.significant_gaps(threshold))
    has_pre = profile.pre_speech_significant(threshold)
    if not has_gap and not has_pre:
        return text
```

- [ ] **Step 6: Re-run test to verify it passes**

Run: `uv run pytest tests/test_silence_markers.py -v --tb=short`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add voice_mode/tools/silence_markers.py tests/test_silence_markers.py
git commit -m "feat: inline silence markers + Silence: field formatting"
```

---

### Task 4: VAD loop computes `SilenceProfile` and returns it

**Files:**
- Modify: `voice_mode/tools/converse.py:1242` (signature + return), `:1294-1296` (state vars), `:1417-1453` (state machine), `:1463-1485` (return), fallbacks `:1526,1538,1553,1265,1273`
- Test: `tests/test_record_returns_profile.py` (create)

**Interfaces:**
- Consumes: `SilenceProfile` (Task 2), config `SILENCE_RELEASE_SEC`, `SIGNIFICANCE_THRESHOLD_SEC` (Task 1).
- Produces: `record_audio_with_silence_detection(max_duration, silence_release_sec=0.0, min_duration=0.0, vad_aggressiveness=None) -> tuple[np.ndarray, bool, SilenceProfile]`. The `disable_silence_detection` boolean param is REMOVED from this function; callers pass `silence_release_sec` (Task 6 handles the alias at the converse layer). Return is now a 3-tuple; profile is `SilenceProfile.empty()` on fallback paths.

**Design note (turn-ending rule inside the loop):**
- `silence_release_sec == 0` → use existing `SILENCE_THRESHOLD_MS` behavior (unchanged).
- `silence_release_sec > 0` → the stop condition uses `silence_duration_ms >= silence_release_sec * 1000` instead of `SILENCE_THRESHOLD_MS` (tolerate longer). Pre-speech: no change (WAITING_FOR_SPEECH already has no timeout; the turn simply won't end before speech — pre-speech delay is recorded for the profile).
- `silence_release_sec < 0` (i.e. -1) → never set `stop_recording` from silence; only `max_duration` ends it.
- Regardless of release policy, the loop tracks `pre_speech_delay`, every completed speech-internal gap `(start_s, end_s)`, `total_silence`, and `speech_active` for the profile.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_record_returns_profile.py
import inspect
import numpy as np
import voice_mode.tools.converse as c
from voice_mode.tools.silence_profile import SilenceProfile


def test_signature_has_silence_release_sec_no_disable_bool():
    sig = inspect.signature(c.record_audio_with_silence_detection)
    params = list(sig.parameters)
    assert "silence_release_sec" in params
    assert "disable_silence_detection" not in params


def test_returns_three_tuple_with_profile(monkeypatch):
    # Force the no-VAD fallback so the test needs no microphone.
    monkeypatch.setattr(c, "VAD_AVAILABLE", False)
    monkeypatch.setattr(c, "record_audio", lambda d: np.array([0.0], dtype=np.float32))
    result = c.record_audio_with_silence_detection(1.0)
    assert isinstance(result, tuple) and len(result) == 3
    audio, speech, profile = result
    assert isinstance(profile, SilenceProfile)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_record_returns_profile.py -v --tb=short`
Expected: FAIL — signature still has `disable_silence_detection`; return is a 2-tuple (`too many values`/assertion on len).

- [ ] **Step 3: Change the signature and fallbacks**

Edit `converse.py:1242`:

```python
def record_audio_with_silence_detection(max_duration: float, silence_release_sec: float = 0.0, min_duration: float = 0.0, vad_aggressiveness: Optional[int] = None) -> Tuple[np.ndarray, bool, "SilenceProfile"]:
```

Add import near the top of the file (with the other tool imports):

```python
from voice_mode.tools.silence_profile import SilenceProfile
```

Update the early no-VAD fallback (`:1262-1265`):

```python
    if not VAD_AVAILABLE:
        logger.warning("webrtcvad not available, falling back to fixed duration recording")
        return (record_audio(max_duration), True, SilenceProfile.empty())
```

Replace the disable-detection early block (`:1267-1273`) with the release-policy gate. `silence_release_sec < 0` means "never release on silence" — record for the fixed max:

```python
    global_disabled = DISABLE_SILENCE_DETECTION  # legacy global env still honored as -1
    effective_release = silence_release_sec
    if global_disabled and effective_release == 0.0:
        effective_release = -1.0
    if effective_release < 0:
        logger.info("Silence release disabled (silence_release_sec=-1): fixed-duration record")
        return (record_audio(max_duration), True, SilenceProfile.empty())
```

Update the two error/exception fallbacks (`:1526` recursive retry, `:1538`, `:1553`) to pass `silence_release_sec` and return 3-tuples:

```python
    # :1526 recursive retry
    return record_audio_with_silence_detection(max_duration, silence_release_sec, min_duration, vad_aggressiveness)
    # :1538 and :1553
    return (record_audio(max_duration), True, SilenceProfile.empty())
```

- [ ] **Step 4: Add profile tracking to the state machine**

At the state-var block (`:1293-1296`) add trackers:

```python
        chunks = []
        silence_duration_ms = 0
        recording_duration = 0
        speech_detected = False
        # --- silence profile trackers ---
        pre_speech_delay_s = 0.0
        total_silence_s = 0.0
        speech_active_s = 0.0
        gaps: list = []              # completed speech-internal gaps (start_s, end_s)
        current_gap_start = None     # start time of an in-progress gap
```

In the state machine (`:1417-1453`), extend each branch. Replace the block with:

```python
                        # State machine for speech detection
                        if not speech_detected:
                            # WAITING_FOR_SPEECH: accumulate pre-speech delay
                            if is_speech:
                                logger.info("🎤 Speech detected, starting active recording")
                                speech_detected = True
                                silence_duration_ms = 0
                            else:
                                pre_speech_delay_s += chunk_duration_s
                                total_silence_s += chunk_duration_s
                        else:
                            if is_speech:
                                # SPEECH_ACTIVE: close any in-progress gap
                                if current_gap_start is not None:
                                    gaps.append((current_gap_start, recording_duration))
                                    current_gap_start = None
                                speech_active_s += chunk_duration_s
                                silence_duration_ms = 0
                            else:
                                # SILENCE_AFTER_SPEECH
                                if current_gap_start is None:
                                    current_gap_start = recording_duration
                                silence_duration_ms += VAD_CHUNK_DURATION_MS
                                total_silence_s += chunk_duration_s

                                effective_min_duration = max(MIN_RECORDING_DURATION, min_duration)
                                # Release threshold: 0 -> legacy SILENCE_THRESHOLD_MS; >0 -> scalar seconds.
                                if effective_release > 0:
                                    release_ms = effective_release * 1000
                                else:
                                    release_ms = SILENCE_THRESHOLD_MS
                                if recording_duration >= effective_min_duration and silence_duration_ms >= release_ms:
                                    logger.info(f"✓ Silence release reached after {recording_duration:.1f}s (threshold {release_ms:.0f}ms)")
                                    stop_recording = True

                        recording_duration += chunk_duration_s
```

(Keep the surrounding `try/except` for `vad.is_speech` and the `recording_duration += chunk_duration_s` line — the replacement above already includes the increment; delete the old duplicate increment at `:1454` to avoid double counting.)

- [ ] **Step 5: Build the profile at return**

At the concatenate/return block (`:1463-1485`) build the profile before returning:

```python
            if chunks:
                full_recording = np.concatenate(chunks)
                # Close a gap still open at end-of-turn.
                if current_gap_start is not None:
                    gaps.append((current_gap_start, recording_duration))
                longest_gap = max((e - s for (s, e) in gaps), default=0.0)
                profile = SilenceProfile(
                    pre_speech_delay=pre_speech_delay_s,
                    longest_gap=longest_gap,
                    total_silence=total_silence_s,
                    speech_active=speech_active_s,
                    gaps=gaps,
                )
                if not speech_detected:
                    logger.info(f"✓ Recording completed ({recording_duration:.1f}s) - No speech detected")
                else:
                    logger.info(f"✓ Recorded {len(full_recording)} samples ({recording_duration:.1f}s) with speech")
                return (full_recording, speech_detected, profile)
            else:
                logger.warning("No audio chunks recorded")
                return (np.array([]), False, SilenceProfile.empty())
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_record_returns_profile.py -v --tb=short`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_record_returns_profile.py
git commit -m "feat: record loop computes SilenceProfile; silence_release_sec scalar replaces disable bool in VAD"
```

---

### Task 5: Unit-test the release policy inside the loop (gap timing)

**Files:**
- Modify: `tests/test_record_returns_profile.py`

**Interfaces:**
- Consumes: `record_audio_with_silence_detection` 3-tuple return (Task 4).

This task adds a focused test that drives the loop with synthetic audio to verify gap capture and the release scalar, using a fake VAD and fake audio queue. If mocking the full sounddevice stream is impractical, assert via a thin extract of the state-machine logic instead.

- [ ] **Step 1: Write the failing test (state-machine extract)**

Add a small pure helper to `converse.py` that the loop also uses, so it is unit-testable without audio:

```python
# converse.py — add near record_audio_with_silence_detection
def _release_threshold_ms(silence_release_sec: float) -> float:
    """0 -> legacy SILENCE_THRESHOLD_MS; >0 -> scalar seconds in ms; <0 -> inf (never)."""
    if silence_release_sec > 0:
        return silence_release_sec * 1000
    if silence_release_sec < 0:
        return float("inf")
    return float(SILENCE_THRESHOLD_MS)
```

Test:

```python
def test_release_threshold_mapping():
    from voice_mode.tools.converse import _release_threshold_ms, SILENCE_THRESHOLD_MS
    assert _release_threshold_ms(0) == float(SILENCE_THRESHOLD_MS)
    assert _release_threshold_ms(60) == 60000
    assert _release_threshold_ms(-1) == float("inf")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_record_returns_profile.py::test_release_threshold_mapping -v --tb=short`
Expected: FAIL — `_release_threshold_ms` not defined.

- [ ] **Step 3: Implement + wire the helper**

Add the helper (above) and replace the inline `if effective_release > 0: release_ms = ... else: release_ms = SILENCE_THRESHOLD_MS` block from Task 4 Step 4 with:

```python
                                release_ms = _release_threshold_ms(effective_release)
```

(`silence_duration_ms >= inf` is always False, giving the "never release" behavior for -1 without a special branch.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_record_returns_profile.py -v --tb=short`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_record_returns_profile.py
git commit -m "test: release-threshold mapping (0=legacy, N=scalar, -1=never)"
```

---

### Task 6: `converse` param — `silence_release_sec`, alias, listen clamp

**Files:**
- Modify: `voice_mode/tools/converse.py:1687-1716` (converse signature), `:2519-2524` (record call site), and the point where `listen_duration_max` is resolved (top of the local-mic path).
- Test: `tests/test_converse_params.py` (create)

**Interfaces:**
- Consumes: `record_audio_with_silence_detection(..., silence_release_sec, ...)` (Task 4), config `DEFAULT_LISTEN_DURATION`, `MAX_LISTEN_DURATION`, `SILENCE_RELEASE_SEC` (Task 1).
- Produces: `converse(...)` gains `silence_release_sec: Optional[float] = None` (None → config default). `disable_silence_detection` kept as deprecated alias: if truthy, forces `silence_release_sec = -1`. `listen_duration_max` clamped to `MAX_LISTEN_DURATION`. A module-level helper `_resolve_silence_release(silence_release_sec, disable_silence_detection) -> float` and `_clamp_listen(v) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_converse_params.py
from voice_mode.tools.converse import _resolve_silence_release, _clamp_listen


def test_disable_alias_forces_minus_one():
    assert _resolve_silence_release(None, True) == -1.0
    assert _resolve_silence_release(60, True) == -1.0  # alias wins when set


def test_none_uses_config_default(monkeypatch):
    import voice_mode.tools.converse as c
    monkeypatch.setattr(c, "SILENCE_RELEASE_SEC", 0.0)
    assert _resolve_silence_release(None, False) == 0.0


def test_explicit_value_passthrough():
    assert _resolve_silence_release(60, False) == 60.0


def test_clamp_listen_caps_at_300():
    assert _clamp_listen(500) == 300.0
    assert _clamp_listen(180) == 180.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_converse_params.py -v --tb=short`
Expected: FAIL — helpers not defined.

- [ ] **Step 3: Implement the helpers**

Add near the top of `converse.py` (after config imports; ensure `MAX_LISTEN_DURATION`, `SILENCE_RELEASE_SEC` are imported from config):

```python
def _resolve_silence_release(silence_release_sec, disable_silence_detection) -> float:
    """Deprecated disable flag is an alias for -1 (never release). Otherwise
    use the explicit value, or the config default when None."""
    if disable_silence_detection:
        return -1.0
    if silence_release_sec is None:
        return float(SILENCE_RELEASE_SEC)
    return float(silence_release_sec)


def _clamp_listen(value: float) -> float:
    return min(float(value), MAX_LISTEN_DURATION)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_converse_params.py -v --tb=short`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire into converse signature and call site**

Add `silence_release_sec: Optional[Union[float, str]] = None` to the `converse()` signature (near `disable_silence_detection`, `:1687-1716`). Coerce a str value to float early (mirroring how other numeric-or-str params are parsed in this function).

At the record resolution point (just before `:2519`):

```python
                    listen_duration_max = _clamp_listen(listen_duration_max)
                    effective_release = _resolve_silence_release(silence_release_sec, disable_silence_detection)
```

Replace the record call (`:2521-2523`) — note the new 3-tuple and the param swap:

```python
                    audio_data, speech_detected, silence_prof = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio_with_silence_detection, listen_duration_max, effective_release, listen_duration_min, vad_aggressiveness
                    )
```

Also update the second record call site if one exists (`:2747` per grep) with the same 3-tuple + `effective_release` swap.

- [ ] **Step 6: Run the existing converse tests to catch breakage**

Run: `uv run pytest tests/ -k "converse" -v --tb=short`
Expected: PASS (any 2-tuple unpacking failures in tests must be updated to 3-tuple; fix and re-run).

- [ ] **Step 7: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_converse_params.py
git commit -m "feat: converse silence_release_sec param, disable alias -> -1, 300s listen clamp"
```

---

### Task 7: Conditional word-timestamp STT on significant-gap turns

**Files:**
- Modify: `voice_mode/tools/converse.py:2610-2675` (STT branch)
- Test: `tests/test_converse_word_timestamps_gate.py` (create)

**Interfaces:**
- Consumes: `silence_prof` (Task 6), `SIGNIFICANCE_THRESHOLD_SEC`, `speech_to_text(...)`.
- Produces: a decision helper `_needs_word_timestamps(profile, threshold) -> bool` (True iff any significant gap OR significant pre-speech), and STT invoked with word timestamps only when True. Words list captured into `stt_words` (list[dict] or None).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_converse_word_timestamps_gate.py
from voice_mode.tools.converse import _needs_word_timestamps
from voice_mode.tools.silence_profile import SilenceProfile


def test_needs_true_on_significant_gap():
    p = SilenceProfile(0.0, 5.1, 5.1, 2.0, gaps=[(4.2, 9.3)])
    assert _needs_word_timestamps(p, 2.0) is True


def test_needs_true_on_significant_pre_speech():
    p = SilenceProfile(3.2, 0.0, 3.2, 3.0, gaps=[])
    assert _needs_word_timestamps(p, 2.0) is True


def test_needs_false_when_clean():
    p = SilenceProfile(0.3, 0.8, 1.1, 5.0, gaps=[(1.0, 1.8)])
    assert _needs_word_timestamps(p, 2.0) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_converse_word_timestamps_gate.py -v --tb=short`
Expected: FAIL — `_needs_word_timestamps` not defined.

- [ ] **Step 3: Implement helper + wire STT**

Add helper near the other converse helpers:

```python
def _needs_word_timestamps(profile, threshold: float) -> bool:
    return bool(profile.significant_gaps(threshold)) or profile.pre_speech_significant(threshold)
```

In the STT branch (`:2616-2618`), gate word timestamps. The existing call is `stt_result = await speech_to_text(audio_data, SAVE_AUDIO, ...)`. This design uses the word-timestamp-capable transcription path when needed. Two integration options — pick the one matching `speech_to_text`'s current plumbing:

  (a) If `speech_to_text` can accept a `word_timestamps` flag, thread it:

```python
                    want_words = _needs_word_timestamps(silence_prof, SIGNIFICANCE_THRESHOLD_SEC)
                    stt_result = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport, word_timestamps=want_words)
                    stt_words = stt_result.get("words") if isinstance(stt_result, dict) else None
```

  (b) If `speech_to_text` does not expose it, add an optional `word_timestamps: bool = False` kwarg to `speech_to_text` (`:934`) that, when True, routes to `voice_mode/tools/transcription/core.transcribe(..., word_timestamps=True)` and includes `"words"` in the returned dict; else keeps the current `simple_stt_failover` path. Implement the minimal kwarg + branch.

Set `stt_words = None` in the no-speech branch (`:2600`) so it is always defined before result assembly.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_converse_word_timestamps_gate.py -v --tb=short`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_converse_word_timestamps_gate.py
git commit -m "feat: request word-timestamp STT only on significant-silence turns"
```

---

### Task 8: Wire markers + Silence field into the result string

**Files:**
- Modify: `voice_mode/tools/converse.py:2958-2982` (result assembly)
- Test: `tests/test_converse_result_silence.py` (create)

**Interfaces:**
- Consumes: `insert_markers`, `format_silence_field` (Task 3), `silence_prof`, `stt_words` (Task 7), `SIGNIFICANCE_THRESHOLD_SEC`.
- Produces: result string where `response_text` has markers inserted, and a `| Silence: ...` segment placed before `| Timing: ...` when `format_silence_field` is non-None. Verbose level appends the full profile always.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_converse_result_silence.py
from voice_mode.tools.converse import _assemble_voice_result
from voice_mode.tools.silence_profile import SilenceProfile

WORDS = [
    {"word": "결제하려는데", "start": 3.2, "end": 4.2},
    {"word": "카드가", "start": 9.3, "end": 9.9},
]


def test_summary_includes_markers_and_silence_field():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    out = _assemble_voice_result(
        response_text="결제하려는데 카드가", stt_info="", timing_str="record 10.0s",
        metrics_level="summary", profile=prof, words=WORDS, threshold=2.0)
    assert "⟨pause 5.1s⟩" in out
    assert "| Silence: gap 5.1s, speech 2.2s" in out
    assert "| Timing: record 10.0s" in out


def test_clean_turn_no_silence_field_no_markers():
    prof = SilenceProfile(0.2, 0.5, 0.7, 5.0, gaps=[])
    out = _assemble_voice_result(
        response_text="네 맞아요", stt_info="", timing_str="record 3.0s",
        metrics_level="summary", profile=prof, words=None, threshold=2.0)
    assert "⟨" not in out
    assert "Silence:" not in out
    assert out == "Voice response: 네 맞아요 | Timing: record 3.0s"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_converse_result_silence.py -v --tb=short`
Expected: FAIL — `_assemble_voice_result` not defined.

- [ ] **Step 3: Extract + implement the assembler**

Refactor the summary/verbose block (`:2958-2975`) into a testable function and call it. Add:

```python
def _assemble_voice_result(response_text, stt_info, timing_str, metrics_level, profile, words, threshold):
    from voice_mode.tools.silence_markers import insert_markers, format_silence_field
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
    # summary
    seg = f"Voice response: {text}{stt_info}"
    if silence_field:
        seg += f" | Silence: {silence_field}"
    seg += f" | Timing: {timing_str}"
    return seg
```

Replace the inline summary/verbose assignment at `:2960-2974` with:

```python
                    result = _assemble_voice_result(
                        response_text, stt_info, timing_str, effective_metrics_level,
                        silence_prof, stt_words, SIGNIFICANCE_THRESHOLD_SEC)
```

(Leave the verbose STT-request/file-size lines as-is if present — append them after this call only in the verbose branch, or fold them into the verbose `parts` here if simpler.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_converse_result_silence.py -v --tb=short`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full converse suite**

Run: `uv run pytest tests/ -k "converse" -v --tb=short`
Expected: PASS (fix any residual 2-tuple/format assumptions).

- [ ] **Step 6: Commit**

```bash
git add voice_mode/tools/converse.py tests/test_converse_result_silence.py
git commit -m "feat: insert silence markers and Silence: field into converse result"
```

---

### Task 9: SKILL guidance (RED-GREEN-REFACTOR via writing-skills)

**Files:**
- Modify: `.claude/skills/converse/SKILL.md` and/or `skills/voicemode/SKILL.md`
- Test: baseline pressure scenarios (documented in `docs/superpowers/plans/2026-07-03-explicit-turn-handoff.md` companion notes)

**This task is governed by `superpowers:writing-skills`. Do NOT hand-edit the SKILL body first.**

- [ ] **Step 1: RED — baseline**

Invoke `superpowers:writing-skills`. Run baseline scenarios WITHOUT the new guidance: (a) user says "생각 좀 할게, 끊지 마" — does the assistant set `silence_release_sec=60` on the next converse call? (b) a converse result contains `⟨pause 5.1s⟩ ... | Silence: gap 5.1s` — does the assistant acknowledge the hesitation empathetically? Document verbatim what the assistant does without guidance.

- [ ] **Step 2: GREEN — minimal SKILL wording**

Add two guidance blocks (per writing-skills form rules — recipe/conditional, not prohibition):
  - *When the user asks for more time or not to be cut off, set `silence_release_sec=60` on the next `converse` call.*
  - *A converse result may contain `⟨pause Ns⟩` / `⟨pre-speech Ns⟩` markers and a `| Silence: ...` field. Read them as hesitation signals; when present, acknowledge and offer help.*

- [ ] **Step 3: Re-run scenarios WITH guidance; confirm compliance. REFACTOR any loophole.**

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/converse/SKILL.md skills/voicemode/SKILL.md
git commit -m "docs(skill): guide silence_release_sec trigger + hesitation-marker response"
```

---

### Task 10: Docs — parameter reference + changelog

**Files:**
- Modify: `docs/reference/converse-parameters.md`, `CHANGELOG.md` (Unreleased)
- Test: `uv run pytest tests/ -v --tb=short` (full suite green)

- [ ] **Step 1: Document `silence_release_sec`**

Add to `docs/reference/converse-parameters.md` (near `disable_silence_detection`): the value table (0/N/-1), the 180s/300s listen bounds, and the `Silence:`/marker output description. Mark `disable_silence_detection` as deprecated alias for `-1`.

- [ ] **Step 2: Changelog entry**

Add under `## [Unreleased]` → `### Added`:

```markdown
- Explicit turn handoff: `silence_release_sec` scalar lets the assistant keep the floor through hesitation (0 = current VAD, N = tolerate N seconds, -1 = never; `disable_silence_detection` becomes an alias for -1). `listen_duration_max` default raised to 180s, hard-capped at 300s.
- Silence observability: every turn reports a silence profile; pauses ≥2s appear as inline `⟨pause Ns⟩` / `⟨pre-speech Ns⟩` transcript markers and a `Silence:` result field so the assistant can respond to hesitation.
```

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: PASS (all green).

- [ ] **Step 4: Commit**

```bash
git add docs/reference/converse-parameters.md CHANGELOG.md
git commit -m "docs: silence_release_sec + silence observability reference and changelog"
```

---

## Self-Review

1. Spec coverage: ✅ — every spec section and AC 1–10 maps to a task (scalar semantics → T4/5/6, alias → T6, listen bounds → T1/6, profile metrics → T2/4, threshold → T1/3, markers → T3/8, conditional word timestamps → T7, result formatting → T8, SKILL RGR → T9, docs → T10).
2. Placeholder scan: ✅ — no TBD/TODO; Task 7's (a)/(b) are complete alternative implementations keyed to existing plumbing, not placeholders.
3. Type consistency: ✅ — 3-tuple return, `SilenceProfile` fields/methods, and all helper signatures match across defining and consuming tasks.
