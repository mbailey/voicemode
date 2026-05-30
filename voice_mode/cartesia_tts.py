"""Cartesia TTS provider for voice-mode.

Provides two entry points against the Cartesia HTTP API:

* :func:`synthesize` — POST to ``/tts/bytes`` and return the full WAV bytes
  for the existing buffered playback path. Used as a fallback when SSE is
  unavailable.
* :func:`stream` — async generator over ``/tts/sse`` that yields raw PCM
  ``int16`` chunks as Cartesia produces them, for low-latency playback.

Both paths try ``config.CARTESIA_MODEL`` first and fall back to
``config.CARTESIA_FALLBACK_MODEL`` if Cartesia rejects the model id.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator, List, Optional, Tuple

import httpx

from . import config

logger = logging.getLogger("voicemode")

CARTESIA_BYTES_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_SSE_URL = "https://api.cartesia.ai/tts/sse"
CARTESIA_VERSION = "2025-04-16"


class CartesiaError(RuntimeError):
    """Raised when Cartesia returns a non-2xx response we cannot recover from."""


def _resolve_request(
    voice_id: Optional[str],
    model: Optional[str],
) -> Tuple[str, str, str, List[str]]:
    """Return ``(api_key, voice_id, primary_model, models_to_try)``.

    Raises :class:`CartesiaError` if the API key or voice id is missing.
    """
    api_key = config.CARTESIA_API_KEY
    if not api_key:
        raise CartesiaError("CARTESIA_API_KEY is not set")

    voice = voice_id or config.CARTESIA_VOICE_ID
    if not voice:
        raise CartesiaError(
            "VOICEMODE_CARTESIA_VOICE_ID is not set. "
            "Pick a voice id from https://play.cartesia.ai/voices and export it."
        )

    primary = model or config.CARTESIA_MODEL
    fallback = config.CARTESIA_FALLBACK_MODEL
    models_to_try = [primary, fallback] if primary != fallback else [primary]
    return api_key, voice, primary, models_to_try


def _build_body(
    model_id: str,
    text: str,
    voice: str,
    container: str,
    sample_rate: int,
    speed: Optional[float],
) -> dict:
    body = {
        "model_id": model_id,
        "transcript": text,
        "voice": {"mode": "id", "id": voice},
        "output_format": {
            "container": container,
            "encoding": "pcm_s16le",
            "sample_rate": sample_rate,
        },
    }
    if speed is not None:
        body["speed"] = speed
    return body


def _is_model_error(status_code: int, body_text: str) -> bool:
    return status_code in (400, 404) and "model" in body_text.lower()


async def synthesize(
    text: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    sample_rate: int = 24000,
    speed: Optional[float] = None,
) -> bytes:
    """Synthesize ``text`` via Cartesia and return WAV bytes.

    Tries ``config.CARTESIA_MODEL`` first; on a 4xx that mentions the model,
    retries with ``config.CARTESIA_FALLBACK_MODEL``.
    """
    api_key, voice, _, models_to_try = _resolve_request(voice_id, model)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Cartesia-Version": CARTESIA_VERSION,
        "Content-Type": "application/json",
    }
    fallback = models_to_try[-1]

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt_model in models_to_try:
            logger.debug(f"Cartesia TTS request: model={attempt_model} voice={voice}")
            resp = await client.post(
                CARTESIA_BYTES_URL,
                headers=headers,
                json=_build_body(attempt_model, text, voice, "wav", sample_rate, speed),
            )
            if resp.status_code == 200:
                return resp.content

            body_text = resp.text[:500]
            if (
                _is_model_error(resp.status_code, body_text)
                and attempt_model != fallback
            ):
                logger.warning(
                    f"Cartesia rejected model {attempt_model} "
                    f"({resp.status_code}); retrying with {fallback}"
                )
                continue
            raise CartesiaError(f"Cartesia TTS failed: {resp.status_code} {body_text}")

    raise CartesiaError("Cartesia TTS exhausted both primary and fallback models")


async def stream(
    text: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    sample_rate: int = 24000,
    speed: Optional[float] = None,
) -> AsyncIterator[bytes]:
    """Stream raw PCM s16le bytes from Cartesia's SSE endpoint.

    Yields chunks as they arrive so the caller can play them progressively.
    On a model-related 4xx, retries the request with the fallback model.
    """
    api_key, voice, _, models_to_try = _resolve_request(voice_id, model)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Cartesia-Version": CARTESIA_VERSION,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    fallback = models_to_try[-1]

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt_model in models_to_try:
            logger.debug(f"Cartesia SSE request: model={attempt_model} voice={voice}")
            try:
                async with client.stream(
                    "POST",
                    CARTESIA_SSE_URL,
                    headers=headers,
                    json=_build_body(
                        attempt_model, text, voice, "raw", sample_rate, speed
                    ),
                ) as resp:
                    if resp.status_code != 200:
                        body_text = (await resp.aread()).decode(
                            "utf-8", errors="replace"
                        )[:500]
                        if (
                            _is_model_error(resp.status_code, body_text)
                            and attempt_model != fallback
                        ):
                            logger.warning(
                                f"Cartesia rejected model {attempt_model} "
                                f"({resp.status_code}); retrying with {fallback}"
                            )
                            continue
                        raise CartesiaError(
                            f"Cartesia SSE failed: {resp.status_code} {body_text}"
                        )

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.debug(f"Cartesia SSE non-JSON line: {payload[:120]}")
                            continue
                        data_b64 = event.get("data")
                        if data_b64:
                            yield base64.b64decode(data_b64)
                        if event.get("done"):
                            return
                    return
            except CartesiaError:
                raise
            except httpx.HTTPError as e:
                raise CartesiaError(f"Cartesia SSE transport error: {e}") from e

    raise CartesiaError("Cartesia SSE exhausted both primary and fallback models")
