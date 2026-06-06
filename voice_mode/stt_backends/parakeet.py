"""In-process Parakeet STT backend (Apple Silicon / MLX).

VoiceMode normally performs speech-to-text by POSTing audio to an
OpenAI-compatible HTTP endpoint (whisper.cpp, mlx-audio, or OpenAI cloud). This
module adds an *in-process* alternative: NVIDIA's Parakeet ASR models running
locally via `parakeet-mlx` (Apple's MLX framework), with no HTTP hop.

It is selected by listing a ``parakeet://`` URL in ``VOICEMODE_STT_BASE_URLS``
(e.g. ``parakeet://local``). On Apple Silicon this is markedly faster than the
whisper.cpp server for English while staying fully local and offline.

``parakeet-mlx`` is an optional, Apple-Silicon-only dependency (install with the
``parakeet`` extra: ``uv tool install voice-mode[parakeet]``). Its import is
deferred until first use, so VoiceMode is unaffected on other platforms; if it
is missing or fails to load, the caller's failover loop simply moves on to the
next configured STT endpoint.
"""

import asyncio
import logging
import os
import tempfile

logger = logging.getLogger("voicemode")

# Cache loaded models across calls -- loading weights costs ~20s+ on a cold
# start, so we never want to pay that per transcription. Keyed by model id so
# switching models at runtime still works.
_MODELS = {}


def _load_model(model_id: str):
    """Load (and cache) a Parakeet model.

    Raises ImportError if `parakeet-mlx` is not installed, or other exceptions
    if the model fails to load -- callers in the STT failover loop catch these
    and fall through to the next endpoint.
    """
    cached = _MODELS.get(model_id)
    if cached is not None:
        return cached
    # Deferred import: parakeet-mlx is an optional, Apple-Silicon-only extra.
    from parakeet_mlx import from_pretrained
    logger.info(f"Parakeet: loading model {model_id} (first use; downloads weights on cache miss)")
    model = from_pretrained(model_id)
    _MODELS[model_id] = model
    return model


def _transcribe_sync(audio_bytes: bytes, model_id: str) -> str:
    """Blocking transcription. Run via ``asyncio.to_thread`` from async code."""
    model = _load_model(model_id)
    # parakeet-mlx transcribes from a file path; persist the bytes to a temp wav.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        result = model.transcribe(tmp_path)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    # parakeet-mlx returns a result object exposing the transcript as `.text`.
    return (getattr(result, "text", "") or "").strip()


async def transcribe_parakeet(audio_file, model_id: str) -> str:
    """Transcribe an audio file-like object in-process with Parakeet.

    Args:
        audio_file: a seekable binary file-like object (as passed through the
            STT failover loop). Its read position is preserved.
        model_id: the Parakeet model repo id, e.g.
            ``mlx-community/parakeet-tdt-0.6b-v3``.

    Returns:
        The transcribed text (empty string if no speech was detected).
    """
    # Read the audio bytes without disturbing the caller's file position.
    start_pos = audio_file.tell()
    try:
        audio_file.seek(0)
        audio_bytes = audio_file.read()
    finally:
        audio_file.seek(start_pos)
    # Offload the blocking MLX inference so we don't stall the event loop.
    return await asyncio.to_thread(_transcribe_sync, audio_bytes, model_id)
