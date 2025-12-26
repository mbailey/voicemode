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

# Optional LiveKit for room-based communication
try:
    from livekit import rtc, api
    LIVEKIT_AVAILABLE = True
except ImportError:
    LIVEKIT_AVAILABLE = False

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
    TTS_SPEED,
    VAD_CHUNK_DURATION_MS,
    INITIAL_SILENCE_GRACE_PERIOD,
    DEFAULT_LISTEN_DURATION,
    TTS_VOICES,
    TTS_MODELS,
    REPEAT_PHRASES,
    WAIT_PHRASES,
    WAIT_DURATION,
    METRICS_LEVEL,
    STT_AUDIO_FORMAT,
    STT_SAVE_FORMAT,
    MP3_BITRATE
)
import voice_mode.config
from voice_mode.provider_discovery import provider_registry
from voice_mode.core import (
    get_openai_clients,
    text_to_speech,
    cleanup as cleanup_clients,
    save_debug_file,
    get_debug_filename,
    get_audio_path,
    play_chime_start,
    play_chime_end,
    play_system_audio
)
from voice_mode.audio_player import NonBlockingAudioPlayer
from voice_mode.statistics_tracking import track_voice_interaction
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

logger = logging.getLogger("voicemode")

# Log silence detection config at module load time
logger.info(f"Module loaded with DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}")


def should_repeat(text: str) -> bool:
    """
    Check if the transcribed text ends with a repeat phrase.

    Args:
        text: The transcribed text to check

    Returns:
        True if text ends with a repeat phrase, False otherwise
    """
    if not text:
        return False

    # Normalize text for comparison (lowercase, strip whitespace and punctuation)
    import string
    normalized_text = text.lower().strip().rstrip(string.punctuation).strip()

    # Check if any repeat phrase appears at the end
    for phrase in REPEAT_PHRASES:
        if normalized_text.endswith(phrase.lower().strip()):
            logger.info(f"Repeat phrase detected: '{phrase}' in '{text}'")
            return True

    return False


def should_wait(text: str) -> bool:
    """
    Check if the transcribed text ends with a wait phrase.

    Args:
        text: The transcribed text to check

    Returns:
        True if text ends with a wait phrase, False otherwise
    """
    if not text:
        return False

    # Normalize text for comparison (lowercase, strip whitespace and punctuation)
    import string
    normalized_text = text.lower().strip().rstrip(string.punctuation).strip()

    # Check if any wait phrase appears at the end
    for phrase in WAIT_PHRASES:
        if normalized_text.endswith(phrase.lower().strip()):
            logger.info(f"Wait phrase detected: '{phrase}' in '{text}'")
            return True

    return False


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
    """Get TTS configuration - simplified to use direct config"""
    from voice_mode.provider_discovery import detect_provider_type

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
    base_url = None
    if provider:
        base_url = provider_urls.get(provider, provider)

    # Use first available endpoint from config
    if not base_url:
        base_url = TTS_BASE_URLS[0] if TTS_BASE_URLS else 'https://api.openai.com/v1'

    provider_type = detect_provider_type(base_url)

    # Return simplified configuration
    return {
        'base_url': base_url,
        'model': model or TTS_MODELS[0] if TTS_MODELS else 'tts-1',
        'voice': voice or TTS_VOICES[0] if TTS_VOICES else 'alloy',
        'instructions': instructions,
        'provider_type': provider_type
    }


