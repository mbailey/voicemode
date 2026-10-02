"""ElevenLabs STT provider for voice-mode.

Posts audio to ``POST /v1/speech-to-text`` with ``xi-api-key`` auth and
returns the transcription text. Mirrors the pattern of elevenlabs_tts.py.

ElevenLabs STT diverges from the OpenAI Whisper path:
  - Endpoint: ``/v1/speech-to-text`` (not ``/v1/audio/transcriptions``)
  - Auth: ``xi-api-key`` header
  - Response: JSON with a ``text`` field
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from . import config

logger = logging.getLogger("voicemode")

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabsSTTError(RuntimeError):
    """Raised when ElevenLabs STT returns a non-2xx response."""


async def transcribe(
    audio_data: bytes,
    filename: str = "audio.mp3",
    model: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """Transcribe audio bytes via ElevenLabs and return the transcript text.

    Args:
        audio_data: Raw audio bytes to transcribe.
        filename: Filename hint for the multipart upload (affects MIME detection).
        model: Model ID to use (defaults to ``config.ELEVENLABS_STT_MODEL``).
        language: Optional ISO-639-1 language code (omit for auto-detect).

    Returns:
        Transcribed text string.

    Raises:
        ElevenLabsSTTError: On API errors or missing credentials.
    """
    api_key = config.ELEVENLABS_API_KEY
    if not api_key:
        raise ElevenLabsSTTError("ELEVENLABS_API_KEY is not set")

    model_id = model or config.ELEVENLABS_STT_MODEL

    headers = {"xi-api-key": api_key}
    data: dict = {"model_id": model_id}
    if language and language != "auto":
        data["language_code"] = language

    files = {"file": (filename, audio_data)}

    logger.debug(f"ElevenLabs STT request: model={model_id}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            _STT_URL,
            headers=headers,
            data=data,
            files=files,
        )

    if resp.status_code == 200:
        result = resp.json()
        text = result.get("text", "")
        logger.debug(f"ElevenLabs STT response: {text[:100]}")
        return text

    raise ElevenLabsSTTError(
        f"ElevenLabs STT failed: {resp.status_code} {resp.text[:500]}"
    )
