"""Conversation tools for interactive voice interactions."""

import asyncio
import logging
import os
import time
import traceback
from typing import Optional, Literal, Tuple, Dict, Union
from pathlib import Path
from datetime import datetime

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from pydub import AudioSegment
from openai import AsyncOpenAI
import httpx

# Optional webrtcvad for silence detection
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError as e:
    webrtcvad = None
    VAD_AVAILABLE = False

from voice_mode.server import mcp
from voice_mode.conversation_logger import get_conversation_logger
from voice_mode.config import (
    audio_operation_lock,
    SAMPLE_RATE,
    CHANNELS,
    DEBUG,
    DEBUG_DIR,
    VAD_DEBUG,
    SAVE_AUDIO,
    AUDIO_DIR,
    OPENAI_API_KEY,
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    PREFER_LOCAL,
    AUDIO_FEEDBACK_ENABLED,
    service_processes,
    HTTP_CLIENT_CONFIG,
    save_transcription,
    SAVE_TRANSCRIPTIONS,
    DISABLE_SILENCE_DETECTION,
    VAD_AGGRESSIVENESS,
    SILENCE_THRESHOLD_MS,
    MIN_RECORDING_DURATION,
    SKIP_TTS,
    VAD_CHUNK_DURATION_MS,
    INITIAL_SILENCE_GRACE_PERIOD,
    DEFAULT_LISTEN_DURATION,
    TTS_VOICES,
    TTS_MODELS
)
import voice_mode.config
from voice_mode.providers import (
    get_tts_client_and_voice,
    get_stt_client,
    is_provider_available,
    get_provider_by_voice,
    select_best_voice
)
from voice_mode.provider_discovery import provider_registry
from voice_mode.core import (
    get_openai_clients,
    text_to_speech,
    cleanup as cleanup_clients,
    save_debug_file,
    get_debug_filename,
    get_audio_path,
    play_chime_start,
    play_chime_end
)
from voice_mode.tools.statistics import track_voice_interaction
from voice_mode.utils import (
    get_event_logger,
    log_recording_start,
    log_recording_end,
    log_stt_start,
    log_stt_complete,
    log_tool_request_start,
    log_tool_request_end
)
from voice_mode.pronounce import get_manager as get_pronounce_manager, is_enabled as pronounce_enabled

logger = logging.getLogger("voice-mode")

# Log silence detection config at module load time
logger.info(f"Module loaded with DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}")

# Track last session end time for measuring AI thinking time
last_session_end_time = None

# Initialize OpenAI clients - now using provider registry for endpoint discovery
openai_clients = get_openai_clients(OPENAI_API_KEY or "dummy-key-for-local", None, None)

# Provider-specific clients are now created dynamically by the provider registry


async def startup_initialization():
    """Initialize services on startup based on configuration"""
    if voice_mode.config._startup_initialized:
        return
    
    voice_mode.config._startup_initialized = True
    logger.info("Running startup initialization...")
    
    # Initialize provider registry
    logger.info("Initializing provider registry...")
    await provider_registry.initialize()
    
    # Check if we should auto-start Kokoro
    auto_start_kokoro = os.getenv("VOICE_MODE_AUTO_START_KOKORO", "").lower() in ("true", "1", "yes", "on")
    if auto_start_kokoro:
        try:
            # Check if Kokoro is already running
            async with httpx.AsyncClient(timeout=3.0) as client:
                base_url = 'http://127.0.0.1:8880'  # Kokoro default
                health_url = f"{base_url}/health"
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    logger.info("Kokoro TTS is already running externally")
                else:
                    raise Exception("Not running")
        except:
            # Kokoro is not running, start it
            logger.info("Auto-starting Kokoro TTS service...")
            try:
                # Import here to avoid circular dependency
                import subprocess
                if "kokoro" not in service_processes:
                    process = subprocess.Popen(
                        ["uvx", "kokoro-fastapi"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={**os.environ}
                    )
                    service_processes["kokoro"] = process
                    
                    # Wait a moment for it to start
                    await asyncio.sleep(2.0)
                    
                    # Verify it started
                    if process.poll() is None:
                        logger.info(f"✓ Kokoro TTS started successfully (PID: {process.pid})")
                    else:
                        logger.error("Failed to start Kokoro TTS")
            except Exception as e:
                logger.error(f"Error auto-starting Kokoro: {e}")
    
    # Log initial status
    logger.info("Service initialization complete")


async def get_tts_config(provider: Optional[str] = None, voice: Optional[str] = None, model: Optional[str] = None, instructions: Optional[str] = None):
    """Get TTS configuration based on provider selection"""
    logger.info(f"[DEBUG] get_tts_config called with provider={provider}, voice={voice}, model={model}")
    
    # Validate instructions usage
    if instructions and model != "gpt-4o-mini-tts":
        logger.warning(f"Instructions parameter is only supported with gpt-4o-mini-tts model, ignoring for model: {model}")
        instructions = None
    
    # Map provider names to base URLs
    provider_urls = {
        'openai': 'https://api.openai.com/v1',
        'kokoro': 'http://127.0.0.1:8880/v1'
    }
    
    # Convert provider name to URL if it's a known provider
    base_url = provider_urls.get(provider, provider)
    
    # Use new provider selection logic
    try:
        client, selected_voice, selected_model, endpoint_info = await get_tts_client_and_voice(
            voice=voice,
            model=model,
            base_url=base_url  # Now using mapped URL
        )
        
        # Return configuration compatible with existing code
        logger.info(f"[DEBUG] TTS endpoint selected: {endpoint_info.base_url} (provider: {endpoint_info.provider_type})")
        logger.info(f"[DEBUG] Using voice: {selected_voice}, model: {selected_model}")
        
        return {
            'client': client,
            'base_url': endpoint_info.base_url,
            'model': selected_model,
            'voice': selected_voice,
            'instructions': instructions,
            'provider': endpoint_info.base_url,  # For logging
            'provider_type': endpoint_info.provider_type
        }
    except Exception as e:
        logger.error(f"Failed to get TTS client: {e}")
        # Fallback to legacy behavior
        return {
            'client_key': 'tts',
            'base_url': 'https://api.openai.com/v1',  # Fallback to OpenAI
            'model': model or 'tts-1',
            'voice': voice or 'alloy',
            'instructions': instructions,
            'provider_type': 'openai'
        }


async def get_stt_config(provider: Optional[str] = None):
    """Get STT configuration based on provider selection"""
    try:
        # Use new provider selection logic
        client, selected_model, endpoint_info = await get_stt_client(
            model=None,  # Let system select
            base_url=provider  # Allow provider to be a base URL
        )
        
        return {
            'client': client,
            'base_url': endpoint_info.base_url,
            'model': selected_model,
            'provider': endpoint_info.base_url,  # For logging
            'provider_type': endpoint_info.provider_type
        }
    except Exception as e:
        logger.error(f"Failed to get STT client: {e}")
        # Fallback to legacy behavior
        return {
            'client_key': 'stt',
            'base_url': 'https://api.openai.com/v1',  # Fallback to OpenAI
            'model': 'whisper-1',
            'provider': 'openai-whisper',
            'provider_type': 'openai'
        }



async def text_to_speech_with_failover(
    message: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    instructions: Optional[str] = None,
    audio_format: Optional[str] = None,
    initial_provider: Optional[str] = None,
    speed: Optional[float] = None
) -> Tuple[bool, Optional[dict], Optional[dict]]:
    """
    Text to speech with automatic failover to next available endpoint.
    
    Returns:
        Tuple of (success, tts_metrics, tts_config)
    """
    from voice_mode.config import SIMPLE_FAILOVER
    
    # Apply pronunciation rules if enabled
    if pronounce_enabled():
        pronounce_mgr = get_pronounce_manager()
        message = pronounce_mgr.process_tts(message)
    
    # Use simple failover if enabled
    if SIMPLE_FAILOVER:
        from voice_mode.simple_failover import simple_tts_failover
        return await simple_tts_failover(
            text=message,
            voice=voice or TTS_VOICES[0],
            model=model or TTS_MODELS[0],
            instructions=instructions,
            audio_format=audio_format,
            debug=DEBUG,
            debug_dir=DEBUG_DIR if DEBUG else None,
            save_audio=SAVE_AUDIO,
            audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
            speed=speed
        )
    
    # Original implementation with health checks
    from voice_mode.provider_discovery import provider_registry
    
    # Track which URLs we've tried
    tried_urls = set()
    last_error = None
    
    # If initial_provider specified, try it first
    if initial_provider:
        provider_urls = {'openai': 'https://api.openai.com/v1', 'kokoro': 'http://127.0.0.1:8880/v1'}
        initial_url = provider_urls.get(initial_provider, initial_provider)
        if initial_url:
            tried_urls.add(initial_url)
            try:
                tts_config = await get_tts_config(initial_provider, voice, model, instructions)
                
                # Handle both new client object and legacy client_key
                if 'client' in tts_config:
                    openai_clients['_temp_tts'] = tts_config['client']
                    client_key = '_temp_tts'
                else:
                    client_key = tts_config.get('client_key', 'tts')
                
                # Get conversation ID from logger
                conversation_logger = get_conversation_logger()
                conversation_id = conversation_logger.conversation_id
                
                success, tts_metrics = await text_to_speech(
                    text=message,
                    openai_clients=openai_clients,
                    tts_model=tts_config['model'],
                    tts_base_url=tts_config['base_url'],
                    tts_voice=tts_config['voice'],
                    debug=DEBUG,
                    debug_dir=DEBUG_DIR if DEBUG else None,
                    save_audio=SAVE_AUDIO,
                    audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
                    client_key=client_key,
                    instructions=tts_config.get('instructions'),
                    audio_format=audio_format,
                    conversation_id=conversation_id,
                    speed=speed
                )
                
                # Clean up temporary client
                if '_temp_tts' in openai_clients:
                    del openai_clients['_temp_tts']
                
                if success:
                    return success, tts_metrics, tts_config
                
                # Mark endpoint as unhealthy
                await provider_registry.mark_unhealthy('tts', tts_config['base_url'], 'TTS request failed')
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Initial provider {initial_provider} failed: {e}")
                logger.debug(f"Full error details for {initial_provider}:", exc_info=True)
    
    # Try remaining endpoints in order
    from voice_mode.config import TTS_BASE_URLS
    
    for base_url in TTS_BASE_URLS:
        if base_url in tried_urls:
            continue
            
        tried_urls.add(base_url)
        
        try:
            # Try to get config for this specific base URL
            tts_config = await get_tts_config(None, voice, model, instructions)
            
            # Skip if we got a different URL than requested (means our preferred wasn't available)
            if tts_config.get('base_url') != base_url:
                continue
            
            # Handle both new client object and legacy client_key
            if 'client' in tts_config:
                openai_clients['_temp_tts'] = tts_config['client']
                client_key = '_temp_tts'
            else:
                client_key = tts_config.get('client_key', 'tts')
            
            # Get conversation ID from logger
            conversation_logger = get_conversation_logger()
            conversation_id = conversation_logger.conversation_id
            
            success, tts_metrics = await text_to_speech(
                text=message,
                openai_clients=openai_clients,
                tts_model=tts_config['model'],
                tts_base_url=tts_config['base_url'],
                tts_voice=tts_config['voice'],
                debug=DEBUG,
                debug_dir=DEBUG_DIR if DEBUG else None,
                save_audio=SAVE_AUDIO,
                audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
                client_key=client_key,
                instructions=tts_config.get('instructions'),
                audio_format=audio_format,
                conversation_id=conversation_id,
                speed=speed
            )
            
            # Clean up temporary client
            if '_temp_tts' in openai_clients:
                del openai_clients['_temp_tts']
            
            if success:
                logger.info(f"TTS succeeded with failover to: {base_url}")
                return success, tts_metrics, tts_config
            else:
                # Mark endpoint as unhealthy
                await provider_registry.mark_unhealthy('tts', base_url, 'TTS request failed')
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"TTS failed for {base_url}: {e}")
            # Mark endpoint as unhealthy
            await provider_registry.mark_unhealthy('tts', base_url, str(e))
    
    # All endpoints failed
    logger.error(f"All TTS endpoints failed. Last error: {last_error}")
    
    # Create a config dict with error information
    from voice_mode.config import TTS_BASE_URLS as CONFIG_TTS_BASE_URLS
    error_config = {
        'error': last_error,
        'tried_urls': list(tried_urls),
        'base_url': CONFIG_TTS_BASE_URLS[0] if CONFIG_TTS_BASE_URLS else 'https://api.openai.com/v1'
    }
    
    return False, None, error_config


