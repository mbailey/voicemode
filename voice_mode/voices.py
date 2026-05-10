"""Voice enumeration for the ``voice://voices`` MCP resource.

Single source of truth for the TTS voices VoiceMode advertises. The
resource handler (``voice_mode/resources/voices.py``) and the
``voice_registry`` tool both call ``enumerate_voices`` so the prose tool
and the JSON resource never drift on the actual voice list.

See ``design.md`` at the task root for the full design rationale —
sources (§3), freshness (§4), failure semantics (§5), dedup rule (§6),
ordering (§7).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .config import TTS_BASE_URLS
from .provider_discovery import detect_provider_type
from .voice_profiles import list_profiles

logger = logging.getLogger("voicemode")

# OpenAI TTS voices. Source: https://platform.openai.com/docs/guides/text-to-speech
# OpenAI does NOT expose /audio/voices, so this list is hand-maintained.
# Last verified: 2026-05-10. Update when OpenAI ships a new voice.
OPENAI_TTS_VOICES = (
    "alloy", "ash", "coral", "echo", "fable",
    "nova", "onyx", "sage", "shimmer",
)

_PROBE_TIMEOUT = 5.0
_CACHE_TTL = 60.0
_IMPRESSION_PROVIDER = "mlx-audio"

# Cache keyed by include_local_only → (monotonic timestamp, voice list).
_cache: dict[bool, tuple[float, list[dict[str, Any]]]] = {}


def _make_entry(provider: str, voice: str) -> dict[str, Any]:
    """Build a voice entry matching the locked v1 schema."""
    return {
        "id": f"{provider}:{voice}",
        "voice": voice,
        "name": voice,
        "provider": provider,
        "language": None,
        "gender": None,
        "preview_url": None,
    }


async def _fetch_audio_voices(url: str) -> list[str]:
    """``GET {url}/audio/voices`` and extract voice names.

    Accepts both response shapes seen in the wild: a bare ``[...]`` list
    and a ``{"voices": [...]}`` wrapper. List items may be plain strings
    or ``{"id": ...}`` objects. Malformed individual items are dropped
    silently — one bad row should not fail the whole probe.
    """
    endpoint = f"{url.rstrip('/')}/audio/voices"
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
        response = await client.get(endpoint)
        response.raise_for_status()
        data = response.json()

    if isinstance(data, dict) and "voices" in data:
        items = data["voices"]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError(
            f"unexpected /audio/voices shape from {endpoint}: "
            f"{type(data).__name__}"
        )

    voices: list[str] = []
    for item in items:
        if isinstance(item, str):
            voices.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            voices.append(item["id"])
    return voices


async def _voices_for_endpoint(url: str) -> tuple[str, list[str]] | None:
    """Resolve ``(provider, voices)`` for a single ``TTS_BASE_URL``.

    Returns ``None`` when the endpoint should not contribute (whisper
    STT-only, or probe failure). Failures log at WARNING for recoverable
    cases (connect, timeout, HTTP 4xx/5xx) and ERROR for malformed JSON
    or unexpected exception types.
    """
    provider = detect_provider_type(url)
    if provider == "whisper":
        return None
    if provider == "openai":
        return provider, list(OPENAI_TTS_VOICES)

    try:
        voices = await _fetch_audio_voices(url)
    except httpx.ConnectError as exc:
        logger.warning("voice probe failed (connect) for %s: %s", url, exc)
        return None
    except httpx.TimeoutException as exc:
        logger.warning("voice probe failed (timeout) for %s: %s", url, exc)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "voice probe failed (HTTP %d) for %s",
            exc.response.status_code, url,
        )
        return None
    except (ValueError, TypeError) as exc:
        logger.error("voice probe returned malformed JSON from %s: %s", url, exc)
        return None
    except Exception as exc:  # noqa: BLE001 — silent-skip with log per design §5
        logger.error(
            "voice probe failed (%s) for %s: %s",
            type(exc).__name__, url, exc,
        )
        return None

    return provider, voices


def _impression_entries() -> list[dict[str, Any]]:
    """Materialise impression voices from ``voice_profiles.list_profiles``."""
    try:
        profiles = list_profiles()
    except Exception as exc:  # noqa: BLE001 — never let this break enumeration
        logger.error("voice_profiles.list_profiles() failed: %s", exc)
        return []
    return [
        _make_entry(_IMPRESSION_PROVIDER, name)
        for name in sorted(profiles, key=str.casefold)
    ]


async def enumerate_voices(*, include_local_only: bool) -> list[dict[str, Any]]:
    """Return TTS voices the server can produce, as schema-shaped dicts.

    Parameters
    ----------
    include_local_only:
        When True, append local impressions/clones from ``VOICES_DIR``
        (the stdio default). When False, omit them — the safe default
        for remote streamable HTTP clients (AC8).

    Returns
    -------
    A fresh shallow copy of the cached voice list. Mutating the returned
    list does not affect future calls. The TTL cache (60 s) is keyed
    independently per ``include_local_only`` value.
    """
    now = time.monotonic()
    cached = _cache.get(include_local_only)
    if cached is not None and (now - cached[0]) < _CACHE_TTL:
        return list(cached[1])

    probes = [_voices_for_endpoint(url) for url in TTS_BASE_URLS]
    results = await asyncio.gather(*probes) if probes else []

    merged: dict[str, dict[str, Any]] = {}
    for result in results:
        if result is None:
            continue
        provider, voices = result
        for voice in sorted(voices, key=str.casefold):
            entry = _make_entry(provider, voice)
            merged[entry["id"]] = entry

    if include_local_only:
        for entry in _impression_entries():
            existing = merged.pop(entry["id"], None)
            if existing is not None:
                logger.debug(
                    "voice id collision %s: impression replaces %s entry",
                    entry["id"], existing["provider"],
                )
            merged[entry["id"]] = entry

    voices_list = list(merged.values())
    _cache[include_local_only] = (now, voices_list)
    return list(voices_list)


def _reset_cache() -> None:
    """Test seam — clear the in-process voice cache."""
    _cache.clear()
