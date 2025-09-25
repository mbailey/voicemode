"""
Simple failover implementation for voice-mode.

This module provides a direct try-and-failover approach without health checks.
Connection refused errors are instant, so there's no performance penalty.
"""

import logging
from typing import Optional, Tuple, Dict, Any
from openai import AsyncOpenAI
from .provider_discovery import is_local_provider

from .config import TTS_BASE_URLS, STT_BASE_URLS, OPENAI_API_KEY
from .provider_discovery import detect_provider_type

logger = logging.getLogger("voicemode")


async def simple_tts_failover(
    text: str,
    voice: str,
    model: str,
    **kwargs
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Simple TTS failover - try each endpoint in order until one works.
    
    Returns:
        Tuple of (success, metrics, config)
    """
    logger.info(f"simple_tts_failover called with: text='{text[:50]}...', voice={voice}, model={model}")
    logger.info(f"kwargs: {kwargs}")
    
    from .core import text_to_speech
    from .conversation_logger import get_conversation_logger

    # Track attempted endpoints and their errors
    attempted_endpoints = []

    # Get conversation ID from logger
    conversation_logger = get_conversation_logger()
    conversation_id = conversation_logger.conversation_id

    # Try each TTS endpoint in order
    logger.info(f"simple_tts_failover: Starting with TTS_BASE_URLS = {TTS_BASE_URLS}")
    for base_url in TTS_BASE_URLS:
        try:
            logger.info(f"Trying TTS endpoint: {base_url}")
            
            # Create client for this endpoint
            provider_type = detect_provider_type(base_url)
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
            
            # Select appropriate voice for this provider
            if provider_type == "openai":
                # Map Kokoro voices to OpenAI equivalents, or use OpenAI default
                openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
                if voice in openai_voices:
                    selected_voice = voice
                else:
                    # Map common Kokoro voices to OpenAI equivalents
                    voice_mapping = {
                        "af_sky": "nova",
                        "af_sarah": "nova", 
                        "af_alloy": "alloy",
                        "am_adam": "onyx",
                        "am_echo": "echo",
                        "am_onyx": "onyx",
                        "bm_fable": "fable"
                    }
                    selected_voice = voice_mapping.get(voice, "alloy")  # Default to alloy
                    logger.info(f"Mapped voice {voice} to {selected_voice} for OpenAI")
            else:
                selected_voice = voice  # Use original voice for Kokoro
            
            # Disable retries for local endpoints - they either work or don't
            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,  # Reasonable timeout
                max_retries=max_retries
            )
            
            # Create clients dict for text_to_speech
            openai_clients = {'tts': client}
            
            # Try TTS with this endpoint
            success, metrics = await text_to_speech(
                text=text,
                openai_clients=openai_clients,
                tts_model=model,
                tts_voice=selected_voice,
                tts_base_url=base_url,
                conversation_id=conversation_id,
                **kwargs
            )
            
            if success:
                config = {
                    'base_url': base_url,
                    'provider': provider_type,
                    'voice': selected_voice,  # Return the voice actually used
                    'model': model,
                    'endpoint': f"{base_url}/audio/speech"
                }
                logger.info(f"TTS succeeded with {base_url} using voice {selected_voice}")
                return True, metrics, config

        except Exception as e:
            error_message = str(e)
            logger.error(f"TTS failed for {base_url}: {error_message}")

            # Add to attempted endpoints with error details
            attempted_endpoints.append({
                'endpoint': f"{base_url}/audio/speech",
                'provider': provider_type,
                'voice': selected_voice,
                'model': model,
                'error': error_message
            })

            # Continue to next endpoint
            continue

    # All endpoints failed - return detailed error info
    logger.error(f"All TTS endpoints failed after {len(attempted_endpoints)} attempts")
    error_config = {
        'error_type': 'all_providers_failed',
        'attempted_endpoints': attempted_endpoints
    }
    return False, None, error_config


async def simple_stt_failover(
    audio_file,
    model: str = "whisper-1",
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Simple STT failover - try each endpoint in order until one works.

    Returns:
        Dict with transcription result or error information:
        - Success: {"text": "...", "provider": "...", "endpoint": "..."}
        - No speech: {"error_type": "no_speech", "provider": "..."}
        - All failed: {"error_type": "connection_failed", "attempted_endpoints": [...]}
    """
    connection_errors = []
    successful_but_empty = False
    successful_provider = None

    # Log STT request details
    logger.info("STT: Starting speech-to-text conversion")
    logger.info(f"  Available endpoints: {STT_BASE_URLS}")

    # Try each STT endpoint in order
    for i, base_url in enumerate(STT_BASE_URLS):
        try:
            # Detect provider type for logging
            provider_type = detect_provider_type(base_url)

            if i == 0:
                logger.info(f"STT: Attempting primary endpoint: {base_url} ({provider_type})")
            else:
                logger.warning(f"STT: Primary failed, attempting fallback #{i}: {base_url} ({provider_type})")

            # Create client for this endpoint
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            # Disable retries for local endpoints - they either work or don't
            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                max_retries=max_retries
            )

            # Try STT with this endpoint
            transcription = await client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="text"
            )

            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

            if text:
                logger.info(f"✓ STT succeeded with {provider_type} at {base_url}")
                logger.info(f"  Transcribed: {text[:100]}{'...' if len(text) > 100 else ''}")
                # Return both text and provider info for display
                return {"text": text, "provider": provider_type, "endpoint": base_url}
            else:
                # Successful connection but no speech detected
                logger.warning(f"STT returned empty result from {base_url} ({provider_type})")
                successful_but_empty = True
                successful_provider = provider_type

        except Exception as e:
            error_str = str(e)
            provider_type = detect_provider_type(base_url)

            # Track connection/auth errors
            full_endpoint = f"{base_url}/audio/transcriptions" if not base_url.endswith("/v1") else f"{base_url}/audio/transcriptions"
            connection_errors.append({
                "endpoint": full_endpoint,
                "provider": provider_type,
                "error": error_str
            })

            # Log failure with appropriate level based on whether we have fallbacks
            if i < len(STT_BASE_URLS) - 1:
                logger.warning(f"STT failed for {base_url} ({provider_type}): {e}")
                logger.info("  Will try next endpoint...")
            else:
                logger.error(f"STT failed for final endpoint {base_url} ({provider_type}): {e}")

            # Continue to next endpoint
            continue

    # Determine what to return based on results
    if successful_but_empty:
        # At least one endpoint connected successfully but returned no speech
        logger.info("STT: No speech detected (successful connection)")
        return {"error_type": "no_speech", "provider": successful_provider}
    elif connection_errors:
        # All endpoints failed with connection/auth errors
        logger.error(f"✗ All STT endpoints failed after {len(STT_BASE_URLS)} attempts")
        return {"error_type": "connection_failed", "attempted_endpoints": connection_errors}
    else:
        # Should not reach here, but handle it gracefully
        logger.error("STT: Unexpected state - no successful connections and no errors tracked")
        return None