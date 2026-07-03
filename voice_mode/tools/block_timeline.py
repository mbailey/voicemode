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
