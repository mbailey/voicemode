"""Provider management tools for voice-mode."""

import logging
from typing import Optional, Union, Dict, Any

from voice_mode.server import mcp
from voice_mode.provider_discovery import provider_registry, detect_provider_type, _default_stt_models
from voice_mode.config import TTS_BASE_URLS, STT_BASE_URLS

logger = logging.getLogger("voicemode")


@mcp.tool()
async def refresh_provider_registry(
    service_type: Optional[str] = None,
    base_url: Optional[str] = None,
    optimistic: Union[bool, str] = True
) -> str:
    """Manually refresh health checks for voice provider endpoints.
    
    Useful when a service has been started/stopped and you want to update
    the registry without restarting the MCP server.
    
    Args:
        service_type: Optional - 'tts' or 'stt' to refresh only one type
        base_url: Optional - specific endpoint URL to refresh
        optimistic: If True, mark all endpoints as healthy without checking (default: True)
    
    Returns:
        Summary of refreshed endpoints and their status
    """
    try:
        results = ["🔄 Provider Registry Refresh"]
        results.append("=" * 50)
        
        # Determine what to refresh
        services_to_refresh = []
        if service_type:
            if service_type not in ['tts', 'stt']:
                return f"Error: Invalid service_type '{service_type}'. Must be 'tts' or 'stt'"
            services_to_refresh = [service_type]
        else:
            services_to_refresh = ['tts', 'stt']
        
        # Refresh endpoints
        for service in services_to_refresh:
            results.append(f"\n{service.upper()} Endpoints:")
            results.append("-" * 30)
            
            urls = TTS_BASE_URLS if service == 'tts' else STT_BASE_URLS
            
            # If specific URL requested, only check that one
            if base_url:
                if base_url not in urls:
                    results.append(f"  ⚠️  {base_url} not in configured URLs")
                    continue
                urls = [base_url]
            
            for url in urls:
                if optimistic:
                    # In optimistic mode, just mark everything as available
                    from voice_mode.provider_discovery import (
                        EndpointInfo, KNOWN_KOKORO_VOICES, OPENAI_SEED_VOICES,
                    )
                    from datetime import datetime

                    provider_registry.registry[service][url] = EndpointInfo(
                        base_url=url,
                        models=_default_stt_models(url) if service == "stt" else (["tts-1", "tts-1-hd"] if "openai.com" in url else ["tts-1"]),
                        voices=[] if service == "stt" else list(OPENAI_SEED_VOICES if "openai.com" in url else KNOWN_KOKORO_VOICES),
                        provider_type=detect_provider_type(url),
                        last_check=datetime.utcnow().isoformat() + "Z"
                    )
                    results.append(f"\n  ✅ {url}")
                    results.append(f"     Status: Available (optimistic mode)")
                else:
                    # Non-optimistic mode: Actually discover endpoint capabilities
                    try:
                        await provider_registry._discover_endpoint(service, url)
                        endpoint_info = provider_registry.registry[service][url]

                        if endpoint_info.last_error:
                            results.append(f"\n  ❌ {url}")
                            results.append(f"     Error: {endpoint_info.last_error}")
                        else:
                            results.append(f"\n  ✅ {url}")
                            if endpoint_info.models:
                                results.append(f"     Models: {', '.join(endpoint_info.models)}")
                            if service == 'tts' and endpoint_info.voices:
                                results.append(f"     Voices: {', '.join(endpoint_info.voices[:5])}{'...' if len(endpoint_info.voices) > 5 else ''}")
                    except Exception as e:
                        results.append(f"\n  ❌ {url}")
                        results.append(f"     Error: {str(e)}")
        
        results.append("\n✨ Refresh complete!")
        return "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error refreshing provider registry: {e}")
        return f"Error refreshing provider registry: {str(e)}"


@mcp.tool()
async def get_provider_details(base_url: str) -> str:
    """Get detailed information about a specific provider endpoint.
    
    Args:
        base_url: The base URL of the provider (e.g., 'http://127.0.0.1:8880/v1')
    
    Returns:
        Detailed information about the provider including all models and voices
    """
    try:
        # Ensure registry is initialized
        await provider_registry.initialize()
        
        # Check both TTS and STT registries
        endpoint_info = None
        service_type = None
        
        if base_url in provider_registry.registry["tts"]:
            endpoint_info = provider_registry.registry["tts"][base_url]
            service_type = "TTS"
        elif base_url in provider_registry.registry["stt"]:
            endpoint_info = provider_registry.registry["stt"][base_url]
            service_type = "STT"
        else:
            return f"Error: Endpoint '{base_url}' not found in registry"
        
        results = [f"📊 Provider Details: {base_url}"]
        results.append("=" * 50)
        
        results.append(f"\nService Type: {service_type}")
        results.append(f"Provider Type: {endpoint_info.provider_type or 'unknown'}")
        results.append(f"Last Check: {endpoint_info.last_check or 'Never'}")

        if endpoint_info.last_error:
            results.append(f"\n⚠️  Error: {endpoint_info.last_error}")
        else:
            results.append(f"Status: ✅ Available")
        
        if endpoint_info.models:
            results.append(f"\n📦 Models ({len(endpoint_info.models)}):")
            for model in endpoint_info.models:
                results.append(f"  • {model}")
        else:
            results.append("\n📦 Models: None detected")
        
        if service_type == "TTS" and endpoint_info.voices:
            results.append(f"\n🔊 Voices ({len(endpoint_info.voices)}):")
            for voice in endpoint_info.voices:
                results.append(f"  • {voice}")
        
        return "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error getting provider details: {e}")
        return f"Error getting provider details: {str(e)}"