async def speech_to_text(audio_data: np.ndarray, save_audio: bool = False, audio_dir: Optional[Path] = None, transport: str = "local") -> Optional[str]:
    """Convert audio to text with automatic failover"""
    # Use the new failover implementation
    return await speech_to_text_with_failover(audio_data, save_audio, audio_dir, transport)


async def speech_to_text_with_failover(
    audio_data: np.ndarray, 
    save_audio: bool = False, 
    audio_dir: Optional[Path] = None,
    transport: str = "local"
) -> Optional[str]:
    """
    Speech to text with automatic failover to next available endpoint.
    
    Returns:
        Transcribed text or None if all endpoints fail
    """
    from voice_mode.config import SIMPLE_FAILOVER, STT_BASE_URLS
    
    # Use simple failover if enabled
    if SIMPLE_FAILOVER:
        import tempfile
        from voice_mode.conversation_logger import get_conversation_logger
        from voice_mode.core import save_debug_file, get_debug_filename
        
        # Determine if we should save the file permanently or use a temp file
        if save_audio and audio_dir:
            # Save directly to final location
            conversation_logger = get_conversation_logger()
            conversation_id = conversation_logger.conversation_id
            
            # Create year/month directory structure
            now = datetime.now()
            year_dir = audio_dir / str(now.year)
            month_dir = year_dir / f"{now.month:02d}"
            month_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename and path
            filename = get_debug_filename("stt", "wav", conversation_id)
            wav_file_path = month_dir / filename
            
            # Write audio data directly to final location
            write(str(wav_file_path), SAMPLE_RATE, audio_data)
            logger.info(f"STT audio saved to: {wav_file_path}")
            
            # Use the saved file for STT
            with open(wav_file_path, 'rb') as audio_file:
                from voice_mode.simple_failover import simple_stt_failover
                result = await simple_stt_failover(
                    audio_file=audio_file,
                    model="whisper-1"
                )
            # Don't delete - it's our saved audio file
        else:
            # Use temporary file that will be deleted
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                write(tmp_file.name, SAMPLE_RATE, audio_data)
                tmp_file.flush()
                
                with open(tmp_file.name, 'rb') as audio_file:
                    from voice_mode.simple_failover import simple_stt_failover
                    result = await simple_stt_failover(
                        audio_file=audio_file,
                        model="whisper-1"
                    )
                
                # Clean up temp file
                os.unlink(tmp_file.name)
        
        return result
    
    # Original implementation with health checks
    from voice_mode.provider_discovery import provider_registry
    
    # Track which URLs we've tried
    tried_urls = set()
    last_error = None
    
    # Try configured endpoints in order
    for base_url in STT_BASE_URLS:
        if base_url in tried_urls:
            continue
            
        tried_urls.add(base_url)
        
        try:
            # Get STT config for this specific endpoint
            client, selected_model, endpoint_info = await get_stt_client(base_url=base_url)
            
            if not client:
                logger.warning(f"No STT client available for {base_url}")
                continue
            
            from voice_mode.provider_discovery import detect_provider_type
            
            stt_config = {
                'client': client,
                'model': selected_model,
                'base_url': endpoint_info.base_url if endpoint_info else base_url,
                'provider': 'whisper-local' if '127.0.0.1' in base_url or 'localhost' in base_url else 'openai-whisper',
                'provider_type': detect_provider_type(endpoint_info.base_url if endpoint_info else base_url)
            }
            
            logger.info(f"Attempting STT with {stt_config['provider']} at {stt_config['base_url']}")
            
            # Create openai_clients dict with temporary STT client
            openai_clients = {'_temp_stt': client}
            
            # Call original speech_to_text with this config
            result = await _speech_to_text_internal(
                audio_data, 
                stt_config, 
                openai_clients,
                save_audio, 
                audio_dir
            )
            
            if result:
                logger.info(f"STT succeeded with {stt_config['provider']}")
                return result
            else:
                # Mark endpoint as unhealthy if it returned None
                await provider_registry.mark_unhealthy('stt', base_url, 'STT returned no result')
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"STT failed for {base_url}: {e}")
            # Mark endpoint as unhealthy
            await provider_registry.mark_unhealthy('stt', base_url, str(e))
    
    # All endpoints failed
    logger.error(f"All STT endpoints failed. Last error: {last_error}")
    return None


