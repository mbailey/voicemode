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

    has_gap = bool(profile.significant_gaps(threshold))
    has_pre = profile.pre_speech_significant(threshold)
    if not has_gap and not has_pre:
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
