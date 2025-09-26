"""
Core functionality for voice-mode.

This module contains the main functions used by the voice-mode script,
extracted to allow for easier testing and reuse.
"""

import asyncio
import logging
import os
import tempfile
import gc
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from pydub import AudioSegment
from openai import AsyncOpenAI
from .provider_discovery import is_local_provider
import httpx

from .config import SAMPLE_RATE
from .utils import (
    get_event_logger,
    log_tts_start,
    log_tts_first_audio
)

logger = logging.getLogger("voicemode")


def get_audio_path(filename: str, base_dir: Path, timestamp: Optional[datetime] = None) -> Path:
    """Get full audio path with year/month structure for a given filename.
    
    Args:
        filename: Just the filename (e.g., "20250728_123456_789_abc123_tts.wav")
        base_dir: Base audio directory
        timestamp: Optional timestamp to determine year/month. If not provided, 
                   will be extracted from filename or use current date.
        
    Returns:
        Full path with year/month structure
    """
    # Try to extract date from filename if timestamp not provided
    if timestamp is None:
        try:
            # Extract YYYYMMDD from filename like "20250728_123456_789_abc123_tts.wav"
            date_str = filename.split('_')[0]
            if len(date_str) == 8 and date_str.isdigit():
                year = int(date_str[:4])
                month = int(date_str[4:6])
                timestamp = datetime(year, month, 1)
        except (IndexError, ValueError):
            pass
    
    # Fall back to current date if still no timestamp
    if timestamp is None:
        timestamp = datetime.now()
    
    # Build path with year/month structure
    year_dir = base_dir / str(timestamp.year)
    month_dir = year_dir / f"{timestamp.month:02d}"
    
    return month_dir / filename


