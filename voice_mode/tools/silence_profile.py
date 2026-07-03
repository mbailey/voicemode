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