async def _speech_to_text_internal(
    audio_data: np.ndarray,
    stt_config: dict,
    openai_clients: dict,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None
) -> Optional[str]:
    """Internal speech to text implementation (extracted from original speech_to_text)"""
    logger.info(f"STT: Converting speech to text, audio data shape: {audio_data.shape}")
    
    if DEBUG:
        logger.debug(f"STT config - Model: {stt_config['model']}, Base URL: {stt_config['base_url']}")
        logger.debug(f"Audio stats - Min: {audio_data.min()}, Max: {audio_data.max()}, Mean: {audio_data.mean():.2f}")
    
    wav_file = None
    export_file = None
    export_format = None
    try:
        import tempfile
        
        # Check if input is silent
        if np.abs(audio_data).max() < 0.001:
            logger.warning("Audio appears to be silent")
            return None
        
        # Ensure audio is in the correct format
        if audio_data.dtype != np.int16:
            logger.debug(f"Converting audio from {audio_data.dtype} to int16")
            audio_data = (audio_data * 32767).astype(np.int16)
        
        # Save as WAV file temporarily
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file_obj:
            wav_file = wav_file_obj.name
            logger.debug(f"Writing audio to WAV file: {wav_file}")
            write(wav_file, SAMPLE_RATE, audio_data)
        
        # Save debug file for original recording
        if DEBUG:
            try:
                with open(wav_file, 'rb') as f:
                    debug_path = save_debug_file(f.read(), "stt-input", "wav", DEBUG_DIR, DEBUG)
                    if debug_path:
                        logger.info(f"STT debug recording saved to: {debug_path}")
            except Exception as e:
                logger.error(f"Failed to save debug WAV: {e}")
        
        # Initialize audio_path for JSONL logging
        audio_path = None
        
        # Save audio file if audio saving is enabled
        if save_audio and audio_dir:
            try:
                with open(wav_file, 'rb') as f:
                    # Get conversation ID from logger
                    conversation_logger = get_conversation_logger()
                    conversation_id = conversation_logger.conversation_id
                    audio_path = save_debug_file(f.read(), "stt", "wav", audio_dir, True, conversation_id)
                    if audio_path:
                        logger.info(f"STT audio saved to: {audio_path}")
            except Exception as e:
                logger.error(f"Failed to save audio WAV: {e}")
        
        # Import config for audio format
        from ..config import STT_AUDIO_FORMAT, validate_audio_format, get_format_export_params
        
        # Determine provider from base URL (simple heuristic)
        provider = stt_config.get('provider', 'openai-whisper')
        # Check if using local Whisper endpoint
        if stt_config.get('base_url') and ("127.0.0.1" in stt_config['base_url'] or "localhost" in stt_config['base_url']):
            provider = "whisper-local"
        
        # Check if we can skip conversion for local whisper
        skip_conversion = False
        if provider == "whisper-local":
            # Check if whisper is truly local (not SSH-forwarded)
            from voice_mode.utils.services.common import check_service_status
            from voice_mode.config import WHISPER_PORT
            status, _ = check_service_status(WHISPER_PORT)
            if status == "local":
                skip_conversion = True
                logger.info("Detected truly local whisper - skipping audio conversion, using WAV directly")
        
        if skip_conversion:
            # Use WAV directly for local whisper
            upload_file = wav_file
            export_format = "wav"
            logger.debug("Using WAV file directly for local whisper upload")
        else:
            # Validate format for provider
            export_format = validate_audio_format(STT_AUDIO_FORMAT, provider, "stt")
            
            # Convert WAV to target format for upload
            logger.debug(f"Converting WAV to {export_format.upper()} for upload...")
            conversion_start = time.perf_counter()
            try:
                audio = AudioSegment.from_wav(wav_file)
                logger.debug(f"Audio loaded - Duration: {len(audio)}ms, Channels: {audio.channels}, Frame rate: {audio.frame_rate}")
                
                # Get export parameters for the format
                export_params = get_format_export_params(export_format)
                
                with tempfile.NamedTemporaryFile(suffix=f'.{export_format}', delete=False) as export_file_obj:
                    export_file = export_file_obj.name
                    audio.export(export_file, **export_params)
                    upload_file = export_file
                    conversion_time = time.perf_counter() - conversion_start
                    logger.info(f"Audio conversion: WAV → {export_format.upper()} took {conversion_time:.3f}s")
                    logger.debug(f"{export_format.upper()} created for STT upload: {upload_file}")
            except Exception as e:
                if "ffmpeg" in str(e).lower() or "avconv" in str(e).lower():
                    logger.error(f"Audio conversion failed - FFmpeg may not be installed: {e}")
                    from voice_mode.utils.ffmpeg_check import get_install_instructions
                    logger.error(f"\n{get_install_instructions()}")
                    raise RuntimeError("FFmpeg is required but not found. Please install FFmpeg and try again.") from e
                else:
                    raise
        
        # Save debug file for upload version
        if DEBUG:
            try:
                with open(upload_file, 'rb') as f:
                    debug_path = save_debug_file(f.read(), "stt-upload", export_format, DEBUG_DIR, DEBUG)
                    if debug_path:
                        logger.info(f"Upload audio saved to: {debug_path}")
            except Exception as e:
                logger.error(f"Failed to save debug {export_format.upper()}: {e}")
        
        # Get file size for logging
        file_size = os.path.getsize(upload_file)
        logger.debug(f"Uploading {file_size} bytes to STT API...")
        
        # Perform STT based on configuration
        with open(upload_file, 'rb') as audio_file:
            # Use client from config
            if 'client' in stt_config:
                stt_client = stt_config['client']
            else:
                # Legacy: get from openai_clients dict
                client_key = stt_config.get('client_key', 'stt')
                stt_client = openai_clients.get(client_key)
                if not stt_client:
                    # Fallback to temporary client
                    stt_client = openai_clients['_temp_stt']
            
            transcription = await stt_client.audio.transcriptions.create(
                model=stt_config['model'],
                file=audio_file,
                response_format="text"
            )
            
            logger.debug(f"STT API response type: {type(transcription)}")
            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
            
            # Apply pronunciation rules if enabled
            if text and pronounce_enabled():
                pronounce_mgr = get_pronounce_manager()
                text = pronounce_mgr.process_stt(text)
            
            if text:
                logger.info(f"✓ STT result: '{text}'")
                
                # Save transcription if enabled
                if SAVE_TRANSCRIPTIONS:
                    metadata = {
                        "type": "stt",
                        "model": stt_config.get('model', 'unknown'),
                        "provider": stt_config.get('provider', 'unknown'),
                        "timestamp": datetime.now().isoformat()
                    }
                    save_transcription(text, prefix="stt", metadata=metadata)
                
                # Log to JSONL
                try:
                    conversation_logger = get_conversation_logger()
                    conversation_logger.log_stt(
                        text=text,
                        audio_file=audio_path.name if audio_path else None,
                        duration_ms=int(duration * 1000) if duration else None,
                        model=stt_config.get('model'),
                        provider=stt_config.get('provider', 'openai'),
                        provider_url=stt_config.get('base_url'),
                        provider_type=stt_config.get('provider_type'),
                        audio_format=export_format,  # Use actual format from conversion
                        transport=transport,
                        silence_detection={
                            "enabled": not DISABLE_SILENCE_DETECTION,
                            "vad_aggressiveness": VAD_AGGRESSIVENESS,
                            "silence_threshold_ms": SILENCE_THRESHOLD_MS
                        },
                        # Add timing metrics if available
                        transcription_time=stt_duration if 'stt_duration' in locals() else None
                    )
                except Exception as e:
                    logger.error(f"Failed to log STT to JSONL: {e}")
                
                return text
            else:
                logger.warning("STT returned empty text")
                return None
                    
    except Exception as e:
        logger.error(f"STT failed: {e}")
        logger.error(f"STT config when error occurred - Model: {stt_config.get('model', 'unknown')}, Base URL: {stt_config.get('base_url', 'unknown')}")
        
        # Check for authentication errors
        error_message = str(e).lower()
        base_url = stt_config.get('base_url', '')
        if hasattr(e, 'response'):
            logger.error(f"HTTP status: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}")
            logger.error(f"Response text: {e.response.text if hasattr(e.response, 'text') else 'unknown'}")
            
            # Check for 401 Unauthorized specifically on OpenAI endpoints
            if hasattr(e.response, 'status_code') and e.response.status_code == 401:
                if 'openai.com' in base_url:
                    logger.error("⚠️  Authentication failed with OpenAI. Please set OPENAI_API_KEY environment variable.")
                    logger.error("   Alternatively, you can use local services (Whisper) without an API key.")
        elif 'api key' in error_message or 'unauthorized' in error_message or 'authentication' in error_message:
            if 'openai.com' in base_url:
                logger.error("⚠️  Authentication issue detected. Please check your OPENAI_API_KEY.")
                logger.error("   For local-only usage, ensure Whisper is running and configured.")
        
        return None
    finally:
        # Clean up temporary files
        if wav_file and os.path.exists(wav_file):
            try:
                os.unlink(wav_file)
                logger.debug(f"Cleaned up WAV file: {wav_file}")
            except Exception as e:
                logger.error(f"Failed to clean up WAV file: {e}")
        
        if export_file and os.path.exists(export_file):
            try:
                os.unlink(export_file)
                export_format = export_format if 'export_format' in locals() else 'audio'
                logger.debug(f"Cleaned up {export_format.upper()} file: {export_file}")
            except Exception as e:
                logger.error(f"Failed to clean up {export_format.upper() if 'export_format' in locals() else 'audio'} file: {e}")


async def play_audio_feedback(
    text: str, 
    openai_clients: dict, 
    enabled: Optional[bool] = None, 
    style: str = "whisper", 
    feedback_type: Optional[str] = None,
    voice: str = "nova",
    model: str = "gpt-4o-mini-tts",
    pip_leading_silence: Optional[float] = None,
    pip_trailing_silence: Optional[float] = None
) -> None:
    """Play an audio feedback chime
    
    Args:
        text: Which chime to play (either "listening" or "finished")
        openai_clients: OpenAI client instances (kept for compatibility, not used)
        enabled: Override global audio feedback setting
        style: Kept for compatibility, not used
        feedback_type: Kept for compatibility, not used
        voice: Kept for compatibility, not used
        model: Kept for compatibility, not used
        pip_leading_silence: Optional override for leading silence duration
        pip_trailing_silence: Optional override for trailing silence duration
    """
    # Use parameter override if provided, otherwise use global setting
    if enabled is False:
        return
    
    # If enabled is None, use global setting
    if enabled is None:
        enabled = AUDIO_FEEDBACK_ENABLED
    
    # Skip if disabled
    if not enabled:
        return
    
    try:
        # Play appropriate chime with optional delay overrides
        if text == "listening":
            await play_chime_start(
                leading_silence=pip_leading_silence,
                trailing_silence=pip_trailing_silence
            )
        elif text == "finished":
            await play_chime_end(
                leading_silence=pip_leading_silence,
                trailing_silence=pip_trailing_silence
            )
    except Exception as e:
        logger.debug(f"Audio feedback failed: {e}")
        # Don't interrupt the main flow if feedback fails


def record_audio(duration: float) -> np.ndarray:
    """Record audio from microphone"""
    logger.info(f"🎤 Recording audio for {duration}s...")
    if DEBUG:
        try:
            devices = sd.query_devices()
            default_input = sd.default.device[0]
            logger.debug(f"Default input device: {default_input} - {devices[default_input]['name'] if default_input is not None else 'None'}")
            logger.debug(f"Recording config - Sample rate: {SAMPLE_RATE}Hz, Channels: {CHANNELS}, dtype: int16")
        except Exception as dev_e:
            logger.error(f"Error querying audio devices: {dev_e}")
    
    # Save current stdio state
    import sys
    original_stdin = sys.stdin
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    try:
        samples_to_record = int(duration * SAMPLE_RATE)
        logger.debug(f"Recording {samples_to_record} samples...")
        
        recording = sd.rec(
            samples_to_record,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.int16
        )
        sd.wait()
        
        flattened = recording.flatten()
        logger.info(f"✓ Recorded {len(flattened)} samples")
        
        if DEBUG:
            logger.debug(f"Recording stats - Min: {flattened.min()}, Max: {flattened.max()}, Mean: {flattened.mean():.2f}")
            # Check if recording contains actual audio (not silence)
            rms = np.sqrt(np.mean(flattened.astype(float) ** 2))
            logger.debug(f"RMS level: {rms:.2f} ({'likely silence' if rms < 100 else 'audio detected'})")
        
        return flattened
        
    except Exception as e:
        logger.error(f"Recording failed: {e}")
        logger.error(f"Audio config when error occurred - Sample rate: {SAMPLE_RATE}, Channels: {CHANNELS}")
        
        # Check if this is a device error that might be recoverable
        error_str = str(e).lower()
        if any(err in error_str for err in ['device unavailable', 'device disconnected', 
                                             'invalid device', 'unanticipated host error',
                                             'portaudio error']):
            logger.info("Audio device error detected - attempting to reinitialize audio system")
            
            # Try to reinitialize sounddevice
            try:
                # Get current default device info before reinit
                try:
                    old_device = sd.query_devices(kind='input')
                    old_device_name = old_device.get('name', 'Unknown')
                except:
                    old_device_name = 'Previous device'
                
                sd._terminate()
                sd._initialize()
                
                # Get new default device info
                try:
                    new_device = sd.query_devices(kind='input')
                    new_device_name = new_device.get('name', 'Unknown')
                    logger.info(f"Audio system reinitialized - switched from '{old_device_name}' to '{new_device_name}'")
                except:
                    logger.info("Audio system reinitialized - retrying with new default device")
                
                # Wait a moment for the system to stabilize
                import time as time_module
                time_module.sleep(0.5)
                
                # Try recording again with the new device (recursive call)
                logger.info("Retrying recording with new audio device...")
                return record_audio(duration)
                
            except Exception as reinit_error:
                logger.error(f"Failed to reinitialize audio: {reinit_error}")
                # Fall through to normal error handling
        
        # Import here to avoid circular imports
        from voice_mode.utils.audio_diagnostics import get_audio_error_help
        
        # Get helpful error message
        help_message = get_audio_error_help(e)
        logger.error(f"\n{help_message}")
        
        # Try to get more info about audio devices
        try:
            devices = sd.query_devices()
            logger.error(f"Available input devices:")
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    logger.error(f"  {i}: {device['name']} (inputs: {device['max_input_channels']})")
        except Exception as dev_e:
            logger.error(f"Cannot query audio devices: {dev_e}")
        
        return np.array([])
    finally:
        # Restore stdio if it was changed
        if sys.stdin != original_stdin:
            sys.stdin = original_stdin
        if sys.stdout != original_stdout:
            sys.stdout = original_stdout
        if sys.stderr != original_stderr:
            sys.stderr = original_stderr


