"""Silero VAD as the frame classifier (spec task 3.4, VM-2274 do-009).

It slots into :class:`~voice_mode.listen.detector.SilenceTurnDetector` as the
``classifier``: the SAME end-of-turn rule (a turn opens on a short run of
speech, ends after ``silence_s`` of non-speech), with the speech/non-speech
call made by Silero instead of webrtcvad. webrtcvad at aggressiveness 3 calls
many non-speech sounds speech, and whisper then hallucinates words into them
("Bye.", "Mmm."): M4's false turns in a silent room. Silero is trained to tell
speech from noise.

The model is Silero VAD v5 as ONNX (MIT). It needs ``onnxruntime`` and the
``silero_vad.onnx`` file; neither is a VoiceMode dependency, so this is
opt-in: ``--detector silero`` with ``VOICEMODE_SILERO_MODEL`` (or
``--silero-model``) naming the file. Nothing here is imported unless asked for.

Framing: Silero v5 at 16 kHz takes 512-sample windows with the previous
window's last 64 samples as context. The loop's frames are 30 ms (480
samples), so frames are rebuffered; each frame is classified by the most
recent window's probability (at most one 32 ms window behind). Hysteresis as
in Silero's own ``get_speech_timestamps``: speech starts at ``threshold``, and
once on, stays on until the probability falls below ``threshold - 0.15``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

from .sources import SAMPLE_RATE

WINDOW = 512  # samples per Silero call at 16 kHz
CONTEXT = 64  # samples of the previous window prepended (Silero v5)
DEFAULT_THRESHOLD = 0.5
MODEL_ENV = "VOICEMODE_SILERO_MODEL"


class SileroError(RuntimeError):
    pass


def model_path(explicit: Optional[str] = None) -> Path:
    raw = explicit or os.environ.get(MODEL_ENV)
    if not raw:
        raise SileroError(f"Silero VAD needs its model file: pass --silero-model PATH or set {MODEL_ENV} (silero_vad.onnx, v5)")
    p = Path(raw).expanduser()
    if not p.is_file():
        raise SileroError(f"Silero model not found: {p}")
    return p


class SileroClassifier:
    """``classify(frame) -> bool`` backed by Silero VAD v5 (onnxruntime)."""

    name = "silero"

    def __init__(self, model: Optional[str] = None, *, threshold: float = DEFAULT_THRESHOLD, session=None) -> None:
        if session is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise SileroError("Silero VAD needs onnxruntime (pip install onnxruntime)") from exc
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            session = ort.InferenceSession(str(model_path(model)), sess_options=opts, providers=["CPUExecutionProvider"])
        self._session = session
        self.threshold = threshold
        self.off_threshold = max(0.0, threshold - 0.15)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)
        self._buf = np.zeros(0, dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self.prob = 0.0  # the latest window's speech probability
        self._on = False

    def _window(self, x: np.ndarray) -> float:
        inp = np.concatenate([self._context, x])[None, :]
        out, self._state = self._session.run(None, {"input": inp, "state": self._state, "sr": self._sr})
        self._context = x[-CONTEXT:]
        return float(out[0][0])

    def __call__(self, frame: np.ndarray) -> bool:
        self._buf = np.concatenate([self._buf, frame.astype(np.float32) / 32768.0])
        while len(self._buf) >= WINDOW:
            self.prob = self._window(self._buf[:WINDOW])
            self._buf = self._buf[WINDOW:]
        if self._on:
            self._on = self.prob >= self.off_threshold
        else:
            self._on = self.prob >= self.threshold
        return self._on
