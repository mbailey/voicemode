"""Diagnostic tools for voice-mode."""

import os
from voice_mode.server import mcp
from voice_mode.version import __version__
from voice_mode.config import TTS_VOICES, TTS_BASE_URLS, TTS_MODELS
from voice_mode.provider_discovery import provider_registry
import logging

logger = logging.getLogger("voicemode")


@mcp.tool()
async def voice_mode_info() -> str:
    """Get diagnostic information about the voice-mode installation.
    
    Shows version, configuration, and provider status to help debug issues.
    """
    info = []
    info.append(f"Voice Mode Diagnostics")
    info.append(f"====================")
    info.append(f"Version: {__version__}")
    info.append(f"Working Directory: {os.getcwd()}")
    info.append(f"Python Executable: {os.sys.executable}")
    
    info.append(f"\nConfiguration:")
    info.append(f"  TTS_VOICES: {TTS_VOICES}")
    info.append(f"  TTS_BASE_URLS: {TTS_BASE_URLS}")
    info.append(f"  TTS_MODELS: {TTS_MODELS}")
    
    info.append(f"\nProvider Registry:")
    await provider_registry.initialize()
    
    for service_type in ["tts", "stt"]:
        info.append(f"\n{service_type.upper()} Endpoints:")
        for url, endpoint in provider_registry.registry[service_type].items():
            # Show status based on whether endpoint has an error
            status = "❌" if endpoint.last_error else "✅"
            info.append(f"  {status} {url} ({endpoint.provider_type})")
            if service_type == "tts" and endpoint.voices:
                info.append(f"     Voices: {', '.join(endpoint.voices[:3])}...")
    
    # Check which provider would be selected
    try:
        from voice_mode.providers import get_tts_client_and_voice
        client, voice, model, endpoint = await get_tts_client_and_voice()
        info.append(f"\nDefault TTS Selection:")
        info.append(f"  Provider: {endpoint.provider_type}")
        info.append(f"  URL: {endpoint.base_url}")
        info.append(f"  Voice: {voice}")
        info.append(f"  Model: {model}")
    except Exception as e:
        info.append(f"\nError getting default TTS: {e}")
    
    return "\n".join(info)