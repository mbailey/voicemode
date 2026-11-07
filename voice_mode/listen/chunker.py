"""Cut speech into chunks for partial transcription.

A chunk opens on a speech frame (with a little pre-roll so the first
phoneme is not clipped) and is cut when a short quiet follows it
(``quiet_s``; kin's ``calls.py`` uses 0.35 s) or when it reaches
``max_s``, so a long unbroken utterance still yields partials while it
goes on. Chunks with too little speech in them (a click) are dropped
rather than sent to STT.

The max cut is SOFT (VM-2274 do-007): when a chunk reaches ``max_s`` it
is cut at the quietest frame (lowest RMS) in its last ``cut_window_s``,
not at the hard edge, and the frames after that point open the next
chunk. A 2 s max puts the first partial about 2 s after onset, while the
speaker is still talking, and the quietest-frame cut usually lands between
words instead of through one. No audio is dropped or sent twice: the
chunks still tile the utterance, so partials stay CHUNKS under the heard
contract.
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
        max_s: float = 2.0,
        preroll_s: float = 0.15,
        min_speech_s: float = 0.12,
        cut_window_s: float = 0.4,
    ) -> None:
        self.quiet_s = quiet_s  # read by the loop: the turn re-decode launches on this quiet (do-008)
        self._quiet_frames = max(1, int(round(quiet_s / FRAME_S)))
        self._max_frames = max(1, int(round(max_s / FRAME_S)))
        self._min_speech_frames = max(1, int(round(min_speech_s / FRAME_S)))
        self._preroll: deque = deque(maxlen=max(0, int(round(preroll_s / FRAME_S))))
        self._window_frames = max(1, int(round(cut_window_s / FRAME_S)))
        self._frames: list = []
        self._flags: list = []  # speech verdict per frame, parallel to _frames
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
            self._flags = [False] * len(self._frames)
            self._preroll.clear()
            self._t0 = t - len(self._frames) * FRAME_S
            self._speech = 0
            self._quiet = 0
        self._frames.append(frame)
        self._flags.append(bool(speech))
        if speech:
            self._speech += 1
            self._quiet = 0
        else:
            self._quiet += 1
        if self._quiet >= self._quiet_frames:
            return self._cut(t + FRAME_S)
        if len(self._frames) >= self._max_frames:
            return self._soft_cut()
        return None

    def _soft_cut(self) -> Optional[Chunk]:
        """Cut at the quietest frame of the last window; carry the rest over."""
        n = len(self._frames)
        lo = max(1, n - self._window_frames)
        rms = [float(np.sqrt(np.mean(np.square(self._frames[i].astype(np.float64)))))
               for i in range(lo, n)]
        k = lo + int(np.argmin(rms))            # cut AFTER frame k
        rest, rest_flags = self._frames[k + 1:], self._flags[k + 1:]
        t_cut = self._t0 + (k + 1) * FRAME_S
        self._frames, self._flags = self._frames[: k + 1], self._flags[: k + 1]
        self._speech = sum(self._flags)
        chunk = self._cut(t_cut)
        if rest:                                 # the next chunk opens with the carried frames
            self._frames, self._flags = rest, rest_flags
            self._t0 = t_cut
            self._speech = sum(rest_flags)
            self._quiet = 0
            for f in reversed(rest_flags):
                if f:
                    break
                self._quiet += 1
        return chunk

    def flush(self, t: float) -> Optional[Chunk]:
        """Cut whatever is open (end of turn, end of listen)."""
        return self._cut(t) if self._frames else None

    def _cut(self, t_end: float) -> Optional[Chunk]:
        frames, speech = self._frames, self._speech
        self._frames = []
        self._flags = []
        self._speech = 0
        self._quiet = 0
        if speech < self._min_speech_frames:
            return None
        return Chunk(audio=np.concatenate(frames), t0=self._t0, t1=t_end)
