"""Optional end-of-turn detection with Smart Turn v3.2 (Pipecat).

The silence timer ends a turn after ``VOICEMODE_SILENCE_THRESHOLD_MS`` of
silence. A speaker who pauses mid-sentence is cut off, and a long threshold
makes every reply slow. Smart Turn listens to how the speaker sounds at a
pause and gives the probability that the turn is over.

With ``VOICEMODE_TURN_DETECTOR=smart-turn``, converse asks the model once at
each pause of ``VOICEMODE_SMART_TURN_PAUSE_MS``. If the model says the turn
is over, recording stops at once. If not, recording continues, and the
silence threshold still ends the turn as before.

The model runs in-process on the CPU through transcribe.cpp (about 30 ms for
8 s of audio). Install it with the ``smart-turn`` extra. If the package or
the model is not available, converse logs a warning and uses the silence
timer only.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from voice_mode.config import (
    SAMPLE_RATE,
    SMART_TURN_MODEL,
    SMART_TURN_PAUSE_MS,
    SMART_TURN_THRESHOLD,
    TURN_DETECTOR,
)

logger = logging.getLogger("voicemode")

TURN_DETECTOR_SILENCE = "silence"
TURN_DETECTOR_SMART_TURN = "smart-turn"

MODEL_SAMPLE_RATE = 16000

Scorer = Callable[[np.ndarray], Tuple[float, bool]]


def resolve_model_path(spec: str) -> str:
    """Return a local path for ``spec``.

    ``spec`` is a path to a ``.gguf`` file, or ``<org>/<repo>/<file>`` on the
    Hugging Face Hub. A Hub file goes into the shared Hugging Face cache.
    """
    expanded = os.path.expanduser(spec)
    if os.path.isfile(expanded):
        return expanded
    parts = spec.split("/")
    if len(parts) < 3:
        raise ValueError(
            f"VOICEMODE_SMART_TURN_MODEL={spec!r} is not a file and not <org>/<repo>/<file>"
        )
    from huggingface_hub import hf_hub_download

    return hf_hub_download("/".join(parts[:2]), "/".join(parts[2:]))


class SmartTurnModel:
    """A Smart Turn model on the CPU, with one turn session."""

    def __init__(self, model_path: str, threshold: Optional[float] = None) -> None:
        import transcribe_cpp

        cpu = next(d for d in transcribe_cpp.backends() if d.device_type == "cpu")
        self._model = transcribe_cpp.Model(model_path, device=cpu)
        self._session = self._model.turn_session()
        self._threshold = threshold
        self._lock = threading.Lock()
        # The first run builds the compute graph (about 1 s). Do it at load,
        # not at the first pause of the first turn.
        self(np.zeros(MODEL_SAMPLE_RATE, dtype=np.float32))

    def __call__(self, pcm_16k: np.ndarray) -> Tuple[float, bool]:
        kwargs = {} if self._threshold is None else {"threshold": self._threshold}
        with self._lock:
            result = self._session.run(pcm_16k, **kwargs)
        return float(result.p), bool(result.ended)


_model: Optional[SmartTurnModel] = None
_load_failed = False
_load_lock = threading.Lock()


def get_scorer() -> Optional[Scorer]:
    """Return the Smart Turn scorer, or ``None`` when it is off or cannot load.

    The model loads once per process. A load failure is logged once, and
    converse then uses the silence timer only.
    """
    global _model, _load_failed
    if TURN_DETECTOR != TURN_DETECTOR_SMART_TURN:
        return None
    with _load_lock:
        if _model is None and not _load_failed:
            try:
                path = resolve_model_path(SMART_TURN_MODEL)
                _model = SmartTurnModel(path, SMART_TURN_THRESHOLD)
                logger.info(f"Smart Turn loaded from {path}")
            except Exception as e:
                _load_failed = True
                logger.warning(
                    f"Smart Turn is not available ({e}). Using the silence threshold only. "
                    "Install it with: uv tool install 'voice-mode[smart-turn]'"
                )
        return _model


def to_model_audio(chunks: Sequence[np.ndarray]) -> np.ndarray:
    """Join int16 chunks at ``SAMPLE_RATE`` into float32 PCM at 16 kHz."""
    from scipy import signal

    pcm = np.concatenate([np.asarray(c).reshape(-1) for c in chunks]).astype(np.float32) / 32768.0
    if SAMPLE_RATE == MODEL_SAMPLE_RATE:
        return pcm
    gcd = np.gcd(SAMPLE_RATE, MODEL_SAMPLE_RATE)
    return signal.resample_poly(pcm, MODEL_SAMPLE_RATE // gcd, SAMPLE_RATE // gcd).astype(np.float32)


class TurnGate:
    """Ask the scorer once per pause whether the speaker has finished.

    Call ``on_speech()`` for each speech frame. Call ``turn_ended()`` for each
    silent frame. It scores the turn audio when the pause reaches
    ``pause_ms`` and does not score again until speech resumes. A scorer
    error turns the gate off for the rest of the recording.
    """

    def __init__(self, scorer: Scorer, pause_ms: int = SMART_TURN_PAUSE_MS) -> None:
        self._scorer = scorer
        self._pause_ms = pause_ms
        self._asked = False
        self._failed = False

    def on_speech(self) -> None:
        self._asked = False

    def turn_ended(self, silence_ms: int, turn_chunks: List[np.ndarray]) -> bool:
        if self._failed or self._asked or silence_ms < self._pause_ms or not turn_chunks:
            return False
        self._asked = True
        try:
            p, ended = self._scorer(to_model_audio(turn_chunks))
        except Exception as e:
            self._failed = True
            logger.warning(f"Smart Turn failed ({e}). Using the silence threshold only.")
            return False
        logger.info(f"Smart Turn after {silence_ms}ms pause: p={p:.2f} ended={ended}")
        return ended


def make_gate() -> Optional[TurnGate]:
    """Return a ``TurnGate`` when Smart Turn is on and loads, else ``None``."""
    scorer = get_scorer()
    return TurnGate(scorer) if scorer is not None else None
