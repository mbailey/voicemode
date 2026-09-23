"""Cut speech into chunks for partial transcription.

A chunk opens on a speech frame (with a little pre-roll so the first
phoneme is not clipped) and is cut when a short quiet follows it
(``quiet_s``; kin's ``calls.py`` uses 0.35 s) or when it reaches
``max_s``, so a long unbroken utterance still yields partials while it
goes on. Chunks with too little speech in them (a click) are dropped
rather than sent to STT.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .sources import FRAME_S


@dataclass
class Chunk:
    audio: np.ndarray  # int16, 16 kHz mono
    t0: float  # stream seconds at the chunk's first frame (incl. pre-roll)
    t1: float  # stream seconds at the chunk's end


class Chunker:
    def __init__(
        self,
        *,
        quiet_s: float = 0.35,
        max_s: float = 5.0,
        preroll_s: float = 0.15,
        min_speech_s: float = 0.12,
    ) -> None:
        self._quiet_frames = max(1, int(round(quiet_s / FRAME_S)))
        self._max_frames = max(1, int(round(max_s / FRAME_S)))
        self._min_speech_frames = max(1, int(round(min_speech_s / FRAME_S)))
        self._preroll: deque = deque(maxlen=max(0, int(round(preroll_s / FRAME_S))))
        self._frames: list = []
        self._t0 = 0.0
        self._speech = 0
        self._quiet = 0

    @property
    def open(self) -> bool:
        return bool(self._frames)

    @property
    def start_t(self) -> Optional[float]:
        """Stream time of the open chunk's first frame (None if none is open)."""
        return self._t0 if self._frames else None

    def feed(self, frame: np.ndarray, speech: bool, t: float) -> Optional[Chunk]:
        """Feed one frame starting at stream time ``t``; return a chunk when one is cut."""
        if not self._frames:
            if not speech:
                self._preroll.append(frame)
                return None
            self._frames = list(self._preroll)
            self._preroll.clear()
            self._t0 = t - len(self._frames) * FRAME_S
            self._speech = 0
            self._quiet = 0
        self._frames.append(frame)
        if speech:
            self._speech += 1
            self._quiet = 0
        else:
            self._quiet += 1
        if self._quiet >= self._quiet_frames or len(self._frames) >= self._max_frames:
            return self._cut(t + FRAME_S)
        return None

    def flush(self, t: float) -> Optional[Chunk]:
        """Cut whatever is open (end of turn, end of listen)."""
        return self._cut(t) if self._frames else None

    def _cut(self, t_end: float) -> Optional[Chunk]:
        frames, speech = self._frames, self._speech
        self._frames = []
        self._speech = 0
        self._quiet = 0
        if speech < self._min_speech_frames:
            return None
        return Chunk(audio=np.concatenate(frames), t0=self._t0, t1=t_end)