async def get_stt_config(provider: Optional[str] = None):
    """Get STT configuration - simplified to use direct config"""
    from voice_mode.provider_discovery import detect_provider_type
    from voice_mode.config import STT_BASE_URLS

    # Map provider names to base URLs
    provider_urls = {
        'whisper-local': 'http://127.0.0.1:2022/v1',
        'openai-whisper': 'https://api.openai.com/v1'
    }

    # Convert provider name to URL if it's a known provider
    base_url = None
    if provider:
        base_url = provider_urls.get(provider, provider)

    # Use first available endpoint from config
    if not base_url:
        base_url = STT_BASE_URLS[0] if STT_BASE_URLS else 'https://api.openai.com/v1'

    provider_type = detect_provider_type(base_url)

    # Return simplified configuration
    return {
        'base_url': base_url,
        'model': 'whisper-1',
        'provider': 'whisper-local' if '127.0.0.1' in base_url or 'localhost' in base_url else 'openai-whisper',
        'provider_type': provider_type
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
    # Apply pronunciation rules if enabled
    if pronounce_enabled():
        pronounce_mgr = get_pronounce_manager()
        message = pronounce_mgr.process_tts(message)

    # Always use simple failover (the only mode now)
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


def prepare_audio_for_stt(audio_data: np.ndarray, output_format: str = "mp3") -> bytes:
    """
    Prepare audio data for STT upload with optional compression.

    Converts raw audio to the specified format, optionally compressing and
    downsampling to 16kHz (Whisper's native rate) for optimal bandwidth.

    Args:
        audio_data: Raw audio data as numpy array (16-bit PCM)
        output_format: Target format ('mp3', 'wav', 'flac', etc.)

    Returns:
        Compressed audio data as bytes
    """
    import io

    # Create AudioSegment from raw data
    # Audio is recorded at SAMPLE_RATE (24kHz), 16-bit mono
    audio = AudioSegment(
        audio_data.tobytes(),
        frame_rate=SAMPLE_RATE,
        sample_width=2,  # 16-bit = 2 bytes
        channels=CHANNELS
    )

    # Calculate original size for logging
    original_size = len(audio_data) * 2  # 16-bit = 2 bytes per sample

    # Downsample to 16kHz (Whisper's native rate) for better compression
    # This also reduces size by ~33% even before compression
    whisper_sample_rate = 16000
    if SAMPLE_RATE != whisper_sample_rate:
        audio = audio.set_frame_rate(whisper_sample_rate)

    # Export to target format
    buffer = io.BytesIO()

    if output_format == "mp3":
        # Use configured bitrate for MP3 (default 32k for speech)
        audio.export(buffer, format="mp3", bitrate=MP3_BITRATE)
    elif output_format == "wav":
        # WAV is uncompressed but we still benefit from downsampling
        audio.export(buffer, format="wav")
    elif output_format == "flac":
        # FLAC is lossless compression
        audio.export(buffer, format="flac")
    else:
        # Default to MP3 for unknown formats
        logger.warning(f"Unknown STT format '{output_format}', falling back to MP3")
        audio.export(buffer, format="mp3", bitrate=MP3_BITRATE)

    compressed_data = buffer.getvalue()
    compressed_size = len(compressed_data)

    # Log compression ratio
    compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
    logger.info(f"STT audio prepared: {original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB "
                f"({output_format}, {compression_ratio:.1f}x compression)")

    return compressed_data


async def speech_to_text(
    audio_data: np.ndarray,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    transport: str = "local"
) -> Optional[Dict]:
    """
    Convert audio to text with automatic failover.

    Handles audio file preparation (saving permanently or using temp file) and
    delegates to simple_stt_failover for the actual transcription attempts.

    For remote endpoints: Audio is compressed (MP3 at 32kbps) and downsampled
    to 16kHz to reduce bandwidth usage when uploading.

    For local endpoints: Audio is sent as WAV to skip compression overhead,
    since network bandwidth isn't a bottleneck for localhost/LAN connections.

    Original full-quality WAV is saved separately when save_audio is enabled.

    Args:
        audio_data: Raw audio data as numpy array
        save_audio: Whether to save the audio file permanently
        audio_dir: Directory to save audio files (if save_audio is True)
        transport: Transport method (for logging context)

    Returns:
        Dict with transcription result or error information:
        - Success: {"text": "...", "provider": "...", "endpoint": "..."}
        - No speech: {"error_type": "no_speech", "provider": "..."}
        - All failed: {"error_type": "connection_failed", "attempted_endpoints": [...]}
    """
    import tempfile
    import io
    from voice_mode.conversation_logger import get_conversation_logger
    from voice_mode.core import save_debug_file, get_debug_filename
    from voice_mode.simple_failover import simple_stt_failover
    from voice_mode.config import STT_BASE_URLS, STT_COMPRESS
    from voice_mode.provider_discovery import is_local_provider

    # Determine compression based on STT_COMPRESS mode
    # Options: auto (default), always, never
    primary_endpoint = STT_BASE_URLS[0] if STT_BASE_URLS else 'https://api.openai.com/v1'
    is_local = is_local_provider(primary_endpoint)

    if STT_COMPRESS == "never":
        # Never compress - always use WAV
        stt_format = "wav"
        logger.info(f"STT: Compression disabled (mode=never), using WAV")
    elif STT_COMPRESS == "always":
        # Always compress regardless of endpoint type
        stt_format = STT_AUDIO_FORMAT if STT_AUDIO_FORMAT != "pcm" else "mp3"
        logger.info(f"STT: Compression forced (mode=always), using {stt_format}")
    else:
        # Auto mode (default): compress for remote, skip for local
        if is_local:
            # Local endpoint: use WAV to skip compression overhead (~200-800ms saved)
            stt_format = "wav"
            logger.info(f"STT: Local endpoint detected ({primary_endpoint}), skipping compression")
        else:
            # Remote endpoint: compress to reduce bandwidth (~90% smaller)
            stt_format = STT_AUDIO_FORMAT if STT_AUDIO_FORMAT != "pcm" else "mp3"
            logger.info(f"STT: Remote endpoint ({primary_endpoint}), using {stt_format} compression")

    # Prepare audio for upload (compressed for remote, WAV for local)
    compressed_audio = prepare_audio_for_stt(audio_data, stt_format)

    # Determine file extension based on format
    file_extension = stt_format if stt_format in ["mp3", "wav", "flac", "m4a", "ogg"] else "mp3"

    # Determine if we should save the file permanently or use a temp file
    if save_audio and audio_dir:
        # Save files for debugging/analysis
        conversation_logger = get_conversation_logger()
        conversation_id = conversation_logger.conversation_id

        # Create year/month directory structure
        now = datetime.now()
        year_dir = audio_dir / str(now.year)
        month_dir = year_dir / f"{now.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)

        # Save recording in configured format (default: wav for full quality)
        save_filename = get_debug_filename("stt", STT_SAVE_FORMAT, conversation_id)
        save_file_path = month_dir / save_filename

        if STT_SAVE_FORMAT == "wav":
            # Save as uncompressed WAV for full quality archival
            write(str(save_file_path), SAMPLE_RATE, audio_data)
        else:
            # Save in configured compressed format
            saved_audio = prepare_audio_for_stt(audio_data, STT_SAVE_FORMAT)
            with open(save_file_path, 'wb') as f:
                f.write(saved_audio)

        logger.info(f"STT audio saved to: {save_file_path} (format: {STT_SAVE_FORMAT})")

        # Use compressed audio for upload (temporary file)
        with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as tmp_file:
            tmp_file.write(compressed_audio)
            tmp_file.flush()

            with open(tmp_file.name, 'rb') as audio_file:
                result = await simple_stt_failover(
                    audio_file=audio_file,
                    model="whisper-1"
                )

            # Clean up temp file (we keep the WAV)
            os.unlink(tmp_file.name)
    else:
        # Use temporary file that will be deleted
        with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as tmp_file:
            tmp_file.write(compressed_audio)
            tmp_file.flush()

            with open(tmp_file.name, 'rb') as audio_file:
                result = await simple_stt_failover(
                    audio_file=audio_file,
                    model="whisper-1"
                )

            # Clean up temp file
            os.unlink(tmp_file.name)

    return result


async def play_audio_feedback(
    text: str,
    openai_clients: dict,
    enabled: Optional[bool] = None,
    style: str = "whisper",
    feedback_type: Optional[str] = None,
    voice: str = "nova",
    model: str = "gpt-4o-mini-tts",
    chime_leading_silence: Optional[float] = None,
    chime_trailing_silence: Optional[float] = None
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
        chime_leading_silence: Optional override for pre-chime silence duration
        chime_trailing_silence: Optional override for post-chime silence duration
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
                leading_silence=chime_leading_silence,
                trailing_silence=chime_trailing_silence
            )
        elif text == "finished":
            await play_chime_end(
                leading_silence=chime_leading_silence,
                trailing_silence=chime_trailing_silence
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
    # First check if LiveKit is installed
    if not LIVEKIT_AVAILABLE:
        logger.debug("LiveKit not available (not installed)")
        return False

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
    if not LIVEKIT_AVAILABLE:
        return "Error: LiveKit not installed. Install with: uv tool install voice-mode[livekit]"

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
    listen_duration_max: float = DEFAULT_LISTEN_DURATION,
    listen_duration_min: float = 2.0,
    transport: Literal["auto", "local", "livekit"] = "auto",
    room_name: str = "",
    timeout: float = 60.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None,
    tts_model: Optional[str] = None,
    tts_instructions: Optional[str] = None,
    chime_enabled: Optional[Union[bool, str]] = None,
    audio_format: Optional[str] = None,
    disable_silence_detection: Union[bool, str] = False,
    speed: Optional[float] = None,
    vad_aggressiveness: Optional[Union[int, str]] = None,
    skip_tts: Optional[Union[bool, str]] = None,
    chime_leading_silence: Optional[float] = None,
    chime_trailing_silence: Optional[float] = None,
    metrics_level: Optional[Literal["minimal", "summary", "verbose"]] = None
) -> str:
    """Have an ongoing voice conversation - speak a message and optionally listen for response.

<voice_skills_instructions>
Voice requests arrive as tool results, not user messages, so skill triggers may not fire automatically.

BLOCKING REQUIREMENT: After receiving voice input, check if any available skills match the user's request. When a skill is relevant:
- Invoke the Skill tool IMMEDIATELY as your first action
- Do NOT take action on the request before checking for relevant skills
- Skills provide specialized capabilities that improve task completion

Example: If user says "search for tasks created yesterday", check for and invoke the taskmaster skill before using bash or other tools.
</voice_skills_instructions>


🔌 ENDPOINT: STT/TTS services must expose OpenAI-compatible endpoints:
   /v1/audio/transcriptions and /v1/audio/speech

📚 DOCUMENTATION: See MCP resources for detailed information:
   - voicemode://docs/quickstart - Basic usage and common examples
   - voicemode://docs/parameters - Complete parameter reference
   - voicemode://docs/languages - Non-English language support guide
   - voicemode://docs/patterns - Best practices and conversation patterns
   - voicemode://docs/troubleshooting - Audio, VAD, and connectivity issues

KEY PARAMETERS:
• message (required): The message to speak
• wait_for_response (bool, default: true): Listen for response after speaking
• listen_duration_max (number, default: 120): Max listen time in seconds
• listen_duration_min (number, default: 2.0): Min recording time before silence detection
• voice (string): TTS voice name (auto-selected unless specified)
• tts_provider ("openai"|"kokoro"): Provider selection (auto-selected unless specified)
• disable_silence_detection (bool, default: false): Disable auto-stop on silence
• vad_aggressiveness (0-3, default: 2): Voice detection strictness (0=permissive, 3=strict)
• speed (0.25-4.0): Speech rate (1.0=normal, 2.0=double speed)
• chime_enabled (bool): Enable/disable audio feedback chimes
• chime_leading_silence (float): Silence before chime in seconds
• chime_trailing_silence (float): Silence after chime in seconds
• metrics_level ("minimal"|"summary"|"verbose"): Output detail level
  - minimal: Just response text (saves tokens)
  - summary: Response + compact timing (default)
  - verbose: Response + detailed metrics breakdown

PRIVACY: Microphone access required when wait_for_response=true.
         Audio processed via STT service, not stored.

For complete parameter list, advanced options, and detailed examples,
consult the MCP resources listed above.
    """
    # Convert string booleans to actual booleans
    if isinstance(wait_for_response, str):
        wait_for_response = wait_for_response.lower() in ('true', '1', 'yes', 'on')
    if isinstance(disable_silence_detection, str):
        disable_silence_detection = disable_silence_detection.lower() in ('true', '1', 'yes', 'on')
    if isinstance(chime_enabled, str):
        chime_enabled = chime_enabled.lower() in ('true', '1', 'yes', 'on')
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

    # Apply default speed from config if not provided
    speed_from_config = False
    if speed is None:
        speed = TTS_SPEED
        speed_from_config = True

    # Validate speed parameter range
    if speed is not None:
        if not (0.25 <= speed <= 4.0):
            source = " from VOICEMODE_TTS_SPEED environment variable" if speed_from_config else ""
            return f"❌ Error: speed must be between 0.25 and 4.0 (got {speed}{source})"

    # Determine effective metrics level (parameter overrides config)
    effective_metrics_level = metrics_level if metrics_level else METRICS_LEVEL

    logger.info(f"Converse: '{message[:50]}{'...' if len(message) > 50 else ''}' (wait_for_response: {wait_for_response})")
    
    # Validate vad_aggressiveness parameter
    if vad_aggressiveness is not None:
        if not isinstance(vad_aggressiveness, int) or vad_aggressiveness < 0 or vad_aggressiveness > 3:
            return f"Error: vad_aggressiveness must be an integer between 0 and 3 (got {vad_aggressiveness})"
    
    # Validate duration parameters
    if wait_for_response:
        if listen_duration_min < 0:
            return "❌ Error: listen_duration_min cannot be negative"
        if listen_duration_max <= 0:
            return "❌ Error: listen_duration_max must be positive"
        if listen_duration_min > listen_duration_max:
            logger.warning(f"listen_duration_min ({listen_duration_min}s) is greater than listen_duration_max ({listen_duration_max}s), using listen_duration_max as minimum")
            listen_duration_min = listen_duration_max
    
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
            "listen_duration_max": listen_duration_max if wait_for_response else None
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
        # Determine transport method (only needed when waiting for response)
        if wait_for_response:
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
                # Use listen_duration_max instead of timeout for consistent behavior
                livekit_result = await livekit_converse(message, room_name, listen_duration_max)

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

        # For both speak-only and local conversation modes
        if not wait_for_response or transport == "local":
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
                                is_fallback=tts_config.get('is_fallback', False) if tts_config else False,
                                fallback_reason=tts_config.get('fallback_reason') if tts_config else None,
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
                        # Check if we have detailed error information
                        if tts_config and tts_config.get('error_type') == 'all_providers_failed':
                            error_lines = ["Error: Could not speak message. TTS service connection failed:"]
                            openai_error_shown = False

                            for attempt in tts_config.get('attempted_endpoints', []):
                                # Check if we have parsed OpenAI error details
                                if attempt.get('error_details') and not openai_error_shown and attempt.get('provider') == 'openai':
                                    error_details = attempt['error_details']
                                    error_lines.append("")
                                    error_lines.append(error_details.get('title', 'OpenAI Error'))
                                    error_lines.append(error_details.get('message', ''))
                                    if error_details.get('suggestion'):
                                        error_lines.append(f"💡 {error_details['suggestion']}")
                                    if error_details.get('fallback'):
                                        error_lines.append(f"ℹ️ {error_details['fallback']}")
                                    openai_error_shown = True
                                else:
                                    # Show raw error for non-OpenAI or if we already showed OpenAI error
                                    endpoint_or_provider = attempt.get('endpoint', attempt.get('provider', 'unknown'))
                                    error_lines.append(f"  - {endpoint_or_provider}: {attempt['error']}")

                            result = "\n".join(error_lines)
                        # Check if we have config info that might indicate why it failed
                        elif tts_config and 'openai.com' in tts_config.get('base_url', ''):
                            # Check if API key is missing for OpenAI
                            from voice_mode.config import OPENAI_API_KEY
                            if not OPENAI_API_KEY:
                                result = "Error: Could not speak message. OpenAI API key is not set. Please set OPENAI_API_KEY environment variable or use local services (Kokoro TTS)."
                            else:
                                result = "Error: Could not speak message. TTS request to OpenAI failed. Please check your API key and network connection."
                        else:
                            result = "Error: Could not speak message. All TTS providers failed. Check that local services are running or set OPENAI_API_KEY for cloud fallback."
                        return result

                    # If speak-only mode, return success after TTS
                    if not wait_for_response:
                        # Format timing info for speak-only mode
                        timing_info = ""
                        if tts_success and tts_metrics:
                            timing_info = f" (gen: {tts_metrics.get('generation', 0):.1f}s, play: {tts_metrics.get('playback', 0):.1f}s)"

                        # Create timing string for statistics
                        timing_str = ""
                        if tts_success and timings:
                            timing_parts = []
                            if 'ttfa' in timings:
                                timing_parts.append(f"ttfa {timings['ttfa']:.1f}s")
                            if 'tts_gen' in timings:
                                timing_parts.append(f"tts_gen {timings['tts_gen']:.1f}s")
                            if 'tts_play' in timings:
                                timing_parts.append(f"tts_play {timings['tts_play']:.1f}s")
                            timing_str = ", ".join(timing_parts)

                        # Track statistics for speak-only interaction
                        track_voice_interaction(
                            message=message,
                            response="[speak-only]",
                            timing_str=timing_str,
                            transport="speak-only",
                            voice_provider=tts_provider,
                            voice_name=voice,
                            model=tts_model,
                            success=tts_success,
                            error_message=None if tts_success else "TTS failed"
                        )

                        # Format result based on metrics level
                        if effective_metrics_level == "minimal":
                            result = "✓ Message spoken successfully"
                        else:
                            result = f"✓ Message spoken successfully{timing_info}"
                        logger.info(f"Speak-only result: {result}")
                        return result

                    # Brief pause before listening
                    await asyncio.sleep(0.5)
                    
                    # Play "listening" feedback sound
                    await play_audio_feedback(
                        "listening",
                        openai_clients,
                        chime_enabled,
                        "whisper",
                        chime_leading_silence=chime_leading_silence,
                        chime_trailing_silence=chime_trailing_silence
                    )
                    
                    # Record response
                    logger.info(f"🎤 Listening for {listen_duration_max} seconds...")

                    # Log recording start
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_START)

                    record_start = time.perf_counter()
                    logger.debug(f"About to call record_audio_with_silence_detection with duration={listen_duration_max}, disable_silence_detection={disable_silence_detection}, min_duration={listen_duration_min}, vad_aggressiveness={vad_aggressiveness}")
                    audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio_with_silence_detection, listen_duration_max, disable_silence_detection, listen_duration_min, vad_aggressiveness
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
                        chime_enabled,
                        "whisper",
                        chime_leading_silence=chime_leading_silence,
                        chime_trailing_silence=chime_trailing_silence
                    )
                    
                    # Mark the end of recording - this is when user expects response to start
                    user_done_time = time.perf_counter()
                    logger.info(f"Recording finished at {user_done_time - tts_start:.1f}s from start")
                    
                    if len(audio_data) == 0:
                        result = "Error: Could not record audio"
                        return result
                    
                    # Track STT-specific metrics (defined here to be in scope for event logging later)
                    stt_metrics = None

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
                        stt_result = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport)
                        timings['stt'] = time.perf_counter() - stt_start

                        # Handle structured STT result
                        if isinstance(stt_result, dict):
                            # Extract metrics if present
                            stt_metrics = stt_result.get("metrics")
                            if stt_metrics:
                                # Store in timings for later use
                                timings['stt_request_ms'] = stt_metrics.get('request_time_ms', 0)
                                timings['stt_file_size_bytes'] = stt_metrics.get('file_size_bytes', 0)
                                timings['stt_is_local'] = stt_metrics.get('is_local', False)
                                logger.debug(f"STT metrics: request={stt_metrics.get('request_time_ms')}ms, "
                                           f"file_size={stt_metrics.get('file_size_bytes')/1024:.1f}KB, "
                                           f"is_local={stt_metrics.get('is_local')}")

                            if "error_type" in stt_result:
                                # Handle connection failures vs no speech
                                if stt_result["error_type"] == "connection_failed":
                                    # Build helpful error message
                                    error_lines = ["STT service connection failed:"]
                                    openai_error_shown = False

                                    for attempt in stt_result.get("attempted_endpoints", []):
                                        # Check if we have parsed OpenAI error details
                                        if attempt.get('error_details') and not openai_error_shown and attempt.get('provider') == 'openai':
                                            error_details = attempt['error_details']
                                            error_lines.append("")
                                            error_lines.append(error_details.get('title', 'OpenAI Error'))
                                            error_lines.append(error_details.get('message', ''))
                                            if error_details.get('suggestion'):
                                                error_lines.append(f"💡 {error_details['suggestion']}")
                                            if error_details.get('fallback'):
                                                error_lines.append(f"ℹ️ {error_details['fallback']}")
                                            openai_error_shown = True
                                        else:
                                            # Show raw error for non-OpenAI or if we already showed OpenAI error
                                            error_lines.append(f"  - {attempt['endpoint']}: {attempt['error']}")

                                    error_msg = "\n".join(error_lines)
                                    logger.error(error_msg)

                                    # Return error immediately
                                    return error_msg

                                elif stt_result["error_type"] == "no_speech":
                                    # Genuine no speech detected
                                    response_text = None
                                    stt_provider = stt_result.get("provider", "unknown")
                            else:
                                # Successful transcription
                                response_text = stt_result.get("text")
                                stt_provider = stt_result.get("provider", "unknown")
                                if stt_provider != "unknown":
                                    logger.info(f"📡 STT Provider: {stt_provider}")
                        else:
                            # Should not happen with new code, but handle gracefully
                            response_text = None
                            stt_provider = "unknown"

                    # Check for repeat phrase - if detected, replay the audio and listen again
                    if response_text and should_repeat(response_text):
                        logger.info(f"🔁 Repeat requested: '{response_text}'")

                        # Play system message for repeat
                        await play_system_audio("repeating", fallback_text="Repeating")

                        # Replay the same audio
                        if transport == "local":
                            logger.info("Replaying audio...")

                            # Play the cached audio if available from tts_metrics
                            audio_path = tts_metrics.get('audio_path') if 'tts_metrics' in locals() and tts_metrics else None
                            if audio_path and os.path.exists(audio_path):
                                try:
                                    import soundfile as sf

                                    # Read and play the audio file using non-blocking player
                                    data, samplerate = sf.read(audio_path)
                                    player = NonBlockingAudioPlayer()
                                    player.play(data, samplerate, blocking=True)
                                    logger.info("Audio replay completed")
                                except Exception as e:
                                    logger.warning(f"Failed to replay cached audio: {e}. Regenerating...")
                                    # Fall back to regenerating TTS
                                    tts_success, new_tts_metrics, _ = await text_to_speech_with_failover(
                                        message=message,
                                        voice=voice,
                                        model=tts_model,
                                        instructions=tts_instructions,
                                        audio_format=audio_format,
                                        initial_provider=tts_provider,
                                        speed=speed
                                    )
                                    if not tts_success:
                                        logger.error("Failed to replay audio via TTS regeneration")
                            else:
                                # No cached audio, regenerate TTS
                                logger.info("No cached audio available, regenerating...")
                                tts_success, new_tts_metrics, _ = await text_to_speech_with_failover(
                                    message=message,
                                    voice=voice,
                                    model=tts_model,
                                    instructions=tts_instructions,
                                    audio_format=audio_format,
                                    initial_provider=tts_provider,
                                    speed=speed
                                )
                                if not tts_success:
                                    logger.error("Failed to replay audio via TTS regeneration")

                            # Listen again for response - reuse the recording logic
                            logger.info("Listening for response after repeat...")

                            # Play "listening" feedback sound
                            await play_audio_feedback(
                                "listening",
                                openai_clients,
                                chime_enabled,
                                "whisper",
                                chime_leading_silence=chime_leading_silence,
                                chime_trailing_silence=chime_trailing_silence
                            )

                            # Record audio
                            record_start = time.perf_counter()
                            audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
                                None, record_audio_with_silence_detection, listen_duration_max, disable_silence_detection, listen_duration_min, vad_aggressiveness
                            )
                            record_time = time.perf_counter() - record_start
                            timings['record'] = timings.get('record', 0) + record_time  # Accumulate timing

                            # Play "finished" feedback sound
                            await play_audio_feedback(
                                "finished",
                                openai_clients,
                                chime_enabled,
                                "whisper",
                                chime_leading_silence=chime_leading_silence,
                                chime_trailing_silence=chime_trailing_silence
                            )

                            if len(audio_data) > 0 and speech_detected:
                                # Transcribe the audio
                                stt_start = time.perf_counter()
                                stt_result = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport)
                                stt_time = time.perf_counter() - stt_start
                                timings['stt'] = timings.get('stt', 0) + stt_time  # Accumulate timing

                                # Process result
                                if isinstance(stt_result, dict) and not stt_result.get("error"):
                                    response_text = stt_result.get("text")
                                    stt_provider = stt_result.get("provider", "unknown")
                                    logger.info(f"New response after repeat: {response_text}")

                    # Check for wait phrase - if detected, pause for configured duration
                    if response_text and should_wait(response_text):
                        logger.info(f"⏸️ Wait requested: '{response_text}'. Pausing for {WAIT_DURATION} seconds...")

                        # Play system message for wait
                        await play_system_audio("waiting-1-minute", fallback_text="Waiting one minute")

                        await asyncio.sleep(WAIT_DURATION)

                        # Play system message when ready to listen again
                        await play_system_audio("ready-to-listen", fallback_text="Ready to listen")

                        # After waiting, listen again
                        logger.info("Wait period ended. Listening for response...")
                        if transport == "local":
                            # Play "listening" feedback sound
                            await play_audio_feedback(
                                "listening",
                                openai_clients,
                                chime_enabled,
                                "whisper",
                                chime_leading_silence=chime_leading_silence,
                                chime_trailing_silence=chime_trailing_silence
                            )

                            # Record audio
                            record_start = time.perf_counter()
                            audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
                                None, record_audio_with_silence_detection, listen_duration_max, disable_silence_detection, listen_duration_min, vad_aggressiveness
                            )
                            record_time = time.perf_counter() - record_start
                            timings['record'] = timings.get('record', 0) + record_time  # Accumulate timing

                            # Play "finished" feedback sound
                            await play_audio_feedback(
                                "finished",
                                openai_clients,
                                chime_enabled,
                                "whisper",
                                chime_leading_silence=chime_leading_silence,
                                chime_trailing_silence=chime_trailing_silence
                            )

                            if len(audio_data) > 0 and speech_detected:
                                # Transcribe the audio
                                stt_start = time.perf_counter()
                                stt_result = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport)
                                stt_time = time.perf_counter() - stt_start
                                timings['stt'] = timings.get('stt', 0) + stt_time  # Accumulate timing

                                # Process result
                                if isinstance(stt_result, dict) and not stt_result.get("error"):
                                    response_text = stt_result.get("text")
                                    stt_provider = stt_result.get("provider", "unknown")
                                    logger.info(f"New response after wait: {response_text}")

                    # Log STT complete with metrics
                    if event_logger:
                        stt_event_data = {}
                        if response_text:
                            stt_event_data["text"] = response_text
                        # Include metrics in event log (debug level data)
                        if stt_metrics:
                            stt_event_data["metrics"] = {
                                "file_size_bytes": stt_metrics.get('file_size_bytes', 0),
                                "request_time_ms": stt_metrics.get('request_time_ms', 0),
                                "is_local": stt_metrics.get('is_local', False),
                                "format": "wav",
                                "sample_rate_hz": SAMPLE_RATE,
                                "bitrate_kbps": (SAMPLE_RATE * 16 * CHANNELS) // 1000
                            }
                        if response_text:
                            event_logger.log_event(event_logger.STT_COMPLETE, stt_event_data)
                        else:
                            event_logger.log_event(event_logger.STT_NO_SPEECH, stt_event_data)
                    
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
                # Add detailed STT metrics if available
                if 'stt_file_size_bytes' in timings and timings['stt_file_size_bytes'] > 0:
                    stt_timing_parts.append(f"audio {timings['stt_file_size_bytes']/1024:.0f}KB")
                
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

                    # Format result based on metrics level
                    stt_info = f" (STT: {stt_provider})" if 'stt_provider' in locals() and stt_provider != "unknown" else ""
                    if effective_metrics_level == "minimal":
                        result = f"Voice response: {response_text}"
                    elif effective_metrics_level == "verbose":
                        # Build verbose metrics block
                        verbose_parts = [f"Voice response: {response_text}{stt_info}"]
                        verbose_parts.append(f"Timing: {timing_str}")
                        if 'stt_request_ms' in timings:
                            verbose_parts.append(f"STT request: {timings['stt_request_ms']:.0f}ms")
                        if 'stt_file_size_bytes' in timings:
                            verbose_parts.append(f"STT file: {timings['stt_file_size_bytes']/1024:.0f}KB")
                        if 'stt_is_local' in timings:
                            verbose_parts.append(f"STT local: {timings['stt_is_local']}")
                        result = " | ".join(verbose_parts)
                    else:  # summary (default)
                        result = f"Voice response: {response_text}{stt_info} | Timing: {timing_str}"
                    success = True
                else:
                    if effective_metrics_level == "minimal":
                        result = "No speech detected"
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




