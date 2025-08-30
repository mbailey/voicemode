"""
Provider selection and management for voice-mode.

This module provides compatibility layer and selection logic for voice providers,
working with the dynamic provider discovery system.
"""

import logging
from typing import Dict, Optional, List, Any, Tuple
from openai import AsyncOpenAI

from .config import TTS_VOICES, TTS_MODELS, TTS_BASE_URLS, OPENAI_API_KEY, get_voice_preferences
from .provider_discovery import provider_registry, EndpointInfo

logger = logging.getLogger("voice-mode")


async def get_tts_client_and_voice(
    voice: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> Tuple[AsyncOpenAI, str, str, EndpointInfo]:
    """
    Get TTS client with automatic selection based on preferences.
    
    Selection algorithm (voice-first approach):
    1. If specific base_url requested, use it with specified/best voice and model
    2. If specific voice requested, find first healthy endpoint that supports it
    3. Otherwise, iterate through TTS_VOICES preference list:
       - For each voice, find first healthy endpoint that supports it
       - Then find compatible model from TTS_MODELS preference list
       - Use this combination
    
    Args:
        voice: Specific voice to use (optional)
        model: Specific model to use (optional)
        base_url: Specific base URL to use (optional)
    
    Returns:
        Tuple of (client, selected_voice, selected_model, endpoint_info)
    
    Raises:
        ValueError: If no suitable endpoint is found
    """
    # Ensure registry is initialized
    await provider_registry.initialize()
    
    # If specific base_url is requested, use it directly
    if base_url:
        logger.info(f"TTS Provider Selection: Using specific base URL: {base_url}")
        endpoint_info = provider_registry.registry["tts"].get(base_url)
        if not endpoint_info or not endpoint_info.healthy:
            raise ValueError(f"Requested base URL {base_url} is not available")
        
        selected_voice = voice or _select_voice_for_endpoint(endpoint_info)
        selected_model = model or _select_model_for_endpoint(endpoint_info)
        
        client = AsyncOpenAI(
            api_key=OPENAI_API_KEY or "dummy-key-for-local",
            base_url=base_url
        )
        
        logger.info(f"  • Selected endpoint: {base_url}")
        logger.info(f"  • Selected voice: {selected_voice}")
        logger.info(f"  • Selected model: {selected_model}")
        
        return client, selected_voice, selected_model, endpoint_info
    
    # Voice-first selection algorithm
    # Get user preferences from configuration
    voice_preferences = get_voice_preferences()
    combined_voice_list = voice_preferences
    
    logger.info(f"TTS Provider Selection (voice-first)")
    if voice_preferences:
        logger.info(f"  Voice preferences: {voice_preferences}")
    logger.info(f"  Voice list: {combined_voice_list}")
    logger.info(f"  Preferred models: {TTS_MODELS}")
    logger.info(f"  Available endpoints: {TTS_BASE_URLS}")
    
    # If specific voice is requested, find an endpoint that supports it
    if voice:
        logger.info(f"  Specific voice requested: {voice}")
        for url in TTS_BASE_URLS:
            endpoint_info = provider_registry.registry["tts"].get(url)
            if not endpoint_info or not endpoint_info.healthy:
                continue
            
            if voice in endpoint_info.voices:
                selected_voice = voice
                selected_model = _select_model_for_endpoint(endpoint_info, model)
                
                api_key = OPENAI_API_KEY if endpoint_info.provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
                client = AsyncOpenAI(api_key=api_key, base_url=url)
                
                logger.info(f"  ✓ Selected endpoint: {url} ({endpoint_info.provider_type})")
                logger.info(f"  ✓ Selected voice: {selected_voice}")
                logger.info(f"  ✓ Selected model: {selected_model}")
                
                return client, selected_voice, selected_model, endpoint_info
    
    # No specific voice requested - iterate through voice preferences
    logger.info("  No specific voice requested, checking voice preferences...")
    for preferred_voice in combined_voice_list:
        logger.debug(f"  Looking for voice: {preferred_voice}")
        
        # Check each endpoint for this voice
        for url in TTS_BASE_URLS:
            endpoint_info = provider_registry.registry["tts"].get(url)
            if not endpoint_info or not endpoint_info.healthy:
                continue
            
            if preferred_voice in endpoint_info.voices:
                logger.info(f"  Found voice '{preferred_voice}' at {url} ({endpoint_info.provider_type})")
                selected_voice = preferred_voice
                selected_model = _select_model_for_endpoint(endpoint_info, model)
                
                api_key = OPENAI_API_KEY if endpoint_info.provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
                client = AsyncOpenAI(api_key=api_key, base_url=url)
                
                logger.info(f"  ✓ Selected endpoint: {url} ({endpoint_info.provider_type})")
                logger.info(f"  ✓ Selected voice: {selected_voice}")
                logger.info(f"  ✓ Selected model: {selected_model}")
                
                return client, selected_voice, selected_model, endpoint_info
    
    # No preferred voices found - fall back to any available endpoint
    logger.warning("  No preferred voices available, using any available endpoint...")
    for url in TTS_BASE_URLS:
        endpoint_info = provider_registry.registry["tts"].get(url)
        if not endpoint_info or not endpoint_info.healthy:
            continue
        
        if endpoint_info.voices:
            selected_voice = endpoint_info.voices[0]
            selected_model = _select_model_for_endpoint(endpoint_info, model)
            
            api_key = OPENAI_API_KEY if endpoint_info.provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
            client = AsyncOpenAI(api_key=api_key, base_url=url)
            
            logger.info(f"  ✓ Selected endpoint: {url} ({endpoint_info.provider_type})")
            logger.info(f"  ✓ Selected voice: {selected_voice}")
            logger.info(f"  ✓ Selected model: {selected_model}")
            
            return client, selected_voice, selected_model, endpoint_info
    
    # No suitable endpoint found
    raise ValueError("No healthy TTS endpoints found that support requested voice/model preferences")


async def get_stt_client(
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> Tuple[AsyncOpenAI, str, EndpointInfo]:
    """
    Get STT client with automatic selection.
    
    Args:
        model: Specific model to use (optional)
        base_url: Specific base URL to use (optional)
    
    Returns:
        Tuple of (client, selected_model, endpoint_info)
    
    Raises:
        ValueError: If no suitable endpoint is found
    """
    # Ensure registry is initialized
    await provider_registry.initialize()
    
    # If specific base_url is requested, use it directly
    if base_url:
        endpoint_info = provider_registry.registry["stt"].get(base_url)
        if not endpoint_info or not endpoint_info.healthy:
            raise ValueError(f"Requested base URL {base_url} is not available")
        
        selected_model = model or "whisper-1"  # Default STT model
        
        client = AsyncOpenAI(
            api_key=OPENAI_API_KEY or "dummy-key-for-local",
            base_url=base_url
        )
        
        return client, selected_model, endpoint_info
    
    # Get any healthy STT endpoint
    healthy_endpoints = provider_registry.get_healthy_endpoints("stt")
    if not healthy_endpoints:
        raise ValueError("No healthy STT endpoints available")
    
    endpoint_info = healthy_endpoints[0]
    selected_model = model or "whisper-1"
    
    api_key = OPENAI_API_KEY if endpoint_info.provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=endpoint_info.base_url
    )
    
    return client, selected_model, endpoint_info


def _select_voice_for_endpoint(endpoint_info: EndpointInfo) -> str:
    """Select the best available voice for an endpoint."""
    # Try to find a preferred voice
    for voice in TTS_VOICES:
        if voice in endpoint_info.voices:
            return voice
    
    # Otherwise use first available voice
    if endpoint_info.voices:
        return endpoint_info.voices[0]
    
    # Fallback
    return "alloy"


def _select_model_for_endpoint(endpoint_info: EndpointInfo, requested_model: Optional[str] = None) -> str:
    """Select the best available model for an endpoint."""
    # If specific model requested and supported, use it
    if requested_model and requested_model in endpoint_info.models:
        return requested_model
    
    # Try to find a preferred model
    for model in TTS_MODELS:
        if model in endpoint_info.models:
            return model
    
    # Otherwise use first available model
    if endpoint_info.models:
        return endpoint_info.models[0]
    
    # Fallback
    return "tts-1"


# Compatibility functions for existing code

async def is_provider_available(provider_id: str, timeout: float = 2.0) -> bool:
    """Check if a provider is available (compatibility function)."""
    # This is now handled by the provider registry
    await provider_registry.initialize()
    
    # Map old provider IDs to base URLs
    provider_map = {
        "kokoro": "http://127.0.0.1:8880/v1",
        "openai": "https://api.openai.com/v1",
        "whisper-local": "http://127.0.0.1:2022/v1",
        "openai-whisper": "https://api.openai.com/v1"
    }
    
    base_url = provider_map.get(provider_id)
    if not base_url:
        return False
    
    # Check in appropriate registry
    service_type = "tts" if provider_id in ["kokoro", "openai"] else "stt"
    endpoint_info = provider_registry.registry[service_type].get(base_url)
    
    return endpoint_info.healthy if endpoint_info else False


def get_provider_by_voice(voice: str) -> Optional[Dict[str, Any]]:
    """Get provider info by voice (compatibility function)."""
    # Kokoro voices
    if voice.startswith(('af_', 'am_', 'bf_', 'bm_')):
        return {
            "id": "kokoro",
            "name": "Kokoro TTS",
            "type": "tts",
            "base_url": "http://127.0.0.1:8880/v1",
            "voices": ["af_sky", "af_sarah", "am_adam", "af_nicole", "am_michael"]
        }
    
    # OpenAI voices
    return {
        "id": "openai",
        "name": "OpenAI TTS",
        "type": "tts",
        "base_url": "https://api.openai.com/v1",
        "voices": ["alloy", "nova", "echo", "fable", "onyx", "shimmer"]
    }


def select_best_voice(provider: str, available_voices: Optional[List[str]] = None) -> Optional[str]:
    """Select the best available voice (compatibility function)."""
    if available_voices is None:
        # Get from registry if possible
        if provider == "kokoro":
            available_voices = ["af_sky", "af_sarah", "am_adam", "af_nicole", "am_michael"]
        else:
            available_voices = ["alloy", "nova", "echo", "fable", "onyx", "shimmer"]
    
    # Get user preferences and prepend to system defaults
    user_preferences = get_preferred_voices()
    combined_voice_list = user_preferences + [v for v in TTS_VOICES if v not in user_preferences]
    
    # Find first preferred voice that's available
    for voice in combined_voice_list:
        if voice in available_voices:
            return voice
    
    # Return first available
    return available_voices[0] if available_voices else None