def record_audio_with_silence_detection(max_duration: float, disable_silence_detection: bool = False, min_duration: float = 0.0, vad_aggressiveness: Optional[int] = None) -> Tuple[np.ndarray, bool]:
    """Record audio from microphone with automatic silence detection.
    
    Uses WebRTC VAD to detect when the user stops speaking and automatically
    stops recording after a configurable silence threshold.
    
    Args:
        max_duration: Maximum recording duration in seconds
        disable_silence_detection: If True, disables silence detection and uses fixed duration recording
        min_duration: Minimum recording duration before silence detection can stop (default: 0.0)
        vad_aggressiveness: VAD aggressiveness level (0-3). If None, uses VAD_AGGRESSIVENESS from config
        
    Returns:
        Tuple of (audio_data, speech_detected):
            - audio_data: Numpy array of recorded audio samples
            - speech_detected: Boolean indicating if speech was detected during recording
    """
    
    logger.info(f"record_audio_with_silence_detection called - VAD_AVAILABLE={VAD_AVAILABLE}, DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}, min_duration={min_duration}")
    
    if not VAD_AVAILABLE:
        logger.warning("webrtcvad not available, falling back to fixed duration recording")
        # For fallback, assume speech is present since we can't detect
        return (record_audio(max_duration), True)
    
    if DISABLE_SILENCE_DETECTION or disable_silence_detection:
        if disable_silence_detection:
            logger.info("Silence detection disabled for this interaction by request")
        else:
            logger.info("Silence detection disabled globally via VOICEMODE_DISABLE_SILENCE_DETECTION")
        # For fallback, assume speech is present since we can't detect
        return (record_audio(max_duration), True)
    
    logger.info(f"🎤 Recording with silence detection (max {max_duration}s)...")
    
    try:
        # Initialize VAD with provided aggressiveness or default
        effective_vad_aggressiveness = vad_aggressiveness if vad_aggressiveness is not None else VAD_AGGRESSIVENESS
        vad = webrtcvad.Vad(effective_vad_aggressiveness)
        
        # Calculate chunk size (must be 10, 20, or 30ms worth of samples)
        chunk_samples = int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)
        chunk_duration_s = VAD_CHUNK_DURATION_MS / 1000
        
        # WebRTC VAD only supports 8000, 16000, or 32000 Hz
        # We'll tell VAD we're using 16kHz even though we're recording at 24kHz
        # This requires adjusting our chunk size to match what VAD expects
        vad_sample_rate = 16000
        vad_chunk_samples = int(vad_sample_rate * VAD_CHUNK_DURATION_MS / 1000)
        
        # Recording state
        chunks = []
        silence_duration_ms = 0
        recording_duration = 0
        speech_detected = False
        stop_recording = False
        
        # Use a queue for thread-safe communication
        import queue
        audio_queue = queue.Queue()
        
        # Save stdio state
        import sys
        original_stdin = sys.stdin
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        logger.debug(f"VAD config - Aggressiveness: {effective_vad_aggressiveness} (param: {vad_aggressiveness}, default: {VAD_AGGRESSIVENESS}), "
                    f"Silence threshold: {SILENCE_THRESHOLD_MS}ms, "
                    f"Min duration: {MIN_RECORDING_DURATION}s, "
                    f"Initial grace period: {INITIAL_SILENCE_GRACE_PERIOD}s")
        
        if VAD_DEBUG:
            logger.info(f"[VAD_DEBUG] Starting VAD recording with config:")
            logger.info(f"[VAD_DEBUG]   max_duration: {max_duration}s")
            logger.info(f"[VAD_DEBUG]   min_duration: {min_duration}s")
            logger.info(f"[VAD_DEBUG]   effective_min_duration: {max(MIN_RECORDING_DURATION, min_duration)}s")
            logger.info(f"[VAD_DEBUG]   VAD aggressiveness: {effective_vad_aggressiveness}")
            logger.info(f"[VAD_DEBUG]   Silence threshold: {SILENCE_THRESHOLD_MS}ms")
            logger.info(f"[VAD_DEBUG]   Sample rate: {SAMPLE_RATE}Hz (VAD using {vad_sample_rate}Hz)")
            logger.info(f"[VAD_DEBUG]   Chunk duration: {VAD_CHUNK_DURATION_MS}ms")
        
        def audio_callback(indata, frames, time, status):
            """Callback for continuous audio stream"""
            if status:
                logger.warning(f"Audio stream status: {status}")
                # Check for device-related errors
                status_str = str(status).lower()
                if any(err in status_str for err in ['device unavailable', 'device disconnected', 
                                                      'invalid device', 'unanticipated host error',
                                                      'stream is stopped', 'portaudio error']):
                    # Signal that we should stop recording due to device error
                    audio_queue.put(None)  # Sentinel value to indicate error
                    return
            # Put the audio data in the queue for processing
            audio_queue.put(indata.copy())
        
        try:
            # Create continuous input stream
            with sd.InputStream(samplerate=SAMPLE_RATE,
                               channels=CHANNELS,
                               dtype=np.int16,
                               callback=audio_callback,
                               blocksize=chunk_samples):
                
                logger.debug("Started continuous audio stream")
                
                while recording_duration < max_duration and not stop_recording:
                    try:
                        # Get audio chunk from queue with timeout
                        chunk = audio_queue.get(timeout=0.1)
                        
                        # Check for error sentinel
                        if chunk is None:
                            logger.error("Audio device error detected - stopping recording")
                            # Raise an exception to trigger recovery logic
                            raise sd.PortAudioError("Audio device disconnected or unavailable")
                        
                        # Flatten for consistency
                        chunk_flat = chunk.flatten()
                        chunks.append(chunk_flat)
                        
                        # For VAD, we need to downsample from 24kHz to 16kHz
                        # Use scipy's resample for proper downsampling
                        from scipy import signal
                        # Calculate the number of samples we need after resampling
                        resampled_length = int(len(chunk_flat) * vad_sample_rate / SAMPLE_RATE)
                        vad_chunk = signal.resample(chunk_flat, resampled_length)
                        # Take exactly the number of samples VAD expects
                        vad_chunk = vad_chunk[:vad_chunk_samples].astype(np.int16)
                        chunk_bytes = vad_chunk.tobytes()
                        
                        # Check if chunk contains speech
                        try:
                            is_speech = vad.is_speech(chunk_bytes, vad_sample_rate)
                            if VAD_DEBUG:
                                # Log VAD decision every 500ms for less spam
                                if int(recording_duration * 1000) % 500 == 0:
                                    rms = np.sqrt(np.mean(chunk.astype(float)**2))
                                    logger.info(f"[VAD_DEBUG] t={recording_duration:.1f}s: speech={is_speech}, RMS={rms:.0f}, state={'WAITING' if not speech_detected else 'ACTIVE'}")
                        except Exception as vad_e:
                            logger.warning(f"VAD error: {vad_e}, treating as speech")
                            is_speech = True
                        
                        # State machine for speech detection
                        if not speech_detected:
                            # WAITING_FOR_SPEECH state
                            if is_speech:
                                logger.info("🎤 Speech detected, starting active recording")
                                if VAD_DEBUG:
                                    logger.info(f"[VAD_DEBUG] STATE CHANGE: WAITING_FOR_SPEECH -> SPEECH_ACTIVE at t={recording_duration:.1f}s")
                                speech_detected = True
                                silence_duration_ms = 0
                            # No timeout in this state - just keep waiting
                            # The only exit is speech detection or max_duration
                        else:
                            # We have detected speech at some point
                            if is_speech:
                                # SPEECH_ACTIVE state - reset silence counter
                                silence_duration_ms = 0
                            else:
                                # SILENCE_AFTER_SPEECH state - accumulate silence
                                silence_duration_ms += VAD_CHUNK_DURATION_MS
                                if VAD_DEBUG and silence_duration_ms % 100 == 0:  # More frequent logging in debug mode
                                    logger.info(f"[VAD_DEBUG] Accumulating silence: {silence_duration_ms}/{SILENCE_THRESHOLD_MS}ms, t={recording_duration:.1f}s")
                                elif silence_duration_ms % 200 == 0:  # Log every 200ms
                                    logger.debug(f"Silence: {silence_duration_ms}ms")
                                
                                # Check if we should stop due to silence threshold
                                # Use the larger of MIN_RECORDING_DURATION (global) or min_duration (parameter)
                                effective_min_duration = max(MIN_RECORDING_DURATION, min_duration)
                                if recording_duration >= effective_min_duration and silence_duration_ms >= SILENCE_THRESHOLD_MS:
                                    logger.info(f"✓ Silence threshold reached after {recording_duration:.1f}s of recording")
                                    if VAD_DEBUG:
                                        logger.info(f"[VAD_DEBUG] STOP: silence_duration={silence_duration_ms}ms >= threshold={SILENCE_THRESHOLD_MS}ms")
                                        logger.info(f"[VAD_DEBUG] STOP: recording_duration={recording_duration:.1f}s >= min_duration={effective_min_duration}s")
                                    stop_recording = True
                                elif VAD_DEBUG and recording_duration < effective_min_duration:
                                    if int(recording_duration * 1000) % 500 == 0:  # Log every 500ms
                                        logger.info(f"[VAD_DEBUG] Min duration not met: {recording_duration:.1f}s < {effective_min_duration}s")
                        
                        recording_duration += chunk_duration_s
                            
                    except queue.Empty:
                        # No audio data available, continue waiting
                        continue
                    except Exception as e:
                        logger.error(f"Error processing audio chunk: {e}")
                        break
            
            # Concatenate all chunks
            if chunks:
                full_recording = np.concatenate(chunks)
                
                if not speech_detected:
                    logger.info(f"✓ Recording completed ({recording_duration:.1f}s) - No speech detected")
                    if VAD_DEBUG:
                        logger.info(f"[VAD_DEBUG] FINAL STATE: No speech was ever detected during recording")
                else:
                    logger.info(f"✓ Recorded {len(full_recording)} samples ({recording_duration:.1f}s) with speech")
                    if VAD_DEBUG:
                        logger.info(f"[VAD_DEBUG] FINAL STATE: Speech was detected, recording complete")
                
                if DEBUG:
                    # Calculate RMS for debug
                    rms = np.sqrt(np.mean(full_recording.astype(float) ** 2))
                    logger.debug(f"Recording stats - RMS: {rms:.2f}, Speech detected: {speech_detected}")
                
                # Return tuple: (audio_data, speech_detected)
                return (full_recording, speech_detected)
            else:
                logger.warning("No audio chunks recorded")
                return (np.array([]), False)
                
        except Exception as e:
            logger.error(f"Recording with VAD failed: {e}")
            
            # Import here to avoid circular imports
            from voice_mode.utils.audio_diagnostics import get_audio_error_help
            
            # Check if this is a device error that might be recoverable
            error_str = str(e).lower()
            if any(err in error_str for err in ['device unavailable', 'device disconnected', 
                                                 'invalid device', 'unanticipated host error',
                                                 'portaudio error']):
                logger.info("Audio device error detected - attempting to reinitialize audio system")
                
                # Try to reinitialize sounddevice
                try:
                    # Get current default device info before reinit
                    try:
                        old_device = sd.query_devices(kind='input')
                        old_device_name = old_device.get('name', 'Unknown')
                    except:
                        old_device_name = 'Previous device'
                    
                    sd._terminate()
                    sd._initialize()
                    
                    # Get new default device info
                    try:
                        new_device = sd.query_devices(kind='input')
                        new_device_name = new_device.get('name', 'Unknown')
                        logger.info(f"Audio system reinitialized - switched from '{old_device_name}' to '{new_device_name}'")
                    except:
                        logger.info("Audio system reinitialized - retrying with new default device")
                    
                    # Wait a moment for the system to stabilize
                    import time as time_module
                    time_module.sleep(0.5)
                    
                    # Try recording again with the new device (recursive call in sync context)
                    logger.info("Retrying recording with new audio device...")
                    return record_audio_with_silence_detection(max_duration, disable_silence_detection, min_duration, vad_aggressiveness)
                    
                except Exception as reinit_error:
                    logger.error(f"Failed to reinitialize audio: {reinit_error}")
                    # Fall through to normal error handling
            
            # Get helpful error message
            help_message = get_audio_error_help(e)
            logger.error(f"\n{help_message}")
            
            logger.info("Falling back to fixed duration recording")
            # For fallback, assume speech is present since we can't detect
            return (record_audio(max_duration), True)
            
        finally:
            # Restore stdio
            if sys.stdin != original_stdin:
                sys.stdin = original_stdin
            if sys.stdout != original_stdout:
                sys.stdout = original_stdout
            if sys.stderr != original_stderr:
                sys.stderr = original_stderr
    
    except Exception as e:
        logger.error(f"VAD initialization failed: {e}")
        logger.info("Falling back to fixed duration recording")
        # For fallback, assume speech is present since we can't detect
        return (record_audio(max_duration), True)


