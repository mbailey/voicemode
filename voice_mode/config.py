"""
Configuration and shared utilities for Voicemode Server.

This module contains all configuration constants, global state, initialization functions,
and shared utilities used across the voicemode server.
"""

import os
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# ==================== ENVIRONMENT CONFIGURATION ====================

# Helper function to parse boolean environment variables
def env_bool(env_var: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    value = os.getenv(env_var, "").lower()
    return value in ("true", "1", "yes", "on") if value else default

# Base directory for all voicemode data
BASE_DIR = Path(os.getenv("VOICEMODE_BASE_DIR", str(Path.home() / ".voicemode")))

# Unified directory structure
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTIONS_DIR = BASE_DIR / "transcriptions"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

# Debug configuration
DEBUG = os.getenv("VOICEMODE_DEBUG", "").lower() in ("true", "1", "yes", "on")
TRACE_DEBUG = os.getenv("VOICEMODE_DEBUG", "").lower() == "trace"
DEBUG_DIR = LOGS_DIR / "debug"  # Debug files now go under logs

# Master save-all configuration
SAVE_ALL = os.getenv("VOICEMODE_SAVE_ALL", "").lower() in ("true", "1", "yes", "on")

# Audio saving configuration
# Enable if SAVE_ALL is true, DEBUG is true, or individually enabled
SAVE_AUDIO = SAVE_ALL or DEBUG or os.getenv("VOICEMODE_SAVE_AUDIO", "").lower() in ("true", "1", "yes", "on")
SAVE_TRANSCRIPTIONS = SAVE_ALL or DEBUG or os.getenv("VOICEMODE_SAVE_TRANSCRIPTIONS", "").lower() in ("true", "1", "yes", "on")

# Audio feedback configuration
AUDIO_FEEDBACK_ENABLED = os.getenv("VOICEMODE_AUDIO_FEEDBACK", "true").lower() in ("true", "1", "yes", "on")

# Local provider preference configuration
PREFER_LOCAL = os.getenv("VOICEMODE_PREFER_LOCAL", "true").lower() in ("true", "1", "yes", "on")

# Always try local providers (don't mark them as permanently unavailable)
ALWAYS_TRY_LOCAL = os.getenv("VOICEMODE_ALWAYS_TRY_LOCAL", "true").lower() in ("true", "1", "yes", "on")

# Auto-start configuration
AUTO_START_KOKORO = os.getenv("VOICEMODE_AUTO_START_KOKORO", "").lower() in ("true", "1", "yes", "on")

# ==================== SERVICE CONFIGURATION ====================

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Helper function to parse comma-separated lists
def parse_comma_list(env_var: str, fallback: str) -> list:
    """Parse comma-separated list from environment variable."""
    value = os.getenv(env_var, fallback)
    return [item.strip() for item in value.split(",") if item.strip()]

# New provider endpoint lists configuration
TTS_BASE_URLS = parse_comma_list("VOICEMODE_TTS_BASE_URLS", "http://127.0.0.1:8880/v1,https://api.openai.com/v1")
STT_BASE_URLS = parse_comma_list("VOICEMODE_STT_BASE_URLS", "http://127.0.0.1:2022/v1,https://api.openai.com/v1")
TTS_VOICES = parse_comma_list("VOICEMODE_TTS_VOICES", "af_sky,alloy")
TTS_MODELS = parse_comma_list("VOICEMODE_TTS_MODELS", "tts-1,tts-1-hd,gpt-4o-mini-tts")

# Legacy variables have been removed - use the new list-based configuration:
# - VOICEMODE_TTS_BASE_URLS (comma-separated list)
# - VOICEMODE_STT_BASE_URLS (comma-separated list)
# - VOICEMODE_TTS_VOICES (comma-separated list)
# - VOICEMODE_TTS_MODELS (comma-separated list)

# LiveKit configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

# ==================== WHISPER CONFIGURATION ====================

# Whisper-specific configuration
WHISPER_MODEL = os.getenv("VOICEMODE_WHISPER_MODEL", "large-v2")
WHISPER_PORT = int(os.getenv("VOICEMODE_WHISPER_PORT", "2022"))
WHISPER_LANGUAGE = os.getenv("VOICEMODE_WHISPER_LANGUAGE", "auto")
WHISPER_MODEL_PATH = os.getenv("VOICEMODE_WHISPER_MODEL_PATH", str(BASE_DIR / "models" / "whisper"))

# ==================== KOKORO CONFIGURATION ====================

# Kokoro-specific configuration
KOKORO_PORT = int(os.getenv("VOICEMODE_KOKORO_PORT", "8880"))
KOKORO_MODELS_DIR = os.getenv("VOICEMODE_KOKORO_MODELS_DIR", str(BASE_DIR / "models" / "kokoro"))
KOKORO_CACHE_DIR = os.getenv("VOICEMODE_KOKORO_CACHE_DIR", str(BASE_DIR / "cache" / "kokoro"))
KOKORO_DEFAULT_VOICE = os.getenv("VOICEMODE_KOKORO_DEFAULT_VOICE", "af_sky")

# ==================== SERVICE MANAGEMENT CONFIGURATION ====================

# Auto-enable services after installation
SERVICE_AUTO_ENABLE = env_bool("VOICEMODE_SERVICE_AUTO_ENABLE", False)

# ==================== AUDIO CONFIGURATION ====================

# Audio parameters
SAMPLE_RATE = 24000  # Standard TTS sample rate for both OpenAI and Kokoro
CHANNELS = 1

# ==================== SILENCE DETECTION CONFIGURATION ====================

# Disable silence detection (useful for noisy environments)
# Silence detection is enabled by default
DISABLE_SILENCE_DETECTION = os.getenv("VOICEMODE_DISABLE_SILENCE_DETECTION", "false").lower() in ("true", "1", "yes", "on")

# VAD (Voice Activity Detection) configuration
VAD_AGGRESSIVENESS = int(os.getenv("VOICEMODE_VAD_AGGRESSIVENESS", "2"))  # 0-3, higher = more aggressive
SILENCE_THRESHOLD_MS = int(os.getenv("VOICEMODE_SILENCE_THRESHOLD_MS", "1000"))  # Stop after 1000ms (1 second) of silence
MIN_RECORDING_DURATION = float(os.getenv("VOICEMODE_MIN_RECORDING_DURATION", "0.5"))  # Minimum 0.5s recording
VAD_CHUNK_DURATION_MS = 30  # VAD frame size (must be 10, 20, or 30ms)
INITIAL_SILENCE_GRACE_PERIOD = float(os.getenv("VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD", "4.0"))  # Give users 4s to start speaking

# Default listen duration for converse tool
DEFAULT_LISTEN_DURATION = float(os.getenv("VOICEMODE_DEFAULT_LISTEN_DURATION", "120.0"))  # Default 120s listening time

# Audio format configuration
AUDIO_FORMAT = os.getenv("VOICEMODE_AUDIO_FORMAT", "pcm").lower()
TTS_AUDIO_FORMAT = os.getenv("VOICEMODE_TTS_AUDIO_FORMAT", "pcm").lower()  # Default to PCM for optimal streaming
# STT requires a format supported by the STT provider - PCM is not supported by OpenAI Whisper
STT_AUDIO_FORMAT = os.getenv("VOICEMODE_STT_AUDIO_FORMAT", "mp3" if AUDIO_FORMAT == "pcm" else AUDIO_FORMAT).lower()

# Supported audio formats
SUPPORTED_AUDIO_FORMATS = ["pcm", "opus", "mp3", "wav", "flac", "aac"]

# Validate formats (validation messages will be logged after logger is initialized)
if AUDIO_FORMAT not in SUPPORTED_AUDIO_FORMATS:
    _invalid_audio_format = AUDIO_FORMAT
    AUDIO_FORMAT = "pcm"

if TTS_AUDIO_FORMAT not in SUPPORTED_AUDIO_FORMATS:
    _invalid_tts_format = TTS_AUDIO_FORMAT
    TTS_AUDIO_FORMAT = AUDIO_FORMAT

if STT_AUDIO_FORMAT not in SUPPORTED_AUDIO_FORMATS:
    _invalid_stt_format = STT_AUDIO_FORMAT
    STT_AUDIO_FORMAT = AUDIO_FORMAT

# Format-specific quality settings
OPUS_BITRATE = int(os.getenv("VOICEMODE_OPUS_BITRATE", "32000"))  # Default 32kbps for voice
MP3_BITRATE = os.getenv("VOICEMODE_MP3_BITRATE", "64k")  # Default 64kbps
AAC_BITRATE = os.getenv("VOICEMODE_AAC_BITRATE", "64k")  # Default 64kbps

# ==================== STREAMING CONFIGURATION ====================

# Streaming playback configuration
STREAMING_ENABLED = os.getenv("VOICEMODE_STREAMING_ENABLED", "true").lower() in ("true", "1", "yes", "on")
STREAM_CHUNK_SIZE = int(os.getenv("VOICEMODE_STREAM_CHUNK_SIZE", "4096"))  # Download chunk size
STREAM_BUFFER_MS = int(os.getenv("VOICEMODE_STREAM_BUFFER_MS", "150"))  # Initial buffer before playback
STREAM_MAX_BUFFER = float(os.getenv("VOICEMODE_STREAM_MAX_BUFFER", "2.0"))  # Max buffer in seconds

# ==================== EVENT LOGGING CONFIGURATION ====================

# Event logging configuration
# Event logs are enabled by default, or if SAVE_ALL is true
EVENT_LOG_ENABLED = SAVE_ALL or os.getenv("VOICEMODE_EVENT_LOG_ENABLED", "true").lower() in ("true", "1", "yes", "on")
EVENT_LOG_DIR = os.getenv("VOICEMODE_EVENT_LOG_DIR", str(LOGS_DIR / "events"))
EVENT_LOG_ROTATION = os.getenv("VOICEMODE_EVENT_LOG_ROTATION", "daily")  # Currently only daily is supported

# ==================== GLOBAL STATE ====================

# Service management
service_processes: Dict[str, subprocess.Popen] = {}

# Concurrency control for audio operations
# This prevents multiple audio operations from interfering with stdio
audio_operation_lock = asyncio.Lock()

# Flag to track if startup initialization has run
_startup_initialized = False

# ==================== LOGGING CONFIGURATION ====================

def setup_logging() -> logging.Logger:
    """Configure logging for the voice-mode server.
    
    Returns:
        Logger instance configured for voice-mode
    """
    log_level = logging.DEBUG if DEBUG else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("voicemode")
    
    # Trace logging setup
    if TRACE_DEBUG:
        import sys
        from datetime import datetime
        
        # Create debug log directory
        debug_log_dir = Path.home() / ".voicemode" / "logs" / "debug"
        debug_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create dated debug log file
        debug_log_file = debug_log_dir / f"voicemode_debug_{datetime.now().strftime('%Y-%m-%d')}.log"
        
        # Set up file handler for debug logs
        debug_handler = logging.FileHandler(debug_log_file, mode='a')
        debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        # Enable debug logging for httpx and openai
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.setLevel(logging.DEBUG)
        httpx_logger.addHandler(debug_handler)
        
        openai_logger = logging.getLogger("openai")
        openai_logger.setLevel(logging.DEBUG)
        openai_logger.addHandler(debug_handler)
        
        # Also add to main logger
        logger.addHandler(debug_handler)
        logger.info(f"Trace debug logging enabled, writing to {debug_log_file}")
        
        # Legacy trace file support
        trace_file = Path.home() / "voicemode_trace.log"
        trace_logger = logging.getLogger("voicemode-trace")
        trace_handler = logging.FileHandler(trace_file, mode='a')
        trace_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        trace_logger.addHandler(trace_handler)
        trace_logger.setLevel(logging.DEBUG)
        
        def trace_calls(frame, event, arg):
            if event == 'call':
                code = frame.f_code
                if 'voicemode' in code.co_filename or 'voice_mode' in code.co_filename:
                    trace_logger.debug(f"Called {code.co_filename}:{frame.f_lineno} {code.co_name}")
            elif event == 'exception':
                trace_logger.debug(f"Exception: {arg}")
            return trace_calls
        
        sys.settrace(trace_calls)
        logger.info(f"Trace debugging enabled, writing to: {trace_file}")
    
    # Also log to file in debug mode
    if DEBUG:
        debug_log_file = Path.home() / "voicemode_debug.log"
        file_handler = logging.FileHandler(debug_log_file, mode='a')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        logger.info(f"Debug logging to file: {debug_log_file}")
    
    # Suppress verbose binary data in HTTP logs
    if DEBUG:
        # Keep our debug logs but reduce HTTP client verbosity
        logging.getLogger("openai._base_client").setLevel(logging.INFO)
        logging.getLogger("httpcore").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.INFO)
    
    return logger