def get_debug_filename(prefix: str, extension: str, conversation_id: Optional[str] = None) -> str:
    """Generate debug filename with timestamp and optional conversation ID.
    
    Args:
        prefix: File prefix (e.g., 'tts', 'stt')
        extension: File extension (e.g., 'mp3', 'wav')
        conversation_id: Optional conversation ID to include in filename
        
    Returns:
        Filename in format: timestamp_conv_id_prefix.extension
        or timestamp_prefix.extension if no conversation ID
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
    
    if conversation_id:
        # Extract just the suffix part of conversation ID for brevity
        # conv_20250628_233802_4t8u0f -> 4t8u0f
        conv_suffix = conversation_id.split('_')[-1] if '_' in conversation_id else conversation_id
        return f"{timestamp}_{conv_suffix}_{prefix}.{extension}"
    else:
        return f"{timestamp}-{prefix}.{extension}"


def save_debug_file(data: bytes, prefix: str, extension: str, debug_dir: Path, debug: bool = False, conversation_id: Optional[str] = None) -> Optional[str]:
    """Save debug file if debug mode is enabled.
    
    Args:
        data: File data to save
        prefix: File prefix (e.g., 'tts', 'stt')
        extension: File extension
        debug_dir: Directory to save files in
        debug: Whether to save the file
        conversation_id: Optional conversation ID to include in filename
        
    Returns:
        Path to saved file or None
    """
    if not debug:
        return None
    
    try:
        # Get current date for directory structure
        now = datetime.now()
        year_dir = debug_dir / str(now.year)
        month_dir = year_dir / f"{now.month:02d}"
        
        # Create year/month directory structure
        month_dir.mkdir(parents=True, exist_ok=True)
        
        filename = get_debug_filename(prefix, extension, conversation_id)
        filepath = month_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(data)
        
        logger.debug(f"Debug file saved: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Failed to save debug file: {e}")
        return None


def get_openai_clients(api_key: str, stt_base_url: Optional[str] = None, tts_base_url: Optional[str] = None) -> dict:
    """Initialize OpenAI clients for STT and TTS with connection pooling"""
    # Configure timeouts and connection pooling
    http_client_config = {
        'timeout': httpx.Timeout(30.0, connect=5.0),
        'limits': httpx.Limits(max_keepalive_connections=5, max_connections=10),
    }

    # Disable retries for local endpoints - they either work or don't
    stt_max_retries = 0 if is_local_provider(stt_base_url) else 2
    tts_max_retries = 0 if is_local_provider(tts_base_url) else 2

    # Create HTTP clients
    stt_http_client = httpx.AsyncClient(**http_client_config)
    tts_http_client = httpx.AsyncClient(**http_client_config)

    return {
        'stt': AsyncOpenAI(
            api_key=api_key,
            base_url=stt_base_url,
            http_client=stt_http_client,
            max_retries=stt_max_retries
        ),
        'tts': AsyncOpenAI(
            api_key=api_key,
            base_url=tts_base_url,
            http_client=tts_http_client,
            max_retries=tts_max_retries
        )
    }


async def text_to_speech(
    text: str,
    openai_clients: dict,
    tts_model: str,
    tts_voice: str,
    tts_base_url: str,
    debug: bool = False,
    debug_dir: Optional[Path] = None,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    client_key: str = 'tts',
    instructions: Optional[str] = None,
    audio_format: Optional[str] = None,
    conversation_id: Optional[str] = None,
    speed: Optional[float] = None
) -> tuple[bool, Optional[dict]]:
    """Convert text to speech and play it.
    
    Returns:
        tuple: (success: bool, metrics: dict) where metrics contains 'generation' and 'playback' times
    """
    import time
    
    logger.info(f"TTS: Converting text to speech: '{text[:100]}{'...' if len(text) > 100 else ''}'")
    
    # Always log the TTS configuration details
    logger.info(f"TTS Request Details:")
    logger.info(f"  • Endpoint URL: {tts_base_url}")
    logger.info(f"  • Model: {tts_model}")
    logger.info(f"  • Voice: {tts_voice}")
    logger.info(f"  • Format: {audio_format or 'default'}")
    logger.info(f"  • Client Key: {client_key}")
    if instructions:
        logger.info(f"  • Instructions: {instructions}")
    
    if debug:
        logger.debug(f"TTS full text: {text}")
        logger.debug(f"Debug mode enabled, will save audio files")
    
    metrics = {}
    
    # Log TTS start event
    event_logger = get_event_logger()
    if event_logger:
        event_logger.log_event(event_logger.TTS_START, {
            "message": text[:200],  # Truncate for log
            "voice": tts_voice,
            "model": tts_model
        })
    
    try:
        # Import config for audio format
        from .config import (
            TTS_AUDIO_FORMAT, validate_audio_format, get_audio_loader_for_format,
            STREAMING_ENABLED, STREAM_CHUNK_SIZE, SAMPLE_RATE
        )
        
        # Determine provider from base URL (simple heuristic)
        if "openai" in tts_base_url:
            provider = "openai"
        else:
            provider = "kokoro"
        
        logger.info(f"  • Detected Provider: {provider} (based on URL: {tts_base_url})")
        
        # Validate format for provider
        # Use provided format or fall back to configured default
        format_to_use = audio_format if audio_format else TTS_AUDIO_FORMAT
        validated_format = validate_audio_format(format_to_use, provider, "tts")
        
        logger.debug("Making TTS API request...")
        # Build request parameters
        request_params = {
            "model": tts_model,
            "input": text,
            "voice": tts_voice,
            "response_format": validated_format
        }
        
        # Add instructions if provided and model supports it
        if instructions and tts_model == "gpt-4o-mini-tts":
            request_params["instructions"] = instructions
            logger.debug(f"TTS instructions: {instructions}")
        
        # Add speed parameter if provided
        if speed is not None:
            request_params["speed"] = speed
            logger.info(f"  • Speed: {speed}x")
        
        # Track generation time
        generation_start = time.perf_counter()
        
        # Check if streaming is enabled and format is supported
        use_streaming = STREAMING_ENABLED and validated_format in ["opus", "mp3", "pcm", "wav"]
        
        # Allow streaming with the requested format
        # PCM has lowest latency but highest bandwidth
        # Opus/MP3 have higher latency but lower bandwidth
        if use_streaming:
            logger.info(f"Using streaming with {validated_format} format")
        
        if use_streaming:
            # Use streaming playback
            logger.info(f"Using streaming playback for {validated_format}")
            from .streaming import stream_tts_audio
            
            # Pass the client directly
            success, stream_metrics = await stream_tts_audio(
                text=text,
                openai_client=openai_clients[client_key],
                request_params=request_params,
                debug=debug,
                save_audio=save_audio,
                audio_dir=audio_dir,
                conversation_id=conversation_id
            )
            
            if success:
                metrics['ttfa'] = stream_metrics.ttfa
                metrics['generation'] = stream_metrics.generation_time
                metrics['playback'] = stream_metrics.playback_time - stream_metrics.generation_time
                
                # Pass through audio path if it exists
                if stream_metrics.audio_path:
                    metrics['audio_path'] = stream_metrics.audio_path
                
                logger.info(f"✓ TTS streamed successfully - TTFA: {metrics['ttfa']:.3f}s")
                
                # Save debug files if needed (we'd need to capture the full audio)
                # For now, skip debug saving in streaming mode
                
                return True, metrics
            else:
                logger.warning("Streaming failed, falling back to buffered playback")
                # Continue with regular buffered playback
        
        # Original buffered playback
        # Use context manager to ensure response is properly closed
        async with openai_clients[client_key].audio.speech.with_streaming_response.create(
            **request_params
        ) as response:
            # Read the entire response content
            response_content = await response.read()
            
        metrics['generation'] = time.perf_counter() - generation_start
        logger.debug(f"TTS API response received, content length: {len(response_content)} bytes")
        
        # Log TTS first audio event
        if event_logger:
            event_logger.log_event(event_logger.TTS_FIRST_AUDIO)
        
        # Save debug file if enabled
        if debug and debug_dir:
            debug_path = save_debug_file(response_content, "tts-output", validated_format, debug_dir, debug, conversation_id)
            if debug_path:
                logger.info(f"TTS debug audio saved to: {debug_path}")
        
        # Save audio file if audio saving is enabled
        audio_path = None
        if save_audio and audio_dir:
            audio_path = save_debug_file(response_content, "tts", validated_format, audio_dir, True, conversation_id)
            if audio_path:
                logger.info(f"TTS audio saved to: {audio_path}")
                # Store audio path in metrics for the caller
                metrics['audio_path'] = audio_path
        
        # Play audio
        playback_start = time.perf_counter()
        # For buffered playback, TTFA includes both API response time and audio initialization
        # This is the time from API call to when audio actually starts playing
        # Note: In voice-chat flows, there's additional latency from LLM processing that's not captured here
        metrics['ttfa'] = playback_start - generation_start
        
        with tempfile.NamedTemporaryFile(suffix=f'.{validated_format}', delete=False) as tmp_file:
            tmp_file.write(response_content)
            tmp_file.flush()
            
            logger.debug(f"Audio written to temp file: {tmp_file.name}")
            
            try:
                # Load audio file based on format
                logger.debug(f"Loading {validated_format.upper()} audio...")
                
                # Get appropriate loader for format
                loader = get_audio_loader_for_format(validated_format)
                if not loader:
                    logger.error(f"No loader available for format: {validated_format}")
                    # Fallback to generic loader
                    audio = AudioSegment.from_file(tmp_file.name, format=validated_format)
                else:
                    # Special handling for PCM which needs parameters
                    if validated_format == "pcm":
                        # Assume 16-bit PCM at standard rate
                        audio = loader(
                            tmp_file.name,
                            sample_width=2,  # 16-bit
                            frame_rate=SAMPLE_RATE,
                            channels=1
                        )
                    else:
                        audio = loader(tmp_file.name)
                
                logger.debug(f"Audio loaded - Duration: {len(audio)}ms, Channels: {audio.channels}, Frame rate: {audio.frame_rate}")
                
                # Convert to numpy array
                logger.debug("Converting to numpy array...")
                samples = np.array(audio.get_array_of_samples())
                if audio.channels == 2:
                    samples = samples.reshape((-1, 2))
                    logger.debug("Reshaped for stereo")
                
                # Convert to float32 for sounddevice
                samples = samples.astype(np.float32) / 32767.0
                logger.debug(f"Audio converted to float32, shape: {samples.shape}")
                
                # Check audio devices
                if debug:
                    try:
                        import sounddevice as sd
                        devices = sd.query_devices()
                        default_output = sd.default.device[1]
                        logger.debug(f"Default output device: {default_output} - {devices[default_output]['name'] if default_output is not None else 'None'}")
                    except Exception as dev_e:
                        logger.error(f"Error querying audio devices: {dev_e}")
                
                logger.debug(f"Playing audio with sounddevice at {audio.frame_rate}Hz...")
                
                # Try to ensure sounddevice doesn't interfere with stdout/stderr
                try:
                    import sounddevice as sd
                    import sys
                    
                    # Save current stdio state
                    original_stdin = sys.stdin
                    original_stdout = sys.stdout
                    original_stderr = sys.stderr
                    
                    try:
                        # Force initialization before playing
                        sd.default.samplerate = audio.frame_rate
                        sd.default.channels = audio.channels
                        
                        # Log TTS playback start event
                        if event_logger:
                            event_logger.log_event(event_logger.TTS_PLAYBACK_START)
                        
                        # Add configurable silence at the beginning to prevent clipping
                        from .config import PIP_LEADING_SILENCE
                        silence_duration = PIP_LEADING_SILENCE  # seconds
                        silence_samples = int(audio.frame_rate * silence_duration)
                        # Match the shape of the samples array exactly
                        if samples.ndim == 1:
                            silence = np.zeros(silence_samples, dtype=np.float32)
                            samples_with_buffer = np.concatenate([silence, samples])
                        else:
                            silence = np.zeros((silence_samples, samples.shape[1]), dtype=np.float32)
                            samples_with_buffer = np.vstack([silence, samples])
                        
                        sd.play(samples_with_buffer, audio.frame_rate)
                        sd.wait()
                        
                        # Log TTS playback end event
                        if event_logger:
                            event_logger.log_event(event_logger.TTS_PLAYBACK_END)
                        
                        logger.info("✓ TTS played successfully")
                        os.unlink(tmp_file.name)
                        metrics['playback'] = time.perf_counter() - playback_start
                        return True, metrics
                    finally:
                        # Restore stdio if it was changed
                        if sys.stdin != original_stdin:
                            sys.stdin = original_stdin
                        if sys.stdout != original_stdout:
                            sys.stdout = original_stdout
                        if sys.stderr != original_stderr:
                            sys.stderr = original_stderr
                except Exception as sd_error:
                    logger.error(f"Sounddevice playback failed: {sd_error}")
                    
                    # Fallback to file-based playback methods
                    logger.info("Attempting alternative playback methods...")
                    
                    # Try using PyDub's playback (requires simpleaudio or pyaudio)
                    try:
                        from pydub.playback import play as pydub_play
                        logger.debug("Using PyDub playback...")
                        pydub_play(audio)
                        logger.info("✓ TTS played successfully with PyDub")
                        os.unlink(tmp_file.name)
                        metrics['playback'] = time.perf_counter() - playback_start
                        return True, metrics
                    except Exception as pydub_error:
                        logger.error(f"PyDub playback failed: {pydub_error}")
                    
                    # Last resort: save to user's home directory for manual playback
                    try:
                        fallback_path = Path.home() / f"voice-mode-audio-{datetime.now().strftime('%Y%m%d_%H%M%S')}.{validated_format}"
                        import shutil
                        shutil.copy(tmp_file.name, fallback_path)
                        logger.warning(f"Audio saved to {fallback_path} for manual playback")
                        os.unlink(tmp_file.name)
                        metrics['playback'] = time.perf_counter() - playback_start
                        return False, metrics
                    except Exception as save_error:
                        logger.error(f"Failed to save audio file: {save_error}")
                        os.unlink(tmp_file.name)
                        metrics['playback'] = time.perf_counter() - playback_start
                        return False, metrics
                
            except Exception as e:
                logger.error(f"Error playing audio: {e}")
                logger.error(f"Audio format - Channels: {audio.channels if 'audio' in locals() else 'unknown'}, Frame rate: {audio.frame_rate if 'audio' in locals() else 'unknown'}")
                logger.error(f"Samples shape: {samples.shape if 'samples' in locals() else 'unknown'}")
                
                # Try alternative playback method in debug mode
                if debug:
                    try:
                        logger.debug("Attempting alternative playback with system command...")
                        import subprocess
                        result = subprocess.run(['paplay', tmp_file.name], capture_output=True, timeout=10)
                        if result.returncode == 0:
                            logger.info("✓ Alternative playback successful")
                            os.unlink(tmp_file.name)
                            metrics['playback'] = time.perf_counter() - playback_start
                            return True, metrics
                        else:
                            logger.error(f"Alternative playback failed: {result.stderr.decode()}")
                    except Exception as alt_e:
                        logger.error(f"Alternative playback error: {alt_e}")
                
                os.unlink(tmp_file.name)
                metrics['playback'] = time.perf_counter() - playback_start
                return False, metrics
                        
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        logger.error(f"TTS config when error occurred - Model: {tts_model}, Voice: {tts_voice}, Base URL: {tts_base_url}")
        logger.debug(f"Full TTS error details:", exc_info=True)
        
        # Check for authentication errors
        error_message = str(e).lower()
        if hasattr(e, 'response'):
            logger.error(f"HTTP status: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}")
            logger.error(f"Response text: {e.response.text if hasattr(e.response, 'text') else 'unknown'}")
            
            # Check for 401 Unauthorized specifically on OpenAI endpoints
            if hasattr(e.response, 'status_code') and e.response.status_code == 401:
                if 'openai.com' in tts_base_url:
                    logger.error("⚠️  Authentication failed with OpenAI. Please set OPENAI_API_KEY environment variable.")
                    logger.error("   Alternatively, you can use local services (Kokoro) without an API key.")
        elif 'api key' in error_message or 'unauthorized' in error_message or 'authentication' in error_message:
            if 'openai.com' in tts_base_url:
                logger.error("⚠️  Authentication issue detected. Please check your OPENAI_API_KEY.")
                logger.error("   For local-only usage, ensure Kokoro is running and configured.")
        
        return False, metrics


def generate_chime(
    frequencies: list, 
    duration: float = 0.1, 
    sample_rate: int = SAMPLE_RATE,
    leading_silence: Optional[float] = None,
    trailing_silence: Optional[float] = None
) -> np.ndarray:
    """Generate a chime sound with given frequencies.
    
    Args:
        frequencies: List of frequencies to play in sequence
        duration: Duration of each tone in seconds
        sample_rate: Sample rate for audio generation
        leading_silence: Optional override for leading silence duration (seconds)
        trailing_silence: Optional override for trailing silence duration (seconds)
        
    Returns:
        Numpy array of audio samples
    """
    samples_per_tone = int(sample_rate * duration)
    fade_samples = int(sample_rate * 0.01)  # 10ms fade
    
    # Determine amplitude based on output device
    amplitude = 0.0375  # Default (very quiet)
    try:
        import sounddevice as sd
        default_output = sd.default.device[1]
        if default_output is not None:
            devices = sd.query_devices()
            device_name = devices[default_output]['name'].lower()
            # Check for Bluetooth devices (AirPods, Bluetooth headphones, etc)
            if 'airpod' in device_name or 'bluetooth' in device_name or 'bt' in device_name:
                amplitude = 0.15  # Higher amplitude for Bluetooth devices
                logger.debug(f"Bluetooth device detected ({devices[default_output]['name']}), using amplitude {amplitude}")
            else:
                amplitude = 0.075  # Moderate amplitude for built-in speakers
                logger.debug(f"Built-in speaker detected ({devices[default_output]['name']}), using amplitude {amplitude}")
    except Exception as e:
        logger.debug(f"Could not detect output device type: {e}, using default amplitude {amplitude}")
    
    all_samples = []
    
    for freq in frequencies:
        # Generate sine wave
        t = np.linspace(0, duration, samples_per_tone, False)
        tone = amplitude * np.sin(2 * np.pi * freq * t)
        
        # Apply fade in/out to prevent clicks
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        
        tone[:fade_samples] *= fade_in
        tone[-fade_samples:] *= fade_out
        
        all_samples.append(tone)
    
    # Concatenate all tones
    chime = np.concatenate(all_samples)
    
    # Import config values if not overridden
    from .config import PIP_LEADING_SILENCE, PIP_TRAILING_SILENCE
    
    # Use parameter overrides or fall back to config
    actual_leading_silence = leading_silence if leading_silence is not None else PIP_LEADING_SILENCE
    actual_trailing_silence = trailing_silence if trailing_silence is not None else PIP_TRAILING_SILENCE
    
    # Add leading silence for Bluetooth wake-up time
    # This prevents the beginning of the chime from being cut off
    silence_samples = int(sample_rate * actual_leading_silence)
    silence = np.zeros(silence_samples)
    
    # Add trailing silence to prevent end cutoff
    trailing_silence_samples = int(sample_rate * actual_trailing_silence)
    trailing_silence = np.zeros(trailing_silence_samples)
    
    # Combine: leading silence + chime + trailing silence
    chime_with_buffer = np.concatenate([silence, chime, trailing_silence])
    
    # Convert to 16-bit integer
    chime_int16 = (chime_with_buffer * 32767).astype(np.int16)
    
    return chime_int16


async def play_chime_start(
    sample_rate: int = SAMPLE_RATE,
    leading_silence: Optional[float] = None,
    trailing_silence: Optional[float] = None
) -> bool:
    """Play the recording start chime (ascending tones).
    
    Args:
        sample_rate: Sample rate for audio
        leading_silence: Optional override for leading silence duration (seconds)
        trailing_silence: Optional override for trailing silence duration (seconds)
    
    Returns:
        True if chime played successfully, False otherwise
    """
    try:
        import sounddevice as sd
        chime = generate_chime(
            [800, 1000], 
            duration=0.1, 
            sample_rate=sample_rate,
            leading_silence=leading_silence,
            trailing_silence=trailing_silence
        )
        sd.play(chime, sample_rate)
        sd.wait()
        return True
    except Exception as e:
        logger.debug(f"Could not play start chime: {e}")
        return False


async def play_chime_end(
    sample_rate: int = SAMPLE_RATE,
    leading_silence: Optional[float] = None,
    trailing_silence: Optional[float] = None
) -> bool:
    """Play the recording end chime (descending tones).
    
    Args:
        sample_rate: Sample rate for audio
        leading_silence: Optional override for leading silence duration (seconds)
        trailing_silence: Optional override for trailing silence duration (seconds)
    
    Returns:
        True if chime played successfully, False otherwise
    """
    try:
        import sounddevice as sd
        chime = generate_chime(
            [1000, 800], 
            duration=0.1, 
            sample_rate=sample_rate,
            leading_silence=leading_silence,
            trailing_silence=trailing_silence
        )
        sd.play(chime, sample_rate)
        sd.wait()
        return True
    except Exception as e:
        logger.debug(f"Could not play end chime: {e}")
        return False


async def cleanup(openai_clients: dict):
    """Cleanup function to close HTTP clients and resources"""
    logger.info("Shutting down Voice Mode Server...")
    
    # Close OpenAI HTTP clients
    try:
        # Close all clients (including provider-specific ones)
        for client_name, client in openai_clients.items():
            if hasattr(client, '_client'):
                await client._client.aclose()
                logger.debug(f"Closed {client_name} HTTP client")
    except Exception as e:
        logger.error(f"Error closing HTTP clients: {e}")
    
    # Final garbage collection
    gc.collect()
    logger.info("Cleanup completed")