async def check_livekit_available() -> bool:
    """Check if LiveKit is available and has active rooms"""
    start_time = time.time()
    logger.debug("Starting LiveKit availability check")
    
    try:
        from livekit import api
        
        api_url = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
        lk_api = api.LiveKitAPI(api_url, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Time the API call specifically
        api_start = time.time()
        rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
        api_duration = time.time() - api_start
        
        active_rooms = [r for r in rooms.rooms if r.num_participants > 0]
        available = len(active_rooms) > 0
        
        total_duration = time.time() - start_time
        logger.info(f"LiveKit availability check: {available} (API: {api_duration:.3f}s, total: {total_duration:.3f}s)")
        
        return available
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.info(f"LiveKit availability check failed: {e} (total: {total_duration:.3f}s)")
        logger.debug(f"LiveKit not available: {e}")
        return False


async def livekit_converse(message: str, room_name: str = "", timeout: float = 60.0) -> str:
    """Have a conversation using LiveKit transport"""
    try:
        from livekit import rtc, api
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import openai as lk_openai, silero
        
        # Auto-discover room if needed
        if not room_name:
            api_url = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
            lk_api = api.LiveKitAPI(api_url, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            
            rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
            for room in rooms.rooms:
                if room.num_participants > 0:
                    room_name = room.name
                    break
            
            if not room_name:
                return "No active LiveKit rooms found"
        
        # Setup TTS and STT for LiveKit
        # Get default providers from registry
        tts_config = await get_tts_config()
        stt_config = await get_stt_config()
        
        # Use dummy API key for local services, real key for OpenAI
        tts_api_key = OPENAI_API_KEY if tts_config.get('provider_type') == 'openai' else "dummy-key-for-local"
        stt_api_key = OPENAI_API_KEY if stt_config.get('provider_type') == 'openai' else "dummy-key-for-local"
        
        tts_client = lk_openai.TTS(voice=tts_config['voice'], base_url=tts_config['base_url'], model=tts_config['model'], api_key=tts_api_key)
        stt_client = lk_openai.STT(base_url=stt_config['base_url'], model=stt_config['model'], api_key=stt_api_key)
        
        # Create simple agent that speaks and listens
        class VoiceAgent(Agent):
            def __init__(self):
                super().__init__(
                    instructions="Speak the message and listen for response",
                    stt=stt_client,
                    tts=tts_client,
                    llm=None
                )
                self.response = None
                self.has_spoken = False
                self.speech_start_time = None
                self.min_speech_duration = 3.0  # Minimum 3 seconds of speech
            
            async def on_enter(self):
                await asyncio.sleep(0.5)
                if self.session:
                    await self.session.say(message, allow_interruptions=True)
                    self.has_spoken = True
            
            async def on_user_speech_started(self):
                """Track when user starts speaking"""
                self.speech_start_time = time.time()
                logger.debug("User started speaking")
            
            async def on_user_turn_completed(self, chat_ctx, new_message):
                if self.has_spoken and not self.response and new_message.content:
                    content = new_message.content[0]
                    
                    # Check if speech duration was long enough
                    if self.speech_start_time:
                        speech_duration = time.time() - self.speech_start_time
                        if speech_duration < self.min_speech_duration:
                            logger.debug(f"Speech too short ({speech_duration:.1f}s < {self.min_speech_duration}s), ignoring")
                            return
                    
                    # Filter out common ASR hallucinations
                    content_lower = content.lower().strip()
                    if content_lower in ['bye', 'bye.', 'goodbye', 'goodbye.', '...', 'um', 'uh', 'hmm', 'hm']:
                        logger.debug(f"Filtered out ASR hallucination: '{content}'")
                        return
                    
                    # Check if we have actual words (not just punctuation or numbers)
                    words = content.split()
                    has_real_words = any(word.isalpha() and len(word) > 1 for word in words)
                    if not has_real_words:
                        logger.debug(f"No real words detected in: '{content}'")
                        return
                    
                    # Filter out excessive repetitions (e.g., "45, 45, 45, 45...")
                    if len(words) > 5:
                        # Check if last 5 words are all the same
                        last_words = words[-5:]
                        if len(set(last_words)) == 1:
                            # Trim repetitive ending
                            content = ' '.join(words[:-4])
                            logger.debug(f"Trimmed repetitive ending from ASR output")
                    
                    # Ensure we have meaningful content
                    if content.strip() and len(content.strip()) > 2:
                        self.response = content
                        logger.debug(f"Accepted response: '{content}'")
        
        # Connect and run
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity("voice-mode-bot").with_name("Voice Mode Bot")
        token.with_grants(api.VideoGrants(
            room_join=True, room=room_name,
            can_publish=True, can_subscribe=True,
        ))
        
        room = rtc.Room()
        await room.connect(LIVEKIT_URL, token.to_jwt())
        
        if not room.remote_participants:
            await room.disconnect()
            return "No participants in LiveKit room"
        
        agent = VoiceAgent()
        # Configure Silero VAD with less aggressive settings for better end-of-turn detection
        vad = silero.VAD.load(
            min_speech_duration=0.1,        # Slightly increased - require more speech to start
            min_silence_duration=1.2,       # Increased to 1.2s - wait much longer before ending speech
            prefix_padding_duration=0.5,    # Keep default - padding at speech start
            max_buffered_speech=60.0,       # Keep default - max speech buffer
            activation_threshold=0.35,      # Lowered to 0.35 - more sensitive to soft speech
            sample_rate=16000,              # Standard sample rate
            force_cpu=True                  # Use CPU for compatibility
        )
        session = AgentSession(vad=vad)
        await session.start(room=room, agent=agent)
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            if agent.response:
                await room.disconnect()
                return agent.response
            await asyncio.sleep(0.1)
        
        await room.disconnect()
        return f"No response within {timeout}s"
        
    except Exception as e:
        logger.error(f"LiveKit error: {e}")
        return f"LiveKit error: {str(e)}"


@mcp.tool()
async def converse(
    message: str,
    wait_for_response: Union[bool, str] = True,
    listen_duration: float = DEFAULT_LISTEN_DURATION,
    min_listen_duration: float = 2.0,
    transport: Literal["auto", "local", "livekit"] = "auto",
    room_name: str = "",
    timeout: float = 60.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None,
    tts_model: Optional[str] = None,
    tts_instructions: Optional[str] = None,
    audio_feedback: Optional[Union[bool, str]] = None,
    audio_feedback_style: Optional[str] = None,
    audio_format: Optional[str] = None,
    disable_silence_detection: Union[bool, str] = False,
    speed: Optional[float] = None,
    vad_aggressiveness: Optional[Union[int, str]] = None,
    skip_tts: Optional[Union[bool, str]] = None,
    pip_leading_silence: Optional[float] = None,
    pip_trailing_silence: Optional[float] = None
) -> str:
    """Have a voice conversation - speak a message and optionally listen for response.
    
    🌍 LANGUAGE SUPPORT - ALWAYS SELECT APPROPRIATE VOICE FOR NON-ENGLISH TEXT:
    When speaking non-English languages, you MUST specify the appropriate voice and provider:
    - Spanish: voice="ef_dora" (or "em_alex"), tts_provider="kokoro"
    - French: voice="ff_siwis", tts_provider="kokoro"
    - Italian: voice="if_sara" (or "im_nicola"), tts_provider="kokoro"
    - Portuguese: voice="pf_dora" (or "pm_alex"), tts_provider="kokoro"
    - Chinese: voice="zf_xiaobei" (female) or "zm_yunjian" (male), tts_provider="kokoro"
    - Japanese: voice="jf_alpha" (female) or "jm_kumo" (male), tts_provider="kokoro"
    - Hindi: voice="hf_alpha" (female) or "hm_omega" (male), tts_provider="kokoro"
    
    ⚠️ IMPORTANT: Default voices (OpenAI) will speak non-English text with an American accent.
    Always check the message content and select language-appropriate voices for natural pronunciation.
    
    PRIVACY NOTICE: When wait_for_response is True, this tool will access your microphone
    to record audio for speech-to-text conversion. Audio is processed using the configured
    STT service and is not permanently stored. Do not use upper case except for acronyms as the TTS will spell these out.
    
    Args:
        message: The message to speak
        wait_for_response: Whether to listen for a response after speaking (default: True)
        listen_duration: How long to listen for response in seconds (default: 120.0)
                         The tool handles silence detection well and uses a sensible default.
                         It's unusual to need to set the duration - only override if you have 
                         specific requirements such as:
                         - Silence detection is disabled and you need a specific timeout
                         - You know the response will be exceptionally long (>120s)
                         - You're in a special mode that requires different timing
                         In most cases, just let the default and silence detection handle it.
        min_listen_duration: Minimum time to record before silence detection can stop (default: 2.0)
                             Useful for preventing premature cutoffs when users need thinking time.
                             Examples:
                             - Complex questions: 2-3 seconds
                             - Open-ended prompts: 3-5 seconds  
                             - Quick responses: 0.5-1 second
        transport: Transport method - "auto" (try LiveKit then local), "local" (direct mic), "livekit" (room-based)
        room_name: LiveKit room name (only for livekit transport, auto-discovered if empty)
        timeout: Maximum wait time for response in seconds (LiveKit only) - DEPRECATED: Use listen_duration instead
        voice: Override TTS voice - ONLY specify if user explicitly requests a specific voice
               OR when speaking non-English languages (see LANGUAGE SUPPORT section above).
               Examples: nova, shimmer (OpenAI); af_sky, af_sarah, am_adam (Kokoro)
               IMPORTANT: Never use 'coral' voice.
        tts_provider: TTS provider - ONLY specify if user explicitly requests or for failover testing
                      The system automatically selects based on availability and preferences.
        tts_model: TTS model - ONLY specify for specific features (e.g., gpt-4o-mini-tts for emotions)
                   The system automatically selects the best available model.
                   Options: tts-1, tts-1-hd, gpt-4o-mini-tts (OpenAI); Kokoro uses tts-1
        tts_instructions: Tone/style instructions for gpt-4o-mini-tts model only (e.g., "Speak in a cheerful tone", "Sound angry", "Be extremely sad")
        audio_feedback: Override global audio feedback setting (default: None uses VOICE_MODE_AUDIO_FEEDBACK env var)
        audio_feedback_style: Audio feedback style - "whisper" (default) or "shout" (default: None uses VOICE_MODE_FEEDBACK_STYLE env var)
        audio_format: Override audio format (pcm, mp3, wav, flac, aac, opus) - defaults to VOICEMODE_TTS_AUDIO_FORMAT env var
        disable_silence_detection: Disable silence detection for this interaction only (default: False)
                                   Silence detection automatically stops recording after detecting silence. 
                                   Disable if user reports being cut off, in noisy environments, or for 
                                   use cases like dictation where pauses are expected.
        speed: Speech rate/speed for TTS playback (default: None uses normal speed)
               Values: 0.25 to 4.0 (0.5 = half speed, 2.0 = double speed)
               Supported by both OpenAI and Kokoro TTS providers.
        vad_aggressiveness: Voice Activity Detection aggressiveness level (default: None uses VOICEMODE_VAD_AGGRESSIVENESS env var)
                            Controls how strict the VAD is about filtering out non-speech audio.
                            Values: 0-3 (integer)
                            - 0: Least aggressive filtering - includes more audio, may include non-speech
                            - 1: Slightly stricter filtering
                            - 2: Balanced filtering (default) - good for most environments
                            - 3: Most aggressive filtering - strict speech detection, may cut off soft speech
                            
                            Use lower values (0-1) in quiet environments to catch all speech
                            Use higher values (2-3) in noisy environments to reduce false triggers
        skip_tts: Skip text-to-speech and only show text (default: None uses VOICEMODE_SKIP_TTS env var)
                  When True: Skip TTS for faster response, text-only output
                  When False: Always use TTS regardless of environment setting
                  When None: Follow VOICEMODE_SKIP_TTS environment variable
                  Useful for rapid development iterations or when voice isn't needed
        pip_leading_silence: Override leading silence before chimes (default: None uses VOICEMODE_PIP_LEADING_SILENCE env var)
                             Time in seconds to add before the chime starts (e.g., 1.0 for Bluetooth devices)
        pip_trailing_silence: Override trailing silence after chimes (default: None uses VOICEMODE_PIP_TRAILING_SILENCE env var)
                              Time in seconds to add after the chime ends (e.g., 0.5 to prevent cutoff)
        If wait_for_response is False: Confirmation that message was spoken
        If wait_for_response is True: The voice response received (or error/timeout message)
    
    Examples:
        - Ask a question: converse("What's your name?")  # Let system auto-select voice/model
        - Make a statement and wait: converse("Tell me more about that")  # Auto-selection recommended
        - Just speak without waiting: converse("Goodbye!", wait_for_response=False)
        - User requests specific voice: converse("Hello", voice="nova")  # Only when explicitly requested
        - Need HD quality: converse("High quality speech", tts_model="tts-1-hd")  # Only for specific features
        
    Language-Specific Examples (MUST specify voice & provider):
        - Spanish: converse("¿Cómo estás?", voice="ef_dora", tts_provider="kokoro")
        - French: converse("Bonjour!", voice="ff_siwis", tts_provider="kokoro")
        - Italian: converse("Ciao!", voice="if_sara", tts_provider="kokoro")
        - Chinese: converse("你好", voice="zf_xiaobei", tts_provider="kokoro")
        
    Emotional Speech (Requires OpenAI API):
        - Excitement: converse("We did it!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound extremely excited and celebratory")
        - Sadness: converse("I'm sorry for your loss", tts_model="gpt-4o-mini-tts", tts_instructions="Sound gentle and sympathetic")
        - Urgency: converse("Watch out!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound urgent and concerned")
        - Humor: converse("That's hilarious!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound amused and playful")
        
    Note: Emotional speech uses OpenAI's gpt-4o-mini-tts model and incurs API costs (~$0.02/minute)
    
    Speed Control Examples:
        - Normal speed: converse("This is normal speed")
        - Faster speech: converse("This is faster speech", speed=1.5)
        - Double speed: converse("This is double speed", speed=2.0)
        - Slower speech: converse("This is slower speech", speed=0.8)
        
        Note: Speed control works with both OpenAI and Kokoro TTS providers
    
    VAD Aggressiveness Examples:
        - Quiet room, capture all speech: converse("Let's have a conversation", vad_aggressiveness=0)
        - Normal home/office: converse("Tell me about your day")  # Uses default (2)
        - Noisy cafe/outdoors: converse("Can you hear me?", vad_aggressiveness=3)
        - Balance for most cases: converse("How are you?", vad_aggressiveness=2)
        
        Remember: Lower values (0-1) = more permissive, may detect non-speech as speech
                 Higher values (2-3) = more strict, may miss soft speech or whispers
    
    Parallel Operations Pattern (RECOMMENDED):
        When performing actions that don't require user confirmation, use wait_for_response=False
        to speak while simultaneously executing other tools. This creates natural, flowing conversations.
        
        Pattern: converse("Status update", wait_for_response=False) then immediately run other tools.
        The speech plays while your actions execute in parallel.
        
        Examples:
        - Search narration: converse("Searching for that file", wait_for_response=False) + Grep(...)
        - Processing update: converse("Analyzing the screenshot", wait_for_response=False) + analyze_screenshot(...)
        - Creation status: converse("Creating that document now", wait_for_response=False) + Write(...)
        - Quick confirmation: converse("Done! The file is saved", wait_for_response=False)
        
        Benefits:
        - No dead air during operations
        - User knows what's happening
        - More natural conversation flow
        - Better user experience
        
        When to use parallel pattern:
        - File operations (reading, writing, searching)
        - Data processing (analysis, computation)
        - Status updates during long operations
        - Confirmations that don't need response
        
        When NOT to use parallel pattern:
        - Questions requiring answers
        - Confirmations needing user approval
        - Error messages needing acknowledgment
        - End of conversation farewells (unless doing cleanup)
    
    Skip TTS Examples:
        - Fast iteration mode: converse("Processing your request", skip_tts=True)  # Text only, no voice
        - Important announcement: converse("Warning: System will restart", skip_tts=False)  # Always use voice
        - Quick confirmation: converse("Done!", skip_tts=True, wait_for_response=False)  # Fast text-only
        - Follow user preference: converse("Hello")  # Uses VOICEMODE_SKIP_TTS setting
    """
    # Convert string booleans to actual booleans
    if isinstance(wait_for_response, str):
        wait_for_response = wait_for_response.lower() in ('true', '1', 'yes', 'on')
    if isinstance(disable_silence_detection, str):
        disable_silence_detection = disable_silence_detection.lower() in ('true', '1', 'yes', 'on')
    if isinstance(audio_feedback, str):
        audio_feedback = audio_feedback.lower() in ('true', '1', 'yes', 'on')
    if skip_tts is not None and isinstance(skip_tts, str):
        skip_tts = skip_tts.lower() in ('true', '1', 'yes', 'on')
    
    # Convert vad_aggressiveness to integer if provided as string
    if vad_aggressiveness is not None and isinstance(vad_aggressiveness, str):
        try:
            vad_aggressiveness = int(vad_aggressiveness)
            # Validation will happen later in the function
        except ValueError:
            logger.warning(f"Invalid VAD aggressiveness value '{vad_aggressiveness}', using default")
            vad_aggressiveness = None
    
    # Determine whether to skip TTS
    if skip_tts is not None:
        # Parameter explicitly set, use it
        should_skip_tts = skip_tts
    else:
        # Use global setting
        should_skip_tts = SKIP_TTS
    
    # Convert string speed to float
    if speed is not None and isinstance(speed, str):
        try:
            speed = float(speed)
        except ValueError:
            return f"❌ Error: speed must be a number (got '{speed}')"
    
    # Validate speed parameter range
    if speed is not None:
        if not (0.25 <= speed <= 4.0):
            return f"❌ Error: speed must be between 0.25 and 4.0 (got {speed})"
    
    logger.info(f"Converse: '{message[:50]}{'...' if len(message) > 50 else ''}' (wait_for_response: {wait_for_response})")
    
    # Validate vad_aggressiveness parameter
    if vad_aggressiveness is not None:
        if not isinstance(vad_aggressiveness, int) or vad_aggressiveness < 0 or vad_aggressiveness > 3:
            return f"Error: vad_aggressiveness must be an integer between 0 and 3 (got {vad_aggressiveness})"
    
    # Validate duration parameters
    if wait_for_response:
        if min_listen_duration < 0:
            return "❌ Error: min_listen_duration cannot be negative"
        if listen_duration <= 0:
            return "❌ Error: listen_duration must be positive"
        if min_listen_duration > listen_duration:
            logger.warning(f"min_listen_duration ({min_listen_duration}s) is greater than listen_duration ({listen_duration}s), using listen_duration as minimum")
            min_listen_duration = listen_duration
    
    # Check if FFmpeg is available
    ffmpeg_available = getattr(voice_mode.config, 'FFMPEG_AVAILABLE', True)  # Default to True if not set
    if not ffmpeg_available:
        from ..utils.ffmpeg_check import get_install_instructions
        error_msg = (
            "FFmpeg is required for voice features but is not installed.\n\n"
            f"{get_install_instructions()}\n\n"
            "Voice features cannot work without FFmpeg."
        )
        logger.error(error_msg)
        return f"❌ Error: {error_msg}"
    
    # Run startup initialization if needed
    await startup_initialization()
    
    # Refresh audio device cache to pick up any device changes (AirPods, etc.)
    # This takes ~1ms and ensures we use the current default device
    import sounddevice as sd
    sd._terminate()
    sd._initialize()
    
    # Get event logger and start session
    event_logger = get_event_logger()
    session_id = None
    
    # Check time since last session for AI thinking time
    global last_session_end_time
    current_time = time.time()
    
    if last_session_end_time and wait_for_response:
        time_since_last = current_time - last_session_end_time
        logger.info(f"Time since last session: {time_since_last:.1f}s (AI thinking time)")
    
    # For conversations with responses, create a session
    if event_logger and wait_for_response:
        session_id = event_logger.start_session()
        # Log the time since last session as an event
        if last_session_end_time:
            event_logger.log_event("TIME_SINCE_LAST_SESSION", {
                "seconds": time_since_last
            })
    
    # Log tool request start (after session is created)
    if event_logger:
        # If we have a session, the event will be associated with it
        log_tool_request_start("converse", {
            "wait_for_response": wait_for_response,
            "listen_duration": listen_duration if wait_for_response else None
        })
    
    # Track execution time and resources
    start_time = time.time()
    if DEBUG:
        import resource
        start_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.debug(f"Starting converse - Memory: {start_memory} KB")
    
    result = None
    success = False
    
    try:
        # If not waiting for response, just speak and return
        if not wait_for_response:
            try:
                async with audio_operation_lock:
                    if should_skip_tts:
                        # Skip TTS entirely
                        success = True
                        tts_metrics = {
                            'ttfa': 0,
                            'generation': 0,
                            'playback': 0,
                            'total': 0
                        }
                        tts_config = {'provider': 'no-op', 'voice': 'none'}
                    else:
                        success, tts_metrics, tts_config = await text_to_speech_with_failover(
                            message=message,
                            voice=voice,
                            model=tts_model,
                            instructions=tts_instructions,
                            audio_format=audio_format,
                            initial_provider=tts_provider,
                            speed=speed
                        )
                    
                # Include timing info if available
                timing_info = ""
                timing_str = ""
                if success and tts_metrics:
                    timing_info = f" (gen: {tts_metrics.get('generation', 0):.1f}s, play: {tts_metrics.get('playback', 0):.1f}s)"
                    # Create timing string for statistics
                    timing_parts = []
                    if 'ttfa' in tts_metrics:
                        timing_parts.append(f"ttfa {tts_metrics['ttfa']:.1f}s")
                    if 'generation' in tts_metrics:
                        timing_parts.append(f"tts_gen {tts_metrics['generation']:.1f}s")
                    if 'playback' in tts_metrics:
                        timing_parts.append(f"tts_play {tts_metrics['playback']:.1f}s")
                    timing_str = ", ".join(timing_parts)
                
                result = f"✓ Message spoken successfully{timing_info}" if success else "✗ Failed to speak message"
                
                # Track statistics for speak-only interaction
                track_voice_interaction(
                    message=message,
                    response="[speak-only]",
                    timing_str=timing_str if success else None,
                    transport="speak-only",
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=success,
                    error_message=None if success else "TTS failed"
                )
                
                # Log TTS to JSONL for speak-only mode
                if success:
                    try:
                        conversation_logger = get_conversation_logger()
                        conversation_logger.log_tts(
                            text=message,
                            audio_file=os.path.basename(tts_metrics.get('audio_path')) if tts_metrics.get('audio_path') else None,
                            model=tts_config.get('model') if tts_config else tts_model,
                            voice=tts_config.get('voice') if tts_config else voice,
                            provider=tts_config.get('provider') if tts_config else (tts_provider if tts_provider else 'openai'),
                            provider_url=tts_config.get('base_url') if tts_config else None,
                            provider_type=tts_config.get('provider_type') if tts_config else None,
                            timing=timing_str,
                            audio_format=audio_format,
                            transport="speak-only",
                            # Add timing metrics
                            time_to_first_audio=tts_metrics.get('ttfa') if tts_metrics else None,
                            generation_time=tts_metrics.get('generation') if tts_metrics else None,
                            playback_time=tts_metrics.get('playback') if tts_metrics else None
                        )
                    except Exception as e:
                        logger.error(f"Failed to log TTS to JSONL: {e}")
                
                logger.info(f"Speak-only result: {result}")
                # success is already set correctly from TTS result
                return result
            except Exception as e:
                logger.error(f"Speak error: {e}")
                error_msg = f"Error: {str(e)}"
                
                # Track failed speak-only interaction
                track_voice_interaction(
                    message=message,
                    response="[error]",
                    timing_str=None,
                    transport="speak-only",
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=False,
                    error_message=str(e)
                )
                
                logger.error(f"Returning error: {error_msg}")
                result = error_msg
                return result
        
        # Otherwise, speak and then listen for response
        # Determine transport method
        if transport == "auto":
            transport_start = time.time()
            logger.debug("Starting transport auto-selection")
            
            if await check_livekit_available():
                transport = "livekit"
                transport_duration = time.time() - transport_start
                logger.info(f"Auto-selected LiveKit transport (selection took {transport_duration:.3f}s)")
            else:
                transport = "local"
                transport_duration = time.time() - transport_start
                logger.info(f"Auto-selected local transport (selection took {transport_duration:.3f}s)")
        
        if transport == "livekit":
            # For LiveKit, use the existing function but with the message parameter
            # Use listen_duration instead of timeout for consistent behavior
            livekit_result = await livekit_converse(message, room_name, listen_duration)
            
            # Track LiveKit interaction (simplified since we don't have detailed timing)
            success = not livekit_result.startswith("Error:") and not livekit_result.startswith("No ")
            track_voice_interaction(
                message=message,
                response=livekit_result,
                timing_str=None,  # LiveKit doesn't provide detailed timing
                transport="livekit",
                voice_provider="livekit",  # LiveKit manages its own providers
                voice_name=voice,
                model=tts_model,
                success=success,
                error_message=livekit_result if not success else None
            )
            
            result = livekit_result
            success = not livekit_result.startswith("Error:") and not livekit_result.startswith("No ")
            return result
        
        elif transport == "local":
            # Local microphone approach with timing
            timings = {}
            try:
                async with audio_operation_lock:
                    # Speak the message
                    tts_start = time.perf_counter()
                    if should_skip_tts:
                        # Skip TTS entirely for faster response
                        tts_success = True
                        tts_metrics = {
                            'ttfa': 0,
                            'generation': 0,
                            'playback': 0,
                            'total': 0
                        }
                        tts_config = {'provider': 'no-op', 'voice': 'none'}
                    else:
                        tts_success, tts_metrics, tts_config = await text_to_speech_with_failover(
                            message=message,
                            voice=voice,
                            model=tts_model,
                            instructions=tts_instructions,
                            audio_format=audio_format,
                            initial_provider=tts_provider,
                            speed=speed
                        )
                    
                    # Add TTS sub-metrics
                    if tts_metrics:
                        timings['ttfa'] = tts_metrics.get('ttfa', 0)
                        timings['tts_gen'] = tts_metrics.get('generation', 0)
                        timings['tts_play'] = tts_metrics.get('playback', 0)
                    timings['tts_total'] = time.perf_counter() - tts_start
                    
                    # Log TTS immediately after it completes
                    if tts_success:
                        try:
                            # Format TTS timing
                            tts_timing_parts = []
                            if 'ttfa' in timings:
                                tts_timing_parts.append(f"ttfa {timings['ttfa']:.1f}s")
                            if 'tts_gen' in timings:
                                tts_timing_parts.append(f"gen {timings['tts_gen']:.1f}s")
                            if 'tts_play' in timings:
                                tts_timing_parts.append(f"play {timings['tts_play']:.1f}s")
                            tts_timing_str = ", ".join(tts_timing_parts) if tts_timing_parts else None
                            
                            conversation_logger = get_conversation_logger()
                            conversation_logger.log_tts(
                                text=message,
                                audio_file=os.path.basename(tts_metrics.get('audio_path')) if tts_metrics and tts_metrics.get('audio_path') else None,
                                model=tts_config.get('model') if tts_config else tts_model,
                                voice=tts_config.get('voice') if tts_config else voice,
                                provider=tts_config.get('provider') if tts_config else (tts_provider if tts_provider else 'openai'),
                                provider_url=tts_config.get('base_url') if tts_config else None,
                                provider_type=tts_config.get('provider_type') if tts_config else None,
                                timing=tts_timing_str,
                                audio_format=audio_format,
                                transport=transport,
                                # Add timing metrics
                                time_to_first_audio=timings.get('ttfa') if timings else None,
                                generation_time=timings.get('tts_gen') if timings else None,
                                playback_time=timings.get('tts_play') if timings else None,
                                total_turnaround_time=timings.get('total') if timings else None
                            )
                        except Exception as e:
                            logger.error(f"Failed to log TTS to JSONL: {e}")
                    
                    if not tts_success:
                        # Check if we have config info that might indicate why it failed
                        if tts_config and 'openai.com' in tts_config.get('base_url', ''):
                            # Check if API key is missing for OpenAI
                            from voice_mode.config import OPENAI_API_KEY
                            if not OPENAI_API_KEY:
                                result = "Error: Could not speak message. OpenAI API key is not set. Please set OPENAI_API_KEY environment variable or use local services (Kokoro TTS)."
                            else:
                                result = "Error: Could not speak message. TTS request to OpenAI failed. Please check your API key and network connection."
                        else:
                            result = "Error: Could not speak message. All TTS providers failed. Check that local services are running or set OPENAI_API_KEY for cloud fallback."
                        return result
                    
                    # Brief pause before listening
                    await asyncio.sleep(0.5)
                    
                    # Play "listening" feedback sound
                    await play_audio_feedback(
                        "listening", 
                        openai_clients, 
                        audio_feedback, 
                        audio_feedback_style or "whisper",
                        pip_leading_silence=pip_leading_silence,
                        pip_trailing_silence=pip_trailing_silence
                    )
                    
                    # Record response
                    logger.info(f"🎤 Listening for {listen_duration} seconds...")
                    
                    # Log recording start
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_START)
                    
                    record_start = time.perf_counter()
                    logger.debug(f"About to call record_audio_with_silence_detection with duration={listen_duration}, disable_silence_detection={disable_silence_detection}, min_duration={min_listen_duration}, vad_aggressiveness={vad_aggressiveness}")
                    audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio_with_silence_detection, listen_duration, disable_silence_detection, min_listen_duration, vad_aggressiveness
                    )
                    timings['record'] = time.perf_counter() - record_start
                    
                    # Log recording end
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_END, {
                            "duration": timings['record'],
                            "samples": len(audio_data)
                        })
                    
                    # Play "finished" feedback sound
                    await play_audio_feedback(
                        "finished", 
                        openai_clients, 
                        audio_feedback, 
                        audio_feedback_style or "whisper",
                        pip_leading_silence=pip_leading_silence,
                        pip_trailing_silence=pip_trailing_silence
                    )
                    
                    # Mark the end of recording - this is when user expects response to start
                    user_done_time = time.perf_counter()
                    logger.info(f"Recording finished at {user_done_time - tts_start:.1f}s from start")
                    
                    if len(audio_data) == 0:
                        result = "Error: Could not record audio"
                        return result
                    
                    # Check if no speech was detected
                    if not speech_detected:
                        logger.info("No speech detected during recording - skipping STT processing")
                        response_text = None
                        timings['stt'] = 0.0
                        
                        # Still save the audio if configured
                        if SAVE_AUDIO and AUDIO_DIR:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            audio_path = os.path.join(AUDIO_DIR, f"no_speech_{timestamp}.wav")
                            write(audio_path, SAMPLE_RATE, audio_data)
                            logger.debug(f"Saved no-speech audio to: {audio_path}")
                    else:
                        # Convert to text
                        # Log STT start
                        if event_logger:
                            event_logger.log_event(event_logger.STT_START)
                        
                        stt_start = time.perf_counter()
                        response_text = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport)
                        timings['stt'] = time.perf_counter() - stt_start
                    
                    # Log STT complete
                    if event_logger:
                        if response_text:
                            event_logger.log_event(event_logger.STT_COMPLETE, {"text": response_text})
                        else:
                            event_logger.log_event(event_logger.STT_NO_SPEECH)
                    
                    # Log STT immediately after it completes (even if no speech detected)
                    try:
                        # Format STT timing
                        stt_timing_parts = []
                        if 'record' in timings:
                            stt_timing_parts.append(f"record {timings['record']:.1f}s")
                        if 'stt' in timings:
                            stt_timing_parts.append(f"stt {timings['stt']:.1f}s")
                        stt_timing_str = ", ".join(stt_timing_parts) if stt_timing_parts else None
                        
                        conversation_logger = get_conversation_logger()
                        # Get STT config for provider info
                        stt_config = await get_stt_config()
                        
                        conversation_logger.log_stt(
                            text=response_text if response_text else "[no speech detected]",
                            model=stt_config.get('model', 'whisper-1'),
                            provider=stt_config.get('provider', 'openai'),
                            provider_url=stt_config.get('base_url'),
                            provider_type=stt_config.get('provider_type'),
                            audio_format='mp3',
                            transport=transport,
                            timing=stt_timing_str,
                            silence_detection={
                                "enabled": not (DISABLE_SILENCE_DETECTION or disable_silence_detection),
                                "vad_aggressiveness": VAD_AGGRESSIVENESS,
                                "silence_threshold_ms": SILENCE_THRESHOLD_MS
                            },
                            # Add timing metrics
                            transcription_time=timings.get('stt'),
                            total_turnaround_time=None  # Will be calculated and added later
                        )
                    except Exception as e:
                        logger.error(f"Failed to log STT to JSONL: {e}")
                
                # Calculate total time (use tts_total instead of sub-metrics)
                main_timings = {k: v for k, v in timings.items() if k in ['tts_total', 'record', 'stt']}
                total_time = sum(main_timings.values())
                
                # Format timing strings separately for TTS and STT
                tts_timing_parts = []
                stt_timing_parts = []
                
                # TTS timings
                if 'ttfa' in timings:
                    tts_timing_parts.append(f"ttfa {timings['ttfa']:.1f}s")
                if 'tts_gen' in timings:
                    tts_timing_parts.append(f"gen {timings['tts_gen']:.1f}s")
                if 'tts_play' in timings:
                    tts_timing_parts.append(f"play {timings['tts_play']:.1f}s")
                
                # STT timings
                if 'record' in timings:
                    stt_timing_parts.append(f"record {timings['record']:.1f}s")
                if 'stt' in timings:
                    stt_timing_parts.append(f"stt {timings['stt']:.1f}s")
                
                tts_timing_str = ", ".join(tts_timing_parts) if tts_timing_parts else None
                stt_timing_str = ", ".join(stt_timing_parts) if stt_timing_parts else None
                
                # Keep combined timing for backward compatibility in result message
                all_timing_parts = []
                if tts_timing_parts:
                    all_timing_parts.extend(tts_timing_parts)
                if stt_timing_parts:
                    all_timing_parts.extend(stt_timing_parts)
                timing_str = ", ".join(all_timing_parts) + f", total {total_time:.1f}s"
                
                # Track statistics for full conversation interaction
                actual_response = response_text or "[no speech detected]"
                track_voice_interaction(
                    message=message,
                    response=actual_response,
                    timing_str=timing_str,
                    transport=transport,
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=bool(response_text),  # Success if we got a response
                    error_message=None if response_text else "No speech detected"
                )
                
                # End event logging session
                if event_logger and session_id:
                    event_logger.end_session()
                
                if response_text:
                    # Save conversation transcription if enabled
                    if SAVE_TRANSCRIPTIONS:
                        conversation_text = f"Assistant: {message}\n\nUser: {response_text}"
                        metadata = {
                            "type": "conversation",
                            "transport": transport,
                            "voice": voice,
                            "model": tts_model,
                            "stt_model": "whisper-1",  # Default STT model
                            "timing": timing_str,
                            "timestamp": datetime.now().isoformat()
                        }
                        save_transcription(conversation_text, prefix="conversation", metadata=metadata)
                    
                    # Logging already done immediately after TTS and STT complete
                    
                    result = f"Voice response: {response_text} | Timing: {timing_str}"
                    success = True
                else:
                    result = f"No speech detected | Timing: {timing_str}"
                    success = True  # Not an error, just no speech
                return result
                    
            except Exception as e:
                logger.error(f"Local voice error: {e}")
                if DEBUG:
                    logger.error(f"Traceback: {traceback.format_exc()}")
                
                # Track failed conversation interaction
                track_voice_interaction(
                    message=message,
                    response="[error]",
                    timing_str=None,
                    transport=transport,
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=False,
                    error_message=str(e)
                )
                
                result = f"Error: {str(e)}"
                return result
            
        else:
            result = f"Unknown transport: {transport}"
            return result
            
    except Exception as e:
        logger.error(f"Unexpected error in converse: {e}")
        if DEBUG:
            logger.error(f"Full traceback: {traceback.format_exc()}")
        result = f"Unexpected error: {str(e)}"
        return result
        
    finally:
        # Log tool request end
        if event_logger:
            log_tool_request_end("converse", success=success)
        
        # Update last session end time for tracking AI thinking time
        if wait_for_response:
            last_session_end_time = time.time()
        
        # Log execution metrics
        elapsed = time.time() - start_time
        logger.info(f"Converse completed in {elapsed:.2f}s")
        
        if DEBUG:
            import resource
            import gc
            end_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory_delta = end_memory - start_memory
            logger.debug(f"Memory delta: {memory_delta} KB (start: {start_memory}, end: {end_memory})")
            
            # Force garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collected {collected} objects")