# ==================== DIRECTORY INITIALIZATION ====================

def initialize_directories():
    """Create necessary directories for voicemode data storage."""
    # Create base directory
    BASE_DIR.mkdir(exist_ok=True)
    
    # Create all subdirectories
    AUDIO_DIR.mkdir(exist_ok=True)
    TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)
    
    # Create subdirectories for logs
    if DEBUG:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create events log directory
    if EVENT_LOG_ENABLED:
        Path(EVENT_LOG_DIR).mkdir(parents=True, exist_ok=True)

# ==================== UTILITY FUNCTIONS ====================

def get_debug_filename(prefix: str, extension: str) -> str:
    """Generate a timestamped filename for debug files.
    
    Args:
        prefix: Prefix for the filename (e.g., 'stt-input', 'tts-output')
        extension: File extension (e.g., 'wav', 'mp3')
    
    Returns:
        Timestamped filename string
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"{prefix}_{timestamp}.{extension}"


def get_project_path() -> str:
    """Get the current project path (git root or current working directory)."""
    try:
        # Try to get git root
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    # Fall back to current working directory
    return os.getcwd()


def save_transcription(text: str, prefix: str = "transcript", metadata: Optional[Dict] = None) -> Optional[Path]:
    """Save a transcription to the transcriptions directory.
    
    Args:
        text: The transcription text to save
        prefix: Prefix for the filename (e.g., 'stt', 'conversation')
        metadata: Optional metadata to include at the top of the file
    
    Returns:
        Path to the saved file or None if saving is disabled
    """
    if not SAVE_TRANSCRIPTIONS:
        return None
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{prefix}_{timestamp}.txt"
        filepath = TRANSCRIPTIONS_DIR / filename
        
        content = []
        
        # Create metadata with project path
        if metadata is None:
            metadata = {}
        metadata["project_path"] = get_project_path()
        
        # Add metadata header
        content.append("--- METADATA ---")
        for key, value in metadata.items():
            content.append(f"{key}: {value}")
        content.append("--- TRANSCRIPT ---")
        content.append("")
        
        content.append(text)
        
        filepath.write_text("\n".join(content), encoding="utf-8")
        logger.debug(f"Transcription saved to: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save transcription: {e}")
        return None

# ==================== SOUNDDEVICE WORKAROUND ====================

def disable_sounddevice_stderr_redirect():
    """Comprehensively disable sounddevice's stderr redirection.
    
    This prevents sounddevice from redirecting stderr to /dev/null
    which can interfere with audio playback in MCP server context.
    """
    try:
        import sounddevice as sd
        import sys
        import atexit
        
        # Method 1: Override _ignore_stderr in various locations
        if hasattr(sd, '_sounddevice'):
            if hasattr(sd._sounddevice, '_ignore_stderr'):
                sd._sounddevice._ignore_stderr = lambda: None
        if hasattr(sd, '_ignore_stderr'):
            sd._ignore_stderr = lambda: None
        
        # Method 2: Override _check_error if it exists
        if hasattr(sd, '_check'):
            original_check = sd._check
            def safe_check(*args, **kwargs):
                # Prevent any stderr manipulation
                return original_check(*args, **kwargs)
            sd._check = safe_check
        
        # Method 3: Protect file descriptors
        original_stderr = sys.stderr
        
        # Create a hook to prevent stderr replacement
        def protect_stderr():
            if sys.stderr != original_stderr:
                sys.stderr = original_stderr
        
        # Install protection
        atexit.register(protect_stderr)
        
    except Exception as e:
        # Log but continue - audio might still work
        if DEBUG:
            # Can't use logger here as it's not initialized yet
            print(f"DEBUG: Could not fully disable sounddevice stderr redirect: {e}", file=sys.stderr)

# ==================== HTTP CLIENT CONFIGURATION ====================

# HTTP client configuration for OpenAI clients
HTTP_CLIENT_CONFIG = {
    'timeout': {
        'total': 30.0,
        'connect': 5.0
    },
    'limits': {
        'max_keepalive_connections': 5,
        'max_connections': 10
    }
}

# ==================== INITIALIZATION ====================

# Initialize directories on module import
initialize_directories()

# Apply sounddevice workaround on module import
disable_sounddevice_stderr_redirect()

# Set up logger
logger = setup_logging()

# Log any format validation warnings
if 'AUDIO_FORMAT' in locals() and '_invalid_audio_format' in locals():
    logger.warning(f"Unsupported audio format '{_invalid_audio_format}', falling back to 'pcm'")

if 'TTS_AUDIO_FORMAT' in locals() and '_invalid_tts_format' in locals():
    logger.warning(f"Unsupported TTS audio format '{_invalid_tts_format}', falling back to '{AUDIO_FORMAT}'")

if 'STT_AUDIO_FORMAT' in locals() and '_invalid_stt_format' in locals():
    logger.warning(f"Unsupported STT audio format '{_invalid_stt_format}', falling back to '{AUDIO_FORMAT}'")

# ==================== AUDIO FORMAT UTILITIES ====================

def get_provider_supported_formats(provider: str, operation: str = "tts") -> list:
    """Get list of audio formats supported by a provider.
    
    Args:
        provider: Provider name (e.g., 'openai', 'kokoro', 'whisper-local')
        operation: 'tts' or 'stt'
    
    Returns:
        List of supported format strings
    """
    # Provider format capabilities
    # Based on API documentation and testing
    provider_formats = {
        # TTS providers
        "openai": {
            "tts": ["opus", "mp3", "aac", "flac", "wav", "pcm"],
            "stt": ["mp3", "opus", "wav", "flac", "m4a", "webm"]
        },
        "kokoro": {
            "tts": ["mp3", "opus", "flac", "wav", "pcm"],  # AAC is not currently supported
            "stt": []  # Kokoro is TTS only
        },
        # STT providers
        "whisper-local": {
            "tts": [],  # Whisper is STT only
            "stt": ["wav", "mp3", "opus", "flac", "m4a"]
        },
        "openai-whisper": {
            "tts": [],  # Whisper is STT only
            "stt": ["mp3", "opus", "wav", "flac", "m4a", "webm"]
        }
    }
    
    provider_info = provider_formats.get(provider, {})
    return provider_info.get(operation, [])


def validate_audio_format(format: str, provider: str, operation: str = "tts") -> str:
    """Validate and potentially adjust audio format based on provider capabilities.
    
    Args:
        format: Requested audio format
        provider: Provider name
        operation: 'tts' or 'stt'
    
    Returns:
        Valid format for the provider (may differ from requested)
    """
    supported = get_provider_supported_formats(provider, operation)
    
    if not supported:
        logger.warning(f"Provider '{provider}' does not support {operation} operation")
        return format
    
    if format in supported:
        return format
    
    # Fallback logic - prefer common formats
    fallback_order = ["opus", "mp3", "wav"]
    for fallback in fallback_order:
        if fallback in supported:
            logger.info(f"Format '{format}' not supported by {provider}, using '{fallback}' instead")
            return fallback
    
    # Last resort - use first supported format
    first_supported = supported[0]
    logger.warning(f"Using {provider}'s first supported format: {first_supported}")
    return first_supported


def get_audio_loader_for_format(format: str):
    """Get the appropriate AudioSegment loader for a format.
    
    Args:
        format: Audio format string
    
    Returns:
        AudioSegment method reference or None
    """
    from pydub import AudioSegment
    
    format_loaders = {
        "mp3": AudioSegment.from_mp3,
        "wav": AudioSegment.from_wav,
        "opus": AudioSegment.from_ogg,  # Opus uses OGG container
        "flac": AudioSegment.from_file if not hasattr(AudioSegment, 'from_flac') else AudioSegment.from_flac,
        "aac": AudioSegment.from_file,  # Generic loader for AAC
        "m4a": AudioSegment.from_file,  # Generic loader for M4A
        "webm": AudioSegment.from_file,  # Generic loader for WebM
        "ogg": AudioSegment.from_ogg,
        "pcm": AudioSegment.from_raw  # Requires additional parameters
    }
    
    return format_loaders.get(format)


def get_format_export_params(format: str) -> dict:
    """Get export parameters for a specific audio format.
    
    Args:
        format: Audio format string
    
    Returns:
        Dict with export parameters for pydub
    """
    params = {
        "format": format
    }
    
    if format == "mp3":
        params["bitrate"] = MP3_BITRATE
    elif format == "opus":
        # Opus in OGG container
        params["format"] = "opus"  # pydub uses 'opus' for OGG/Opus
        params["parameters"] = ["-b:a", str(OPUS_BITRATE)]
    elif format == "aac":
        params["bitrate"] = AAC_BITRATE
    elif format == "flac":
        # FLAC is lossless, no bitrate setting
        pass
    elif format == "wav":
        # WAV is uncompressed, no bitrate setting
        pass
    
    return params
