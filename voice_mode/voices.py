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
# `ballad` and `verse` were added with gpt-4o-mini-tts (Sep 2024); the original
# six (alloy/echo/fable/nova/onyx/shimmer) work with tts-1 and tts-1-hd too.
OPENAI_TTS_VOICES = (
    "alloy", "ash", "ballad", "coral", "echo", "fable",
    "nova", "onyx", "sage", "shimmer", "verse",
)

# ElevenLabs built-in voices. Source: https://elevenlabs.io/docs/voices
# ElevenLabs does NOT expose /audio/voices, so this list is hand-maintained.
# ``voice`` is the ID passed to the API path; ``name`` is the display label.
# Both IDs and display names are accepted by the ElevenLabs API.
#
# Only voices confirmed free-tier accessible are listed (verified 2026-10-02).
# Paid/library-only voices (HTTP 402 on free accounts) are excluded:
#   Aria (9BWtsMINqrJLrRacOk9x), Charlotte (XB0fDUnXU5powFXDhCwa),
#   Rachel (21m00Tcm4TlvDq8ikWAM).
# Voice availability is account and tier-dependent — users must set
# VOICEMODE_ELEVENLABS_VOICE_ID explicitly.
ELEVENLABS_TTS_VOICES: tuple[tuple[str, str], ...] = (
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice"),       # female, British, confident, news
    ("pqHfZKP75CvOlQylNhV4", "Bill"),         # male, American, trustworthy, narration
    ("nPczCjzI2devNBz1zQrb", "Brian"),        # male, American, deep, narration
    ("N2lVS1w4EtoT3dr4eOWO",  "Callum"),     # male, Transatlantic, intense, characters
    ("IKne3meq5aSn9XLyUdCD",  "Charlie"),    # male, Australian, natural, conversational
    ("iP95p4xoKVk53GoZ742B",  "Chris"),      # male, American, casual, conversational
    ("onwK4e9ZLuTAKqWW03F9",  "Daniel"),     # male, British, authoritative, news
    ("cjVigY5qzO86Huf0OWal",  "Eric"),       # male, American, friendly, conversational
    ("JBFqnCBsd6RMkjVDRZzb",  "George"),     # male, British, warm, narration
    ("cgSgspJ2msm6clMCkdW9",  "Jessica"),    # female, American, expressive, conversational
    ("FGY2WhTYpPnrIDTdsKH5",  "Laura"),      # female, American, upbeat, social media
    ("TX3LPaxmHKxFdv7VOQHJ",  "Liam"),       # male, American, articulate, narration
    ("pFZP5JQG7iQjIQuC4Bku",  "Lily"),       # female, British, warm, narration
    ("XrExE9yKIg1WjnnlVkGX",  "Matilda"),    # female, American, friendly, narration
    ("SAz9YHcvj6GT2YYXdXww",  "River"),      # non-binary, American, confident, social media
    ("CwhRBWXzGAHq8TQ4Fs17",  "Roger"),      # male, American, confident, social media
    ("EXAVITQu4vr4xnSDxMaL",  "Sarah"),      # female, American, soft, news
    ("bIHbv24MWmeRgasZH58o",  "Will"),       # male, American, friendly, social media
)


_CACHE_TTL = 60.0
_PROBE_TIMEOUT = 5.0  # seconds; matches provider_discovery.py probe timeouts
_IMPRESSION_PROVIDER = "mlx-audio"

# Cache keyed by include_local_only → (monotonic timestamp, voice list).
_cache: dict[bool, tuple[float, list[dict[str, Any]]]] = {}


def _make_entry(provider: str, voice: str, name: str | None = None) -> dict[str, Any]:
    """Build a voice entry matching the locked v1 schema."""
    return {
        "id": f"{provider}:{voice}",
        "voice": voice,
        "name": name or voice,
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
    if provider == "elevenlabs":
        # ElevenLabs does not expose /audio/voices. Return None here —
        # enumerate_voices() injects ElevenLabs entries via _elevenlabs_entries()
        # so they carry both the voice ID and display name.
        return None

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


def _elevenlabs_entries() -> list[dict[str, Any]]:
    """Build ElevenLabs voice entries when api.elevenlabs.io is configured.

    Merges the built-in catalogue (ELEVENLABS_TTS_VOICES) with any voices
    configured in VOICEMODE_VOICES / VOICEMODE_ELEVENLABS_VOICE_ID so
    user-configured voices always appear even if not in the built-in list.
    ``voice`` carries the ID (passed to the API path); ``name`` is the
    display label.
    """
    from .config import TTS_VOICES, ELEVENLABS_VOICE_ID

    # Check if any TTS_BASE_URL is an ElevenLabs endpoint
    if not any(detect_provider_type(u) == "elevenlabs" for u in TTS_BASE_URLS):
        return []

    # Build id→name map from built-ins
    # Collect all voice IDs to include: built-ins + user-configured
    all_voices: list[tuple[str, str]] = list(ELEVENLABS_TTS_VOICES)
    seen_ids = {vid for vid, _ in ELEVENLABS_TTS_VOICES}

    # Add VOICEMODE_ELEVENLABS_VOICE_ID if set and not already present
    if ELEVENLABS_VOICE_ID and ELEVENLABS_VOICE_ID not in seen_ids:
        all_voices.insert(0, (ELEVENLABS_VOICE_ID, ELEVENLABS_VOICE_ID))
        seen_ids.add(ELEVENLABS_VOICE_ID)

    # Add any VOICEMODE_VOICES entries that look like ElevenLabs (names or IDs)
    for v in TTS_VOICES:
        if v not in seen_ids:
            # Could be a display name or an unknown ID — include it either way
            all_voices.append((v, v))
            seen_ids.add(v)

    return [
        _make_entry("elevenlabs", voice_id, name)
        for voice_id, name in all_voices
    ]


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

    # ElevenLabs has no /audio/voices endpoint — inject from built-in catalogue
    # + user-configured voices. Done before impressions so a cloned voice can
    # override a built-in entry with the same id if they ever collide.
    for entry in _elevenlabs_entries():
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
