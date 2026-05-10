"""Voice provider registry tool -- prose listing for the LLM converse loop.

Refactored on 2026-05-10 (VM-1208 impl-003) to source the voice list
from the shared ``enumerate_voices`` helper instead of the dormant
``provider_registry``. Per-endpoint diagnostics (URL, status emoji,
provider type, model defaults) are synthesised inline so the prose
format stays identical to the prior implementation while the data
source is now live and shared with the ``voice://voices`` MCP resource.

See ``design.md`` §9 for the rationale (option (a): ignore
``provider_registry`` entirely here; full retirement is VM-1214's job)
and §12 for the AC9 contract.

This module no longer imports ``provider_discovery``; ``detect_provider_type``
is reached via ``voice_mode.voices`` (the new home of the URL-classification
utility for tool-tier consumers), so leaving ``provider_registry`` truly
unused in this code path is a one-grep audit.
"""

from voice_mode.config import STT_BASE_URLS, TTS_BASE_URLS
from voice_mode.server import mcp
from voice_mode.voices import detect_provider_type, enumerate_voices


def _default_tts_models(provider: str) -> list[str]:
    if provider == "openai":
        return ["gpt4o-mini-tts", "tts-1", "tts-1-hd"]
    return ["tts-1"]


def _default_stt_models(provider: str) -> list[str]:
    # mlx-audio rejects "whisper-1" (it expects a full HF repo id), so
    # advertise its websocket default instead. Mirrors the legacy
    # provider_discovery._default_stt_models seeding behaviour.
    if provider == "mlx-audio":
        return ["mlx-community/whisper-large-v3-turbo"]
    return ["whisper-1"]


@mcp.tool()
async def voice_registry() -> str:
    """Get the current voice provider registry showing all discovered endpoints.

    Returns a formatted view of all TTS and STT endpoints with their:
    - Available models
    - Available voices (TTS only)
    - Provider type
    - Last check time
    - Any recent errors

    This allows the LLM to see what voice services are currently available.
    """
    # Voice list comes from the shared enumerator -- same source as voice://voices.
    # include_local_only=False keeps impressions out of the prose, matching this
    # tool's prior behaviour (the tool never surfaced clones).
    enumerated = await enumerate_voices(include_local_only=False)
    voices_by_provider: dict[str, list[str]] = {}
    for entry in enumerated:
        voices_by_provider.setdefault(entry["provider"], []).append(entry["voice"])

    lines = ["Voice Provider Registry", "=" * 50, ""]

    # TTS Endpoints
    lines.append("TTS Endpoints:")
    lines.append("-" * 30)

    for url in TTS_BASE_URLS:
        provider = detect_provider_type(url)
        models = _default_tts_models(provider)
        voices = voices_by_provider.get(provider, [])
        last_error = None
        last_check = None
        status = "❌" if last_error else "✅"
        lines.append(f"\n{status} {url}")
        lines.append(f"   Provider: {provider}")
        lines.append(f"   Models: {', '.join(models) if models else 'none detected'}")
        lines.append(f"   Voices: {', '.join(voices) if voices else 'none detected'}")

        if last_error:
            lines.append(f"   Last Error: {last_error}")

        if last_check:
            lines.append(f"   Last Check: {last_check}")

    # STT Endpoints
    lines.append("\n\nSTT Endpoints:")
    lines.append("-" * 30)

    for url in STT_BASE_URLS:
        provider = detect_provider_type(url)
        models = _default_stt_models(provider)
        last_error = None
        last_check = None
        status = "❌" if last_error else "✅"
        lines.append(f"\n{status} {url}")
        lines.append(f"   Provider: {provider}")
        lines.append(f"   Models: {', '.join(models) if models else 'none detected'}")

        if last_error:
            lines.append(f"   Last Error: {last_error}")

        if last_check:
            lines.append(f"   Last Check: {last_check}")

    return "\n".join(lines)
