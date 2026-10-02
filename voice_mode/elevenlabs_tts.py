"""ElevenLabs TTS provider for voice-mode.

Provides two entry points against the ElevenLabs HTTP API, following the
Cartesia adapter pattern (cartesia_tts.py):

* :func:`synthesize` — POST to ``/v1/text-to-speech/{voice_id}`` and return
  the full audio bytes for the buffered playback path.
* :func:`stream` — async generator over ``/v1/text-to-speech/{voice_id}/stream``
  that yields raw audio bytes as ElevenLabs produces them (plain chunked HTTP,
  no SSE framing required).

Both paths try ``config.ELEVENLABS_MODEL`` first and fall back to
``config.ELEVENLABS_FALLBACK_MODEL`` if ElevenLabs rejects the model.

ElevenLabs API diverges from OpenAI at every layer:
  - Auth: ``xi-api-key`` header (not ``Authorization: Bearer``)
  - Voice: URL path parameter (not a body field)
  - Body fields: ``text`` / ``model_id`` (not ``input`` / ``model``)
  - Format: ``output_format`` query parameter (not a body field)
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional, Tuple

import httpx

from . import config

logger = logging.getLogger("voicemode")

_BASE = "https://api.elevenlabs.io"

# Maps VoiceMode output format names to ElevenLabs output_format query values.
# pcm_44100 requires ElevenLabs Pro tier; default to pcm_24000 on the PCM path.
_OUTPUT_FORMAT_MAP = {
    "mp3": "mp3_44100_128",
    "mp3_44100_128": "mp3_44100_128",
    "mp3_44100_64": "mp3_44100_64",
    "pcm": "pcm_24000",
    "pcm_16000": "pcm_16000",
    "pcm_22050": "pcm_22050",
    "pcm_24000": "pcm_24000",
    "pcm_44100": "pcm_44100",
    "opus": "opus_48000_32",
    "ulaw": "ulaw_8000",
}
_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class ElevenLabsError(RuntimeError):
    """Raised when ElevenLabs returns a non-2xx response we cannot recover from."""


def _resolve_request(
    voice_id: Optional[str],
    model: Optional[str],
) -> Tuple[str, str, str, List[str]]:
    """Return ``(api_key, voice_id, primary_model, models_to_try)``.

    Raises :class:`ElevenLabsError` if the API key or voice id is missing.
    """
    api_key = config.ELEVENLABS_API_KEY
    if not api_key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not set")

    voice = voice_id or config.ELEVENLABS_VOICE_ID
    if not voice:
        raise ElevenLabsError(
            "No ElevenLabs voice ID available. "
            "Set VOICEMODE_ELEVENLABS_VOICE_ID to a 20-character ElevenLabs voice ID, "
            "or include one in VOICEMODE_VOICES (e.g. 21m00Tcm4TlvDq8ikWAM)."
        )

    # Validate voice is a 20-char alphanumeric ElevenLabs ID, not a Kokoro/OpenAI voice name
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9]{20}", voice):
        raise ElevenLabsError(
            f"'{voice}' is not a valid ElevenLabs voice ID (expected 20-char alphanumeric). "
            f"Set VOICEMODE_ELEVENLABS_VOICE_ID to your ElevenLabs voice ID "
            f"(e.g. 21m00Tcm4TlvDq8ikWAM for Rachel)."
        )

    primary = model or config.ELEVENLABS_MODEL
    fallback = config.ELEVENLABS_FALLBACK_MODEL
    models_to_try = [primary, fallback] if primary != fallback else [primary]
    return api_key, voice, primary, models_to_try


def _map_output_format(output_format: Optional[str]) -> str:
    """Map a VoiceMode output format string to an ElevenLabs output_format value."""
    if not output_format:
        return _DEFAULT_OUTPUT_FORMAT
    return _OUTPUT_FORMAT_MAP.get(output_format.lower(), _DEFAULT_OUTPUT_FORMAT)


def _clamp_speed(speed: Optional[float]) -> Optional[float]:
    """Clamp speed to ElevenLabs valid range [0.7, 1.2]."""
    if speed is None:
        return None
    clamped = max(0.7, min(1.2, speed))
    if clamped != speed:
        logger.debug(f"ElevenLabs: clamped speed {speed} → {clamped}")
    return clamped


def _is_model_error(status_code: int, body_text: str) -> bool:
    return status_code in (400, 404, 422) and "model" in body_text.lower()


async def synthesize(
    text: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    output_format: Optional[str] = "mp3",
    speed: Optional[float] = None,
) -> bytes:
    """Synthesize ``text`` via ElevenLabs and return audio bytes.

    Tries ``config.ELEVENLABS_MODEL`` first; on a 4xx that mentions the model,
    retries with ``config.ELEVENLABS_FALLBACK_MODEL``.
    """
    api_key, voice, _, models_to_try = _resolve_request(voice_id, model)
    el_format = _map_output_format(output_format)
    fallback_model = models_to_try[-1]

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt_model in models_to_try:
            url = f"{_BASE}/v1/text-to-speech/{voice}"
            body: dict = {"text": text, "model_id": attempt_model}
            if speed is not None:
                body["voice_settings"] = {"speed": _clamp_speed(speed)}

            logger.debug(f"ElevenLabs TTS request: model={attempt_model} voice={voice}")
            resp = await client.post(
                url,
                headers=headers,
                json=body,
                params={"output_format": el_format},
            )
            if resp.status_code == 200:
                return resp.content

            body_text = resp.text[:500]
            if _is_model_error(resp.status_code, body_text) and attempt_model != fallback_model:
                logger.warning(
                    f"ElevenLabs rejected model {attempt_model} "
                    f"({resp.status_code}); retrying with {fallback_model}"
                )
                continue
            raise ElevenLabsError(
                f"ElevenLabs TTS failed: {resp.status_code} {body_text}"
            )

    raise ElevenLabsError("ElevenLabs TTS exhausted both primary and fallback models")


async def stream(
    text: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    output_format: Optional[str] = "mp3",
    speed: Optional[float] = None,
) -> AsyncIterator[bytes]:
    """Stream audio bytes from ElevenLabs' chunked streaming endpoint.

    Yields chunks as they arrive so the caller can play them progressively.
    ElevenLabs /stream returns plain chunked HTTP audio — no SSE framing or
    base64 decoding needed (unlike Cartesia).
    """
    api_key, voice, _, models_to_try = _resolve_request(voice_id, model)
    el_format = _map_output_format(output_format)
    fallback_model = models_to_try[-1]

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt_model in models_to_try:
            url = f"{_BASE}/v1/text-to-speech/{voice}/stream"
            body: dict = {"text": text, "model_id": attempt_model}
            if speed is not None:
                body["voice_settings"] = {"speed": _clamp_speed(speed)}

            logger.debug(
                f"ElevenLabs stream request: model={attempt_model} voice={voice}"
            )
            try:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=body,
                    params={"output_format": el_format},
                ) as resp:
                    if resp.status_code != 200:
                        body_text = (await resp.aread()).decode(
                            "utf-8", errors="replace"
                        )[:500]
                        if (
                            _is_model_error(resp.status_code, body_text)
                            and attempt_model != fallback_model
                        ):
                            logger.warning(
                                f"ElevenLabs rejected model {attempt_model} "
                                f"({resp.status_code}); retrying with {fallback_model}"
                            )
                            continue
                        raise ElevenLabsError(
                            f"ElevenLabs stream failed: {resp.status_code} {body_text}"
                        )

                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk
                    return
            except ElevenLabsError:
                raise
            except httpx.HTTPError as exc:
                raise ElevenLabsError(
                    f"ElevenLabs stream transport error: {exc}"
                ) from exc

    raise ElevenLabsError(
        "ElevenLabs stream exhausted both primary and fallback models"
    )
