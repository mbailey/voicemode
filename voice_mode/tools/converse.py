"""Conversation tools for interactive voice interactions."""

import asyncio
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
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
from voice_mode.conch import Conch, _get_hold_expiry
from voice_mode.conch_queue import ConchQueue
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
    REPEAT_MAX_LEADING_WORDS,
    WAIT_MAX_LEADING_WORDS,
    WAIT_DURATION,
    METRICS_LEVEL,
    STT_AUDIO_FORMAT,
    STT_SAVE_FORMAT,
    MP3_BITRATE,
    CONCH_ENABLED,
    CONCH_TIMEOUT,
    CONCH_CHECK_INTERVAL,
    CONCH_MODE,
    AUTO_FOCUS_PANE,
    MAX_LISTEN_DURATION,
    SILENCE_RELEASE_SEC,
    SIGNIFICANCE_THRESHOLD_SEC,
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
    log_tool_request_end,
    update_latest_symlinks
)
from voice_mode.pronounce import get_manager as get_pronounce_manager, is_enabled as pronounce_enabled
from voice_mode.tools.silence_profile import SilenceProfile
from voice_mode.control_channel import get_control_state, intent_sentence, COMMAND_SKIP_BACK
from voice_mode.control_socket import start_control_listener, stop_control_listener
from voice_mode.history_buffer import get_history_buffer

logger = logging.getLogger("voicemode")

# Log silence detection config at module load time
logger.info(f"Module loaded with DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}")


def is_tmux() -> bool:
    """Check if the current process is running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def _resolve_silence_release(silence_release_sec, disable_silence_detection) -> float:
    """Deprecated disable flag is an alias for -1 (never release). Otherwise
    use the explicit value, or the config default when None."""
    if disable_silence_detection:
        return -1.0
    if silence_release_sec is None:
        return float(SILENCE_RELEASE_SEC)
    return float(silence_release_sec)


def _clamp_listen(value: float) -> float:
    return min(float(value), MAX_LISTEN_DURATION)


def _is_focus_held() -> bool:
    """Check if another tool recently took visual focus (the 'visual conch').

    Returns True if ~/.voicemode/focus-hold exists and was modified within
    the hold period, meaning auto-focus should be suppressed to let the
    user view what was shown (e.g. a file opened by show-me).

    The hold duration is read from the file contents (written by show-me's
    --hold flag), falling back to VOICEMODE_FOCUS_HOLD_SECONDS env var,
    then 30 seconds.
    """
    hold_file = os.path.expanduser("~/.voicemode/focus-hold")
    default_hold = float(os.environ.get("VOICEMODE_FOCUS_HOLD_SECONDS", "30"))
    try:
        age = time.time() - os.path.getmtime(hold_file)
        # Read hold duration from file (written by show-me --hold)
        try:
            with open(hold_file) as f:
                hold_seconds = float(f.read().strip())
        except (ValueError, OSError):
            hold_seconds = default_hold
        return age < hold_seconds
    except (OSError, ValueError):
        return False


def focus_tmux_pane() -> None:
    """Make the agent's tmux window visible, and optionally switch a client.

    Steps:
    1. Check autofocus-disabled sentinel — skip if user has toggled autofocus off
    2. Check focus-hold sentinel — skip if another tool recently took focus
    3. select-window: make the agent's window current (without changing active pane)
    4. Check if any client is already showing this session — if so, stop
    5. If no client is showing the session, switch the focused client to it

    Deliberately does NOT call select-pane — this avoids stealing focus from
    whichever pane the user is currently working in.  The window becomes
    visible so the user can see the agent is speaking, but their cursor stays
    where it was.

    Silent no-op if not in tmux, TMUX_PANE is unset, or tmux is not found.
    """
    import subprocess

    tmux_pane = os.environ.get("TMUX_PANE", "")
    if not tmux_pane:
        return

    # Respect the autofocus quick-toggle sentinel — user disabled via
    # `voicemode autofocus off`. Overrides VOICEMODE_AUTO_FOCUS_PANE.
    from voice_mode.cli_commands.autofocus import is_autofocus_disabled_by_sentinel
    if is_autofocus_disabled_by_sentinel():
        return

    # Respect the visual conch — another tool recently took focus
    if _is_focus_held():
        return

    try:
        # Select the window containing our pane (without changing active pane).
        # This makes the window visible but doesn't steal focus from whichever
        # pane the user is currently looking at.
        subprocess.run(["tmux", "select-window", "-t", tmux_pane], capture_output=True)

        # Find which session owns this pane
        r = subprocess.run(
            ["tmux", "display-message", "-t", tmux_pane, "-p", "#{session_name}"],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            return
        session_name = r.stdout.strip()

        # Check if any client is already attached to this session
        r = subprocess.run(
            ["tmux", "list-clients", "-t", session_name, "-F", "#{client_tty}"],
            capture_output=True, text=True
        )
        if r.returncode == 0 and r.stdout.strip():
            # Session already visible in a terminal — don't steal focus
            return

        # No client is showing our session — switch the focused client to it
        r = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_tty} #{client_flags}"],
            capture_output=True, text=True
        )
        for line in r.stdout.strip().split("\n"):
            parts = line.split(" ", 1)
            if len(parts) == 2 and "focused" in parts[1]:
                client_tty = parts[0]
                subprocess.run(
                    ["tmux", "switch-client", "-c", client_tty, "-t", session_name],
                    capture_output=True
                )
                break
    except FileNotFoundError:
        pass  # tmux binary not installed


# DJ Ducking Configuration
DJ_SOCKET_PATH = "/tmp/voicemode-mpv.sock"
DJ_VOLUME_DUCK_AMOUNT = int(os.environ.get("VOICEMODE_DJ_DUCK_AMOUNT", "20"))  # Volume reduction during TTS


def _dj_command(cmd: str) -> Optional[str]:
    """Send a command to mpv-dj via IPC socket.

    Args:
        cmd: JSON command to send (e.g., '{ "command": ["get_property", "volume"] }')

    Returns:
        Response string from mpv, or None if DJ not running
    """
    import subprocess
    import json

    if not os.path.exists(DJ_SOCKET_PATH):
        return None

    try:
        result = subprocess.run(
            ["socat", "-", DJ_SOCKET_PATH],
            input=cmd + "\n",
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_dj_volume() -> Optional[float]:
    """Get current DJ volume level.

    Returns:
        Current volume (0-100) or None if DJ not running
    """
    import json
    response = _dj_command('{ "command": ["get_property", "volume"] }')
    if response:
        try:
            data = json.loads(response)
            if "data" in data:
                return float(data["data"])
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
    return None


def set_dj_volume(volume: float) -> bool:
    """Set DJ volume level.

    Args:
        volume: Volume level (0-100)

    Returns:
        True if successful, False otherwise
    """
    import json
    volume = max(0, min(100, volume))  # Clamp to valid range
    response = _dj_command(f'{{ "command": ["set_property", "volume", {volume}] }}')
    if response:
        try:
            data = json.loads(response)
            return data.get("error") == "success"
        except json.JSONDecodeError:
            pass
    return False


class DJDucker:
    """Context manager for ducking DJ volume during TTS playback."""

    def __init__(self, duck_amount: int = None):
        self.duck_amount = duck_amount if duck_amount is not None else DJ_VOLUME_DUCK_AMOUNT
        self.original_volume: Optional[float] = None
        self.ducked = False

    def __enter__(self):
        self.original_volume = get_dj_volume()
        if self.original_volume is not None:
            ducked_volume = max(0, self.original_volume - self.duck_amount)
            if set_dj_volume(ducked_volume):
                self.ducked = True
                logger.debug(f"DJ ducked: {self.original_volume:.0f}% -> {ducked_volume:.0f}%")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.ducked and self.original_volume is not None:
            if set_dj_volume(self.original_volume):
                logger.debug(f"DJ restored: {self.original_volume:.0f}%")
        return False  # Don't suppress exceptions


def _matching_trailing_phrase(text: str, phrases, max_leading_words: int):
    """
    Return the trigger phrase a message ends with, but ONLY when it is a
    genuine standalone request rather than a long utterance that happens to
    end with a trigger word.

    A phrase matches when:
      - it appears at the end of the (normalized) text, AND
      - it sits on a word boundary (so "what" does not match "somewhat"), AND
      - the number of words BEFORE the phrase is <= max_leading_words.

    This prevents data loss: a substantive 30-word sentence ending in "what"
    is delivered intact, while a bare "what?" (0 leading words) still fires.
    See VM-291.

    Args:
        text: The transcribed text to check
        phrases: Iterable of trigger phrases
        max_leading_words: Max words allowed before the phrase for it to fire

    Returns:
        The matched phrase (str) or None.
    """
    if not text:
        return None

    # Normalize text for comparison (lowercase, strip whitespace and punctuation)
    import string
    normalized_text = text.lower().strip().rstrip(string.punctuation).strip()
    if not normalized_text:
        return None

    for phrase in phrases:
        p = phrase.lower().strip()
        if not p:
            continue
        if not normalized_text.endswith(p):
            continue

        prefix = normalized_text[:-len(p)]
        # Require a word boundary before the phrase so e.g. "somewhat" does not
        # match the trigger "what". An empty prefix means the whole message is
        # the phrase.
        if prefix and not prefix[-1].isspace():
            continue

        leading_words = len(prefix.split())
        if leading_words <= max_leading_words:
            return phrase

    return None


def should_repeat(text: str) -> bool:
    """
    Check if the transcribed text is a standalone repeat request.

    Returns True only when a repeat phrase is at the end AND preceded by at
    most REPEAT_MAX_LEADING_WORDS words, so long messages ending in a trigger
    word are not discarded (VM-291).
    """
    phrase = _matching_trailing_phrase(text, REPEAT_PHRASES, REPEAT_MAX_LEADING_WORDS)
    if phrase is not None:
        logger.info(f"Repeat phrase detected: '{phrase}' in '{text}'")
        return True
    return False


def should_wait(text: str) -> bool:
    """
    Check if the transcribed text is a standalone wait request.

    Returns True only when a wait phrase is at the end AND preceded by at most
    WAIT_MAX_LEADING_WORDS words, so long messages ending in a trigger word
    are not discarded (VM-291). WAIT_MAX_LEADING_WORDS can be raised once
    VM-1493 preserves pre-trigger speech across the pause.
    """
    phrase = _matching_trailing_phrase(text, WAIT_PHRASES, WAIT_MAX_LEADING_WORDS)
    if phrase is not None:
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
    from voice_mode.voice_profiles import is_clone_voice, get_profile

    # Check if this is a clone voice — override provider/model/base_url
    if voice and is_clone_voice(voice):
        profile = get_profile(voice)
        logger.info(f"Voice '{voice}' is a clone profile: {profile.description}")
        return {
            'base_url': profile.base_url,
            'model': profile.model,
            'voice': voice,
            'instructions': None,
            'provider_type': 'clone'
        }

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



def resolve_ref_text(ref_text: Optional[str]) -> Optional[str]:
    """Resolve a ``ref_text`` argument that may be a file path OR literal text.

    Auto-detect: if the value names an existing file, its contents (stripped)
    are used as the transcript; otherwise the value is treated as the literal
    transcript text. Returns ``None`` when no override was supplied, so callers
    can distinguish "use the profile/sidecar transcript" from an explicit
    override.

    Note: path detection is local-only. For a remote TTS host the *audio*
    path must exist on that host, but ``ref_text`` is sent as a string, so
    reading the transcript file locally here is always correct.
    """
    if ref_text is None:
        return None
    candidate = os.path.expanduser(ref_text)
    try:
        if os.path.isfile(candidate):
            with open(candidate, "r") as fh:
                return fh.read().strip()
    except OSError:
        # Fall through and treat the value as literal text.
        pass
    return ref_text


async def text_to_speech_with_failover(
    message: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    instructions: Optional[str] = None,
    audio_format: Optional[str] = None,
    initial_provider: Optional[str] = None,
    speed: Optional[float] = None,
    ref_text: Optional[str] = None
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
        speed=speed,
        ref_text=ref_text
    )


async def synthesize_turn_with_failover(
    message: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    instructions: Optional[str] = None,
    audio_format: Optional[str] = None,
    initial_provider: Optional[str] = None,
    speed: Optional[float] = None,
    ref_text: Optional[str] = None,
):
    """Synthesize one turn to decoded audio samples WITHOUT playing it (VM-1772).

    Synth-only sibling of :func:`text_to_speech_with_failover`, used by the
    multi-utterance pipeline so turn N+1 can be generated while turn N plays.

    Returns:
        Tuple of (success, samples, sample_rate, metrics, config).
    """
    # Apply pronunciation rules if enabled (parity with the play path).
    if pronounce_enabled():
        pronounce_mgr = get_pronounce_manager()
        message = pronounce_mgr.process_tts(message)

    from voice_mode.simple_failover import simple_tts_synthesize
    return await simple_tts_synthesize(
        text=message,
        voice=voice or TTS_VOICES[0],
        model=model or TTS_MODELS[0],
        instructions=instructions,
        audio_format=audio_format,
        debug=DEBUG,
        debug_dir=DEBUG_DIR if DEBUG else None,
        save_audio=SAVE_AUDIO,
        audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
        speed=speed,
        ref_text=ref_text,
    )


# ---------------------------------------------------------------------------
# VM-1772: multi-utterance turns[] support (speak-only, P1)
# ---------------------------------------------------------------------------

# P1 Turn schema (flat, additive). `play`/`ask`/`wait_for_response` keys are
# RESERVED for P2 (VM-1775) / P3 (VM-840) — present here only so we can reject
# them with a clear "not in P1" message rather than silently ignoring them.
_TURN_RESERVED_KEYS = {"play", "ask", "wait_for_response"}
_TURN_KNOWN_KEYS = {"say", "voice", "pause_after_ms", "tts_instructions", "speed"} | _TURN_RESERVED_KEYS


def _normalize_turns(
    turns,
    *,
    default_voice: Optional[str],
    default_pause_after_ms: int,
    default_tts_instructions: Optional[str],
    default_speed: Optional[float],
) -> list:
    """Validate and normalize the raw ``turns`` argument into a flat list.

    Each item is resolved against the call-level defaults so the pipeline can
    treat every turn uniformly: ``{say, voice, pause_after_ms, tts_instructions,
    speed}``. Raises ``ValueError`` (caught by ``converse`` and returned as an
    error string) on any malformed item.
    """
    if isinstance(turns, dict):
        # A single turn object passed unwrapped — accept it as a length-1 list.
        turns = [turns]
    if not isinstance(turns, (list, tuple)):
        raise ValueError("`turns` must be a list of turn objects.")

    normalized = []
    for i, raw in enumerate(turns):
        if not isinstance(raw, dict):
            raise ValueError(f"turn {i}: each turn must be an object, got {type(raw).__name__}.")

        # Reject reserved (future-phase) verbs explicitly so callers aren't
        # surprised by silent no-ops.
        for key in _TURN_RESERVED_KEYS:
            if key in raw and raw[key] not in (None, False):
                raise ValueError(
                    f"turn {i}: '{key}' is reserved for a later phase and is not "
                    f"supported in P1 (speak-only). Use 'say'."
                )

        say = raw.get("say")
        if say is None or not isinstance(say, str) or not say.strip():
            raise ValueError(f"turn {i}: 'say' is required and must be a non-empty string.")

        # pause_after_ms: per-turn override, else the call-level default.
        pause = raw.get("pause_after_ms", default_pause_after_ms)
        try:
            pause = int(pause)
        except (TypeError, ValueError):
            raise ValueError(f"turn {i}: 'pause_after_ms' must be an integer (got {pause!r}).")
        if pause < 0:
            raise ValueError(f"turn {i}: 'pause_after_ms' cannot be negative (got {pause}).")

        # speed: per-turn override, else call-level default.
        turn_speed = raw.get("speed", default_speed)
        if turn_speed is not None:
            try:
                turn_speed = float(turn_speed)
            except (TypeError, ValueError):
                raise ValueError(f"turn {i}: 'speed' must be a number (got {turn_speed!r}).")
            if not (0.25 <= turn_speed <= 4.0):
                raise ValueError(f"turn {i}: 'speed' must be between 0.25 and 4.0 (got {turn_speed}).")

        voice = raw.get("voice") or default_voice
        instructions = raw.get("tts_instructions") or default_tts_instructions

        normalized.append({
            "say": say,
            "voice": voice,
            "pause_after_ms": pause,
            "tts_instructions": instructions,
            "speed": turn_speed,
        })

    return normalized


def _play_samples_blocking(samples, sample_rate):
    """Play decoded samples to completion (blocking). Runs in a worker thread
    via ``asyncio.to_thread`` so the producer keeps synthesizing during playback."""
    player = NonBlockingAudioPlayer()
    player.play(samples, sample_rate, blocking=True)


async def _speak_turns_pipeline(
    turns,
    *,
    tts_model,
    tts_provider,
    audio_format,
    resolved_ref_text,
    should_skip_tts,
    lookahead: int = 1,
) -> list:
    """Producer/consumer pipeline: synthesize turn N+1 while turn N plays.

    A single producer walks the ordered ``turns`` list, synthesizing each to
    decoded audio and pushing onto a bounded queue (``maxsize=lookahead`` →
    "synth one ahead"). A single consumer drains the queue in order, plays each
    turn, then waits ``pause_after_ms`` before the next. After the first turn's
    synthesis, playback is continuous — the only inter-utterance gap is the
    configured pause (synth dead-air is hidden behind playback).

    Per-turn TTS failure is logged and skipped (the sequence continues), per the
    task's graceful-degradation requirement.

    Returns a list of per-turn result dicts (in order).
    """
    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, lookahead))
    SENTINEL = object()
    results: list = []
    n = len(turns)

    async def producer():
        for idx, turn in enumerate(turns):
            if should_skip_tts:
                await audio_queue.put({
                    "index": idx, "turn": turn, "samples": None, "sample_rate": None,
                    "success": True, "skipped": True, "metrics": {"generation": 0.0},
                })
                continue
            try:
                success, samples, sample_rate, metrics, _config = await synthesize_turn_with_failover(
                    message=turn["say"],
                    voice=turn["voice"],
                    model=tts_model,
                    instructions=turn["tts_instructions"],
                    audio_format=audio_format,
                    initial_provider=tts_provider,
                    speed=turn["speed"],
                    ref_text=resolved_ref_text,
                )
            except Exception as e:
                logger.error(f"Turn {idx} synthesis raised: {e}")
                success, samples, sample_rate, metrics = False, None, None, {}
            await audio_queue.put({
                "index": idx, "turn": turn, "samples": samples, "sample_rate": sample_rate,
                "success": bool(success), "metrics": metrics or {},
            })
        await audio_queue.put(SENTINEL)

    async def consumer():
        while True:
            item = await audio_queue.get()
            if item is SENTINEL:
                break
            idx = item["index"]
            turn = item["turn"]
            rec = {
                "index": idx,
                "voice": turn["voice"],
                "success": item["success"],
                "generation": item["metrics"].get("generation", 0.0),
                "playback": 0.0,
                "pause_after_ms": turn["pause_after_ms"],
            }
            if item.get("skipped"):
                rec["skipped"] = True
            elif item["success"] and item.get("samples") is not None:
                play_start = time.perf_counter()
                try:
                    await asyncio.to_thread(_play_samples_blocking, item["samples"], item["sample_rate"])
                except Exception as e:
                    logger.error(f"Turn {idx} playback failed: {e}")
                    rec["success"] = False
                rec["playback"] = time.perf_counter() - play_start
            else:
                logger.warning(f"Turn {idx} synthesis failed; skipping playback and continuing.")
            results.append(rec)

            # Pace: insert pause_after_ms after each turn except the last (a
            # trailing pause would only delay the return with nothing to follow).
            if idx < n - 1 and turn["pause_after_ms"] > 0:
                await asyncio.sleep(turn["pause_after_ms"] / 1000.0)

    await asyncio.gather(producer(), consumer())
    # Defensive: results are appended in consumption order (single ordered
    # producer + queue), but sort by index so callers never depend on timing.
    results.sort(key=lambda r: r["index"])
    return results


def _format_turns_result(results, metrics_level: str) -> Tuple[str, bool]:
    """Build the speak-only summary string for a turns[] run + overall success.

    Mirrors the single-message speak-only return, extended across N turns.
    """
    n_total = len(results)
    n_ok = sum(1 for r in results if r["success"])
    total_gen = sum(r["generation"] for r in results)
    total_play = sum(r["playback"] for r in results)

    if n_ok == 0:
        return (
            "Error: Could not speak any turn. All TTS attempts failed. "
            "Check that local services are running or set OPENAI_API_KEY for cloud fallback.",
            False,
        )

    failed_note = "" if n_ok == n_total else f" ({n_total - n_ok} failed)"

    if metrics_level == "minimal":
        return f"✓ Spoke {n_ok}/{n_total} turns{failed_note}", True

    summary = f"✓ Spoke {n_ok}/{n_total} turns{failed_note} (gen: {total_gen:.1f}s, play: {total_play:.1f}s)"
    if metrics_level == "verbose":
        lines = [summary]
        for r in results:
            status = "" if r["success"] else " [FAILED]"
            lines.append(
                f"  turn {r['index'] + 1} [{r['voice'] or 'default'}]: "
                f"gen {r['generation']:.2f}s, play {r['playback']:.2f}s, "
                f"pause {r['pause_after_ms']}ms{status}"
            )
        return "\n".join(lines), True
    return summary, True


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
    transport: str = "local",
    word_timestamps: bool = False,
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

        # Update latest symlinks for quick access to most recent STT audio
        update_latest_symlinks(save_file_path, "stt")

        # Use compressed audio for upload (temporary file)
        # Windows fix: close temp file before reopening (Issue #135)
        tmp_file = tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False)
        tmp_path = tmp_file.name
        try:
            tmp_file.write(compressed_audio)
            tmp_file.flush()
            tmp_file.close()  # Close before reopening on Windows

            with open(tmp_path, 'rb') as audio_file:
                result = await simple_stt_failover(
                    audio_file=audio_file,
                    word_timestamps=word_timestamps,
                )
        finally:
            # Clean up temp file (we keep the WAV)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    else:
        # Use temporary file that will be deleted
        # Windows fix: close temp file before reopening (Issue #135)
        tmp_file = tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False)
        tmp_path = tmp_file.name
        try:
            tmp_file.write(compressed_audio)
            tmp_file.flush()
            tmp_file.close()  # Close before reopening on Windows

            with open(tmp_path, 'rb') as audio_file:
                result = await simple_stt_failover(
                    audio_file=audio_file,
                    word_timestamps=word_timestamps,
                )
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

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


def _release_threshold_ms(silence_release_sec: float) -> float:
    """0 -> legacy SILENCE_THRESHOLD_MS; >0 -> scalar seconds in ms; <0 -> inf (never)."""
    if silence_release_sec > 0:
        return silence_release_sec * 1000
    if silence_release_sec < 0:
        return float("inf")
    return float(SILENCE_THRESHOLD_MS)


def _build_silence_profile(pre_speech_delay_s, total_silence_s, speech_active_s,
                           gaps, first_speech_start, recording_end):
    """Construct a SilenceProfile from record-loop tracker values."""
    longest_gap = max((e - s for (s, e) in gaps), default=0.0)
    return SilenceProfile(
        pre_speech_delay=pre_speech_delay_s,
        longest_gap=longest_gap,
        total_silence=total_silence_s,
        speech_active=speech_active_s,
        gaps=gaps,
        first_speech_start=first_speech_start,
        recording_end=recording_end,
    )


def _needs_word_timestamps(profile, threshold: float) -> bool:
    """Return True if word-level timestamps should be requested for this turn.

    Word timestamps are needed when the silence profile indicates a significant
    gap inside speech or a significant pre-speech pause, so downstream code can
    align words with those silences.
    """
    return bool(profile.significant_gaps(threshold)) or profile.pre_speech_significant(threshold)


def _want_words_for_turn(profile, measure_blocks: bool, threshold: float) -> bool:
    """When measure_blocks is on, words are needed to split text across blocks --
    but only if there is at least one gap (pre-speech or speech-internal).
    When off, defer to the significance-based marker path."""
    if profile is None:
        return False
    if measure_blocks:
        return bool(profile.gaps) or profile.first_speech_start > 1e-9
    return _needs_word_timestamps(profile, threshold)


def record_audio_with_silence_detection(max_duration: float, silence_release_sec: float = 0.0, min_duration: float = 0.0, vad_aggressiveness: Optional[int] = None) -> Tuple[np.ndarray, bool, "SilenceProfile"]:
    """Record audio from microphone with automatic silence detection.

    Uses WebRTC VAD to detect when the user stops speaking and automatically
    stops recording after a configurable silence threshold.

    Args:
        max_duration: Maximum recording duration in seconds
        silence_release_sec: Seconds of silence before stopping (0=legacy SILENCE_THRESHOLD_MS, -1=never stop on silence)
        min_duration: Minimum recording duration before silence detection can stop (default: 0.0)
        vad_aggressiveness: VAD aggressiveness level (0-3). If None, uses VAD_AGGRESSIVENESS from config

    Returns:
        Tuple of (audio_data, speech_detected, silence_profile):
            - audio_data: Numpy array of recorded audio samples
            - speech_detected: Boolean indicating if speech was detected during recording
            - silence_profile: SilenceProfile with timing data (SilenceProfile.empty() on fallback paths)
    """
    
    logger.info(f"record_audio_with_silence_detection called - VAD_AVAILABLE={VAD_AVAILABLE}, DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}, min_duration={min_duration}")
    
    if not VAD_AVAILABLE:
        logger.warning("webrtcvad not available, falling back to fixed duration recording")
        return (record_audio(max_duration), True, SilenceProfile.empty())

    global_disabled = DISABLE_SILENCE_DETECTION  # legacy global env still honored as -1
    effective_release = silence_release_sec
    if global_disabled and effective_release == 0.0:
        effective_release = -1.0
    if effective_release < 0:
        logger.info("Silence release disabled (silence_release_sec=-1): fixed-duration record")
        return (record_audio(max_duration), True, SilenceProfile.empty())
    
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
        # --- silence profile trackers ---
        pre_speech_delay_s = 0.0
        total_silence_s = 0.0
        speech_active_s = 0.0
        gaps: list = []              # completed speech-internal gaps (start_s, end_s)
        current_gap_start = None     # start time of an in-progress gap
        first_speech_start = None    # recording_duration when speech first detected
        
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
                    # VM-1676: honour a control-channel stop while listening, so a
                    # stop that arrives mid-record returns cleanly (converse then
                    # builds the normal control-marker result). Cheap snapshot;
                    # inert by default -- the state is 'running' unless the channel
                    # is enabled and a stop has actually fired.
                    snap = get_control_state().snapshot()
                    if snap.is_stopped:
                        logger.info("🛑 Recording stopped via control channel")
                        stop_recording = True
                        break
                    # VM-1685: a skip_back pressed while listening ends this
                    # recording early (peek only -- converse consumes the request,
                    # replays the cached audio, then re-listens). Without this we
                    # would wait for silence/timeout before the replay.
                    if snap.pending_transport == COMMAND_SKIP_BACK:
                        logger.info("⏮  Recording ended early by skip_back -- handing off to replay")
                        break
                    # VM-1754: a skip_forward pressed while listening ends this
                    # recording NOW -- the manual "I'm done, go now" end-of-turn
                    # and the VAD fallback for when silence detection isn't firing.
                    # A plain break: unlike the stop path we do NOT set
                    # stop_recording (so converse builds no [control: stop] marker),
                    # and unlike skip_back there is no replay -- whatever was
                    # captured so far is returned from this function and converse
                    # transcribes it. skip_forward is a sticky STATE
                    # (is_skip_forward, not a one-shot pending_transport), so
                    # converse consumes the edge with control_state.reset() once we
                    # return.
                    if snap.is_skip_forward:
                        logger.info("⏭  Recording ended early by skip_forward -- transcribing what we have")
                        break
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
                            # WAITING_FOR_SPEECH: accumulate pre-speech delay
                            if is_speech:
                                logger.info("🎤 Speech detected, starting active recording")
                                if VAD_DEBUG:
                                    logger.info(f"[VAD_DEBUG] STATE CHANGE: WAITING_FOR_SPEECH -> SPEECH_ACTIVE at t={recording_duration:.1f}s")
                                speech_detected = True
                                first_speech_start = recording_duration
                                silence_duration_ms = 0
                                speech_active_s += chunk_duration_s  # count first speech chunk
                            else:
                                pre_speech_delay_s += chunk_duration_s
                                total_silence_s += chunk_duration_s
                        else:
                            if is_speech:
                                # SPEECH_ACTIVE: close any in-progress gap
                                if current_gap_start is not None:
                                    gaps.append((current_gap_start, recording_duration))
                                    current_gap_start = None
                                speech_active_s += chunk_duration_s
                                silence_duration_ms = 0
                            else:
                                # SILENCE_AFTER_SPEECH
                                if current_gap_start is None:
                                    current_gap_start = recording_duration
                                silence_duration_ms += VAD_CHUNK_DURATION_MS
                                total_silence_s += chunk_duration_s
                                if VAD_DEBUG and silence_duration_ms % 100 == 0:
                                    logger.info(f"[VAD_DEBUG] Accumulating silence: {silence_duration_ms}ms, t={recording_duration:.1f}s")
                                elif silence_duration_ms % 200 == 0:
                                    logger.debug(f"Silence: {silence_duration_ms}ms")

                                effective_min_duration = max(MIN_RECORDING_DURATION, min_duration)
                                # Release threshold: 0 -> legacy SILENCE_THRESHOLD_MS; >0 -> scalar seconds.
                                release_ms = _release_threshold_ms(effective_release)
                                if recording_duration >= effective_min_duration and silence_duration_ms >= release_ms:
                                    logger.info(f"✓ Silence release reached after {recording_duration:.1f}s (threshold {release_ms:.0f}ms)")
                                    if VAD_DEBUG:
                                        logger.info(f"[VAD_DEBUG] STOP: silence_duration={silence_duration_ms}ms >= threshold={release_ms:.0f}ms")
                                        logger.info(f"[VAD_DEBUG] STOP: recording_duration={recording_duration:.1f}s >= min_duration={effective_min_duration}s")
                                    stop_recording = True
                                elif VAD_DEBUG and recording_duration < effective_min_duration:
                                    if int(recording_duration * 1000) % 500 == 0:
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
                # Close a gap still open at end-of-turn.
                if current_gap_start is not None:
                    gaps.append((current_gap_start, recording_duration))
                profile = _build_silence_profile(
                    pre_speech_delay_s=pre_speech_delay_s,
                    total_silence_s=total_silence_s,
                    speech_active_s=speech_active_s,
                    gaps=gaps,
                    first_speech_start=(first_speech_start or 0.0),
                    recording_end=recording_duration,
                )

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

                return (full_recording, speech_detected, profile)
            else:
                logger.warning("No audio chunks recorded")
                return (np.array([]), False, SilenceProfile.empty())
                
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
                    return record_audio_with_silence_detection(max_duration, silence_release_sec, min_duration, vad_aggressiveness)
                    
                except Exception as reinit_error:
                    logger.error(f"Failed to reinitialize audio: {reinit_error}")
                    # Fall through to normal error handling
            
            # Get helpful error message
            help_message = get_audio_error_help(e)
            logger.error(f"\n{help_message}")
            
            logger.info("Falling back to fixed duration recording")
            return (record_audio(max_duration), True, SilenceProfile.empty())

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
        return (record_audio(max_duration), True, SilenceProfile.empty())


# ==================== CONTROL CHANNEL (VM-1676) ====================
#
# A control-channel `stop` makes converse return NORMALLY with a control marker
# in the result string -- the agent reads an ordinary tool result and continues
# (e.g. switches to text). This is deliberately NOT the asyncio.CancelledError /
# ESC path, so the MCP server is never torn down and no `/mcp` reconnect is
# needed. The listener + the control state are inert when the channel is
# disabled (default), so all of this is a no-op on the normal path.

@asynccontextmanager
async def _control_listener_scope():
    """Reset the control state and run the socket listener for one audio op.

    Entered *inside* ``audio_operation_lock`` (see converse) so the listener's
    start/stop stay serialized with every other audio operation -- only the
    currently-speaking server owns the single well-known socket. The listener is
    config-gated and bind failures are non-fatal, so when the channel is disabled
    this is a cheap no-op wrapped around an inert control state. ``reset`` clears
    any latched stop from a previous utterance so it can never leak across turns.

    Yields the process-wide ``ControlState`` so the caller can poll its snapshot.
    """
    control_state = get_control_state()
    control_state.reset()
    start_control_listener()
    try:
        yield control_state
    finally:
        stop_control_listener()


def _format_control_timing(timings: Dict) -> str:
    """Format whatever timing fields exist so far into the usual ``k v.vs`` string."""
    parts = []
    if 'ttfa' in timings:
        parts.append(f"ttfa {timings['ttfa']:.1f}s")
    if 'tts_gen' in timings:
        parts.append(f"gen {timings['tts_gen']:.1f}s")
    if 'tts_play' in timings:
        parts.append(f"play {timings['tts_play']:.1f}s")
    if 'record' in timings:
        parts.append(f"record {timings['record']:.1f}s")
    return ", ".join(parts)


def _build_control_stop_result(snapshot, timings: Dict) -> str:
    """Build the NORMAL converse return string for a control-channel stop.

    Shape: ``[control: stop] <server-owned sentence> | Timing: ...``.

    SECURITY (F1 / VM-1691): the detail is a **server-authored** sentence chosen
    by the stop command's named ``hint`` (validated against
    ``control_channel.CONTROL_INTENTS`` at parse time). Caller-supplied free text
    is NEVER surfaced -- a stop's free-form ``message`` is logged locally only, so
    a local process can't inject instructions into the agent's tool-result. The
    leading ``[control: stop]`` marker lets the agent distinguish an intentional
    cut-short turn from a normal voice response.
    """
    detail = intent_sentence(snapshot.hint) or "playback stopped via control channel"
    if snapshot.message:
        # Accepted for operator logs, deliberately kept out of the agent context.
        logger.info(
            "control stop carried a free-form message (not surfaced to agent): %r",
            snapshot.message[:256],
        )
    result = f"[control: stop] {detail}"
    timing_str = _format_control_timing(timings)
    if timing_str:
        result += f" | Timing: {timing_str}"
    return result


async def _drain_skip_back(control_state, replay_cursor: int) -> int:
    """Consume pending skip_back presses, replaying cached audio (VM-1685, CD cursor).

    Drains every queued ``skip_back`` transport request, re-playing the targeted
    history-buffer entry through the normal playback path, and returns the
    updated cursor. CD-player semantics over the history buffer:

    * ``replay_cursor`` is how many entries back from the newest we are. Each
      press steps one further back (``get(-cursor)``), clamped to the buffer
      depth -- pressing past the oldest entry just re-plays the oldest (a CD
      stays on track 1).
    * The first press (cursor 0 -> 1) re-plays the newest entry. Since
      impl-drain-restart drains an interrupted utterance fully into the buffer
      before handing off here, that newest entry is the **current** utterance --
      so a mid-playback skip_back **restarts the current utterance from its
      start** (true CD behaviour), and each further press steps one entry back.

    Replay is **playback-layer only**: ``play_cached_utterance`` never invokes
    STT or the model, so skip_back can never start a new agent turn. It
    **composes with pause**: a press while paused lifts the hold so the replay is
    audible (a sticky stop is never cleared). A further press *during* a replay
    cuts it and is consumed on the next loop, so rapid presses step back quickly.
    """
    from voice_mode.streaming import play_cached_utterance, REPLAY_STOPPED

    buffer = get_history_buffer()
    while True:
        request = control_state.take_transport_request()
        if request != COMMAND_SKIP_BACK:
            # Nothing pending (or an unknown/forward request we don't handle here).
            return replay_cursor

        depth = len(buffer)
        if depth == 0:
            logger.info("skip_back ignored -- history buffer empty")
            continue

        # A skip_back while paused means "let me hear it" -- lift the hold so the
        # replay actually plays. Never touch a sticky stop.
        if control_state.snapshot().is_paused:
            control_state.request_resume()

        replay_cursor = min(replay_cursor + 1, depth)
        record = buffer.get(-replay_cursor)
        if record is None:  # pragma: no cover -- clamp above keeps it in range
            continue

        logger.info(
            "skip_back: replaying history entry -%d/%d (%.1fs)",
            replay_cursor, depth, record.duration,
        )
        reason = await play_cached_utterance(record, control_state)
        if reason == REPLAY_STOPPED:
            # A stop during the replay ends the turn; let converse's stop check
            # build the control-stop result.
            return replay_cursor
        # On a transport interrupt (a further press) the loop consumes it next.


def _assemble_voice_result(response_text, stt_info, timing_str, metrics_level, profile, words, threshold, measure_blocks: bool = False):
    """Assemble the result string for a voice turn.

    measure_blocks on: transcript body is the VAD block timeline; the
    significant-silence markers and Silence: field are suppressed (the timeline
    replaces them). measure_blocks off: existing marker/Silence path."""
    from voice_mode.tools.silence_markers import insert_markers, format_silence_field
    if measure_blocks and profile is not None:
        from voice_mode.tools.block_timeline import render_block_timeline
        text = render_block_timeline(profile, words, response_text)
        silence_field = None
    else:
        text = insert_markers(response_text, words, profile, threshold) if profile is not None else response_text
        silence_field = format_silence_field(profile, threshold) if profile is not None else None

    if metrics_level == "minimal":
        return f"Voice response: {text}"
    if metrics_level == "verbose":
        parts = [f"Voice response: {text}{stt_info}"]
        if profile is not None:
            parts.append(f"Silence: pre {profile.pre_speech_delay:.1f}s, gap {profile.longest_gap:.1f}s, "
                         f"total {profile.total_silence:.1f}s, speech {profile.speech_active:.1f}s")
        parts.append(f"Timing: {timing_str}")
        return " | ".join(parts)
    # summary (default)
    seg = f"Voice response: {text}{stt_info}"
    if silence_field:
        seg += f" | Silence: {silence_field}"
    seg += f" | Timing: {timing_str}"
    return seg


@mcp.tool()
async def converse(
    message: Optional[str] = None,
    turns: Optional[list] = None,
    pause_after_ms: int = 150,
    wait_for_response: Union[bool, str] = True,
    listen_duration_max: float = DEFAULT_LISTEN_DURATION,
    listen_duration_min: float = 2.0,
    timeout: float = 60.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None,
    tts_model: Optional[str] = None,
    tts_instructions: Optional[str] = None,
    chime_enabled: Optional[Union[bool, str]] = None,
    audio_format: Optional[str] = None,
    disable_silence_detection: Union[bool, str] = False,
    silence_release_sec: Optional[Union[float, str]] = None,
    measure_blocks: Union[bool, str] = False,
    speed: Optional[float] = None,
    vad_aggressiveness: Optional[Union[int, str]] = None,
    skip_tts: Optional[Union[bool, str]] = None,
    chime_leading_silence: Optional[float] = None,
    chime_trailing_silence: Optional[float] = None,
    metrics_level: Optional[Literal["minimal", "summary", "verbose"]] = None,
    wait_for_conch: Union[bool, str, int, float] = False,
    conch_mode: Optional[Literal["wait", "callback"]] = None,
    hold_conch: Union[bool, str] = False,
    conch_hold_timeout: Optional[Union[float, str]] = None,
    skip_conch: Union[bool, str] = False,
    session_id: Optional[str] = None,
    ref_text: Optional[str] = None,
) -> str:
    """Have an ongoing voice conversation - speak a message and optionally listen for response.

Multi-agent turn-taking: if your next converse call will continue this thread (asking a question you'll answer, or speaking across several turns), pass hold_conch=true so other agents wait instead of cutting in at the turn boundary.

<echo>Transcript visibility: print `> **ASSISTANT (voicemode):** <message>` before calling, and `> **USER (voicemode):** <reply>` after a spoken reply, so the conversation stays readable in the transcript. Skip if the user opted out of echo.</echo>

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
   - voice://voices - JSON list of available TTS voices
     (filter by provider with voice://voices/{provider}, e.g. voice://voices/kokoro)
   - voice://voices/persona convention — a voice's character (who they are, how they
     speak, sample lines) lives at ~/.voicemode/voices/<name>/README.md; read it before
     speaking in-character (index: PERSONAS.md). MCP-resource version planned: VM-1222.

KEY PARAMETERS:
• message (string): The message to speak (required unless `turns` is given)
• turns (list, optional): Speak an ordered multi-voice sequence in ONE call,
  gap-free — turn N+1 is synthesized while turn N plays (no synth dead-air).
  Each turn is an object: {"say": str (required), "voice"?: str,
  "pause_after_ms"?: int, "tts_instructions"?: str, "speed"?: float}. Per-turn
  `voice` overrides the call-level `voice`. Speak-only (no reply collection in
  this version). If both `message` and `turns` are given, `turns` wins.
• pause_after_ms (int, default: 150): Silence inserted after each turn in a
  `turns` sequence; a turn's own `pause_after_ms` overrides this. 0 = gap-free.
• wait_for_response (bool, default: true): Listen for response after speaking
• voice (string): TTS voice name (auto-selected unless specified)
  - To list available voices, read MCP resource voice://voices
  - An absolute path to a .wav clones from that clip directly (no profile needed)
  - The chosen voice is recorded in the conch, so in a multi-agent session you
    can read another agent's voice (Conch.get_holder) and pick a different one
    to avoid a voice clash.
• ref_text (string): Reference transcript for clip-based cloning. A file path
  is read; anything else is the literal transcript. Overrides any sidecar.
  Only used with a clone voice (abs-path clip or registered profile).
• tts_provider ("openai"|"kokoro"): Provider selection (auto-selected unless specified)
• disable_silence_detection (bool, default: false): Disable auto-stop on silence
• vad_aggressiveness (0-3, default: 3): Voice detection strictness (0=permissive, 3=strict)
• speed (0.25-4.0): Speech rate (1.0=normal, 2.0=double speed)
• chime_enabled (bool): Enable/disable audio feedback chimes
• chime_leading_silence (float): Silence before chime in seconds
• chime_trailing_silence (float): Silence after chime in seconds
• metrics_level ("minimal"|"summary"|"verbose"): Output detail level
  - minimal: Just response text (saves tokens)
  - summary: Response + compact timing (default)
  - verbose: Response + detailed metrics breakdown
• wait_for_conch (bool|number, default: false): Multi-agent coordination — the
  GATE for whether a busy conch puts you in the waiter queue at all.
  - false: If another agent is speaking, return a status immediately WITHOUT
    queuing (back-compat; you are never silently blocked). The status names the
    holder and tells you how to queue.
  - true: Join the FIFO waiter queue (you show up in `voicemode conch status`),
    then behave per conch_mode (below). Fast-fails the moment the holder dies.
  - a number: As true, but wait at most that many seconds, overriding the
    configured default timeout for this call.
• conch_mode ("wait"|"callback", default: VOICEMODE_CONCH_MODE, itself "wait"):
  How a queued caller is served once wait_for_conch has engaged the queue. Has
  NO effect unless wait_for_conch is truthy.
  - wait: Block until the conch is granted to you (FIFO; the queue's grant hint
    ensures only the next-in-line acquires — no thundering-herd steal), bounded
    by the timeout. On timeout you are cleanly deregistered.
  - callback: Register and return IMMEDIATELY with your queue position; your
    message is NOT spoken now. When the conch is granted to you, your turn is
    actively delivered out-of-band: a session nudge prompts you to call
    converse() and take the floor (requires a session id; `voicemode conch
    status` is always available as a supplementary view of your place in line).
    You stay registered — that's the point.
• hold_conch (bool, default: false): Keep the floor across turns (opt-in)
  - WHEN: set true if your NEXT converse call will continue this thread —
    you're asking a question you'll answer, or speaking over several turns —
    so other agents queue instead of cutting in at the turn boundary. Leave
    false (the default) for a one-off reply that ends the exchange.
  - The hold is a SHORT, refreshed TTL: each converse(hold_conch=true)
    re-stamps it to now + the hold timeout (default ~10s). Keep conversing
    inside the window and the floor stays yours; stop and within the window
    the hold lapses and the next queued agent is promoted — no stale wedge.
    Released immediately by your next converse(hold_conch=false), your process
    exiting, or idle-expiry. For a deliberate pause, use pause_conversation.
• conch_hold_timeout (number, optional): Override the hold idle-expiry TTL for
  THIS hold, in seconds (default: VOICEMODE_CONCH_HOLD_EXPIRY, ~10s). Only has
  effect alongside hold_conch=true. The value is stamped into the conch lock so
  OTHER agents honour your chosen window — raise it when you know the next turn
  needs longer (heavy tool use between turns), lower it to release faster.
• skip_conch (bool, default: false): Bypass conch entirely
  - false: Honour the conch lock (default multi-agent coordination)
  - true: Don't try to acquire or release the conch -- speak immediately
    regardless of whether another agent holds it (including a hold). Deliberate
    escape hatch for overriding a stuck holder; not a fallback for a timeout.
• session_id (string, optional): Caller-provided harness session ID, stored
  verbatim in the conch lock so tooling can see which *session* holds the
  floor. Falls back to VOICEMODE_SESSION_ID / CLAUDE_CODE_SESSION_ID from the
  environment (stdio transport only) when not passed.

TIMING PARAMETERS (usually leave at defaults):
  Silence detection handles most cases automatically. Only override these if
  silence detection is disabled or the user reports being cut off.
  Defaults are configurable by the user via ~/.voicemode/voicemode.env.
• listen_duration_max (number, default: 120): Max listen time in seconds
• listen_duration_min (number, default: 2.0): Min recording time before silence detection

PRIVACY: Microphone access required when wait_for_response=true.
         Audio processed via STT service, not stored.

RECOGNITION TIP: If specific words are consistently misrecognized, configure
   VOICEMODE_STT_PROMPT for vocabulary biasing - see voicemode://docs/parameters

VOICEMODE ECHO (default ON): Some hosts (e.g. newer Claude Code) collapse MCP
   tool calls, hiding voice turns from the visible transcript. To keep voice
   exchanges readable on screen, echo each converse turn as Markdown blockquotes:
       > **ASSISTANT (voicemode):** <message arg, verbatim>
       [voicemode:converse tool call]
       > **USER (voicemode):** <captured user message, verbatim>
   - ASSISTANT echo: always (incl. wait_for_response=false). Verbatim — the
     exact string passed to `message`, not a paraphrase or reformat.
   - USER echo: only when a user message was captured (skip on empty result
     or transcription failure). Verbatim, no truncation.
   - Visual aids (lists, tables, code) may follow AFTER the blockquote, not
     inside it — the blockquote stays a clean verbatim copy of what was spoken.
   - Don't double-echo content already visible as prose.
   - Disable on request — canonical phrase: "disable voicemode echo".

For complete parameter list, advanced options, and detailed examples,
consult the MCP resources listed above.
    """
    # Convert string booleans to actual booleans
    if isinstance(wait_for_response, str):
        wait_for_response = wait_for_response.lower() in ('true', '1', 'yes', 'on')
    if isinstance(disable_silence_detection, str):
        disable_silence_detection = disable_silence_detection.lower() in ('true', '1', 'yes', 'on')
    if isinstance(measure_blocks, str):
        measure_blocks = measure_blocks.lower() in ('true', '1', 'yes', 'on')
    effective_measure_blocks = bool(measure_blocks)
    if isinstance(chime_enabled, str):
        chime_enabled = chime_enabled.lower() in ('true', '1', 'yes', 'on')
    if skip_tts is not None and isinstance(skip_tts, str):
        skip_tts = skip_tts.lower() in ('true', '1', 'yes', 'on')
    # wait_for_conch accepts bool | str | number. A positive number means
    # "wait at most that many seconds" (and implies waiting); truthy strings
    # use the configured default timeout.
    conch_wait_timeout = CONCH_TIMEOUT
    if isinstance(wait_for_conch, bool):
        pass
    elif isinstance(wait_for_conch, (int, float)):
        conch_wait_timeout = float(wait_for_conch)
        wait_for_conch = conch_wait_timeout > 0
    elif isinstance(wait_for_conch, str):
        s = wait_for_conch.strip().lower()
        if s in ('true', '1', 'yes', 'on'):
            wait_for_conch = True
        elif s in ('false', '0', 'no', 'off', ''):
            wait_for_conch = False
        else:
            try:
                conch_wait_timeout = float(s)
                wait_for_conch = conch_wait_timeout > 0
            except ValueError:
                wait_for_conch = False
    if isinstance(hold_conch, str):
        hold_conch = hold_conch.lower() in ('true', '1', 'yes', 'on')
    # conch_hold_timeout (VM-1649): per-call override for THIS hold's idle-expiry
    # TTL, in seconds. None ⇒ fall back to the configured CONCH_HOLD_EXPIRY
    # default. A numeric string is coerced; a non-numeric/negative value is
    # ignored (falls back to the default) so a typo never disables the safety
    # valve. It is threaded into the Conch payload so other agents honour it.
    resolved_hold_timeout: Optional[float] = None
    if conch_hold_timeout is not None:
        try:
            parsed = float(conch_hold_timeout)
            if parsed > 0:
                resolved_hold_timeout = parsed
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid conch_hold_timeout value {conch_hold_timeout!r}; "
                "using configured default"
            )
    if isinstance(skip_conch, str):
        skip_conch = skip_conch.lower() in ('true', '1', 'yes', 'on')
    # conch_mode (VM-1619) selects how a *queued* caller is served once
    # wait_for_conch has engaged the queue. The arg overrides the
    # VOICEMODE_CONCH_MODE config default (VM-1415); an unknown/empty value
    # falls back to "wait" so a typo never silently downgrades a wait into a
    # silent callback.
    if conch_mode is None:
        resolved_conch_mode = CONCH_MODE
    else:
        resolved_conch_mode = str(conch_mode).strip().lower()
    if resolved_conch_mode not in ("wait", "callback"):
        resolved_conch_mode = "wait"

    # Resolve the session ID and project path once, for the conch payload.
    # Precedence: explicit param > VOICEMODE_SESSION_ID > Claude Code's stdio
    # env vars > absent. Env is only meaningful for stdio transport (a
    # per-session child process); a shared serve/HTTP daemon simply won't have
    # these set, so reading them is safe.
    resolved_session_id = (
        session_id
        or os.environ.get("VOICEMODE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
    )
    try:
        resolved_project_path = os.getcwd()
    except OSError:
        resolved_project_path = None
    # The nominal voice this call will use (param, else the first configured
    # default). Resolved cheaply here (no provider/network) so it can go in the
    # conch for voice-clash avoidance (VM-914) — another agent can read the
    # holder's voice and choose a different one.
    resolved_voice = voice or (TTS_VOICES[0] if TTS_VOICES else None)

    # Resolve ref_text override once (path-vs-inline auto-detect). None means
    # "no override" — fall back to the resolved profile/sidecar transcript.
    resolved_ref_text = resolve_ref_text(ref_text)

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

    # VM-1772: normalize the optional turns[] list (speak-only multivoice). When
    # present it takes precedence over the scalar `message` (precedence is
    # resolved here, not in the schema — strict-mode JSON Schema has no oneOf).
    normalized_turns = None
    if turns is not None:
        try:
            normalized_turns = _normalize_turns(
                turns,
                default_voice=voice,
                default_pause_after_ms=pause_after_ms,
                default_tts_instructions=tts_instructions,
                default_speed=speed,
            )
        except ValueError as e:
            return f"❌ Error: {e}"
        if not normalized_turns:
            # Empty list -> nothing to speak via turns; fall back to `message`.
            normalized_turns = None

    # Neither a message nor turns -> nothing to speak. The MCP tool errors here
    # (the CLI keeps its default greeting upstream). `message == ""` stays valid
    # for the listen-only / continuous case, so only None counts as "absent".
    if normalized_turns is None and message is None:
        return ("❌ Error: converse needs either `message` (text to speak) or a "
                "non-empty `turns` list.")

    # When speaking turns, the scalar `message` is irrelevant; keep the
    # message-based logging/metrics below from tripping over None.
    if normalized_turns is not None and message is None:
        message = ""

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
    conch = Conch(  # Named for event logging
        agent_name="converse",
        session_id=resolved_session_id,
        project_path=resolved_project_path,
        voice=resolved_voice,
        hold_timeout=resolved_hold_timeout,  # VM-1649 per-call hold TTL override
    )

    try:
        # Try to acquire conch atomically (no race condition)
        # skip_conch=true bypasses coordination entirely: don't acquire, don't
        # check the holder, don't release. Speak regardless of who else has it.
        if CONCH_ENABLED and not skip_conch:
            acquired = conch.try_acquire()

            if not acquired:
                # Another agent holds the conch (or a grant points elsewhere).
                holder = Conch.get_holder()
                holder_agent = holder.get('agent', 'unknown') if holder else 'unknown'

                if event_logger:
                    event_logger.log_event("CONCH_BLOCKED", {
                        "pid": os.getpid(),
                        "holder_pid": holder.get('pid') if holder else None,
                        "holder_agent": holder_agent,
                        "wait_for_conch": wait_for_conch,
                        "conch_mode": resolved_conch_mode,
                    })

                if not wait_for_conch:
                    # Gate closed (default): return IMMEDIATELY without queuing.
                    # Mike's hard constraint — never silently block a caller who
                    # did not opt in. Leave no registration behind. Tell them how
                    # to engage the queue (and that a callback is an option).
                    return (
                        f"{holder_agent} currently holds the voice channel — your "
                        f"message was NOT spoken, and you are NOT queued. Pass "
                        f"wait_for_conch=true to join the queue: conch_mode=wait "
                        f"blocks until your turn, conch_mode=callback returns "
                        f"immediately with your position and delivers your turn "
                        f"when granted. Or just try again later."
                    )

                # Gate open: become a first-class queue participant (visible in
                # `voicemode conch status`) instead of blind-polling. A session
                # id is required to be a tracked waiter — the queue and grant
                # hint key on it — so fall back to a per-process id when the
                # harness didn't supply one, pinning it on the conch so the grant
                # machinery (grant-aware acquire + deregister-on-acquired) stays
                # coherent through the wait.
                if conch.session_id is None:
                    conch.session_id = f"converse-{os.getpid()}"
                queue_session_id = conch.session_id
                try:
                    position = ConchQueue.register(
                        queue_session_id,
                        agent="converse",
                        project_path=resolved_project_path,
                        voice=resolved_voice,
                        mode=resolved_conch_mode,
                        pid=os.getpid(),
                    )
                except Exception as e:
                    # The queue must never break the critical-path lock. If
                    # registration fails, fall back to legacy poll-and-block.
                    logger.warning(f"Conch queue register failed ({e}); polling without a queue entry")
                    position = None

                if resolved_conch_mode == "callback":
                    # Do NOT block. Return immediately with the position and stay
                    # registered, so the turn can be delivered out-of-band when
                    # granted: on a holder's release, grant_next pings a skipped
                    # callback waiter via conch_notify.notify_granted (a session
                    # nudge). Make crystal clear the message was not spoken and
                    # how the turn resumes.
                    if event_logger:
                        event_logger.log_event("CONCH_CALLBACK_REGISTERED", {
                            "pid": os.getpid(),
                            "session_id": queue_session_id,
                            "position": position,
                            "holder_agent": holder_agent,
                        })
                    where = f"position #{position}" if position else "the queue"
                    return (
                        f"Queued for a callback at {where} — your message was NOT "
                        f"spoken ({holder_agent} holds the voice channel). Your turn "
                        f"will be actively delivered when the conch is granted to "
                        f"you: a session nudge prompts you to call converse() and "
                        f"take the floor (requires a session id). `voicemode conch "
                        f"status` shows your place in line any time as a "
                        f"supplementary view."
                    )

                # WAIT mode — block until granted, bounded by the timeout. Now
                # that we are registered, try_acquire() is grant-aware: only the
                # granted head acquires when the floor frees (FIFO; no steal),
                # and it consumes the grant + deregisters us on success. It also
                # fast-fails a dead holder and waits through a live hold.
                if event_logger:
                    event_logger.log_event("CONCH_WAIT_START", {
                        "pid": os.getpid(),
                        "holder_agent": holder_agent,
                        "timeout": conch_wait_timeout,
                        "position": position,
                    })

                waited = 0.0
                while not conch.try_acquire() and waited < conch_wait_timeout:
                    await asyncio.sleep(CONCH_CHECK_INTERVAL)
                    waited += CONCH_CHECK_INTERVAL

                if event_logger:
                    event_logger.log_event("CONCH_WAIT_END", {
                        "pid": os.getpid(),
                        "waited_seconds": waited,
                        "result": "acquired" if conch._acquired else "timeout"
                    })

                if not conch._acquired:
                    # Timed out — deregister cleanly so we leave no wedged entry
                    # in the queue (a stale head would block promotion of others).
                    try:
                        ConchQueue.deregister(queue_session_id)
                    except Exception:
                        pass
                    return (
                        f"Timed out waiting for conch ({conch_wait_timeout:.0f}s). "
                        f"{holder_agent} is still speaking. You can request a "
                        f"callback instead with conch_mode=callback."
                    )

            # Successfully acquired
            if event_logger:
                event_logger.log_event("CONCH_ACQUIRE", {
                    "pid": os.getpid(),
                    "agent": "converse"
                })

            # Auto-focus tmux pane after conch acquisition, before audio playback
            if AUTO_FOCUS_PANE and is_tmux():
                focus_tmux_pane()
        elif CONCH_ENABLED and skip_conch:
            # Conch is enabled but the caller asked to bypass it.
            if event_logger:
                holder = Conch.get_holder()
                event_logger.log_event("CONCH_SKIPPED", {
                    "pid": os.getpid(),
                    "agent": "converse",
                    "holder_pid": holder.get('pid') if holder else None,
                    "holder_agent": holder.get('agent') if holder else None,
                })
            # Still auto-focus tmux pane -- pane focus is unrelated to the conch.
            if AUTO_FOCUS_PANE and is_tmux():
                focus_tmux_pane()

        # Local microphone approach with timing
        transport = "local"
        timings = {}
        try:
            # VM-1676: bring the control channel up around the audio op. The
            # listener + reset live inside audio_operation_lock so start/stop are
            # serialized with all other audio ops; ``control_state`` is the shared
            # singleton the streaming loops + record loop poll for pause/stop.
            async with audio_operation_lock, _control_listener_scope() as control_state:
                # VM-1772: multi-utterance turns[] pipeline (speak-only, P1).
                # The conch is already held for the whole call (acquired above,
                # released in the finally), so the sequence plays in order under
                # a single hold — no per-turn conch race. Synth N+1 overlaps
                # playback of N. Speak-only: no reply collection in this slice,
                # so we return the multi-turn summary without entering the
                # record/listen path (regardless of wait_for_response).
                if normalized_turns is not None:
                    with DJDucker():
                        turn_results = await _speak_turns_pipeline(
                            normalized_turns,
                            tts_model=tts_model,
                            tts_provider=tts_provider,
                            audio_format=audio_format,
                            resolved_ref_text=resolved_ref_text,
                            should_skip_tts=should_skip_tts,
                        )
                    result, success = _format_turns_result(turn_results, effective_metrics_level)

                    n_ok = sum(1 for r in turn_results if r["success"])
                    timing_str = ", ".join(
                        f"turn{r['index'] + 1} gen {r['generation']:.1f}s play {r['playback']:.1f}s"
                        for r in turn_results
                    )
                    track_voice_interaction(
                        message=f"[turns x{len(turn_results)}] "
                                + " | ".join(t["say"][:40] for t in normalized_turns),
                        response="[speak-only]",
                        timing_str=timing_str,
                        transport="speak-only",
                        voice_provider=tts_provider,
                        voice_name=voice,
                        model=tts_model,
                        success=success,
                        error_message=None if success else f"{len(turn_results) - n_ok} turn(s) failed",
                    )
                    logger.info(f"Turns result: {result}")
                    return result

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
                    # Duck DJ volume during TTS playback
                    with DJDucker():
                        tts_success, tts_metrics, tts_config = await text_to_speech_with_failover(
                            message=message,
                            voice=voice,
                            model=tts_model,
                            instructions=tts_instructions,
                            audio_format=audio_format,
                            initial_provider=tts_provider,
                            speed=speed,
                            ref_text=resolved_ref_text
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

                # VM-1739: skip_forward is a transport barge-in, NOT a stop. The
                # playback polls already aborted the utterance (same instant-cut
                # as stop); here we consume the transport edge -- reset the state
                # back to running -- and fall through to the normal post-TTS path:
                # the record/listen turn when wait_for_response, else the ordinary
                # speak-only result. No [control: stop] marker; this advances the
                # turn. Checked BEFORE is_stopped (they're mutually exclusive
                # states); a racing stop would have dominated the latch upstream.
                control_snapshot = control_state.snapshot()
                if control_snapshot.is_skip_forward:
                    logger.info("Converse skip-forward via control channel during TTS")
                    control_state.reset()
                # VM-1676: a control-channel stop during TTS playback ends the
                # turn cleanly. Return NORMALLY with a control marker -- explicitly
                # NOT the asyncio.CancelledError / ESC path, so there is no MCP
                # teardown and no `/mcp` reconnect. Covers speak-only too (checked
                # before the wait_for_response branch).
                elif control_snapshot.is_stopped:
                    logger.info("Converse stopped via control channel during TTS")
                    success = True
                    return _build_control_stop_result(control_snapshot, timings)

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

                # VM-1685: CD-style skip-back replay + listen loop. Any pending
                # skip_back (from a mid-TTS drain-to-buffer, a "pause then
                # skip_back", or a press while listening) is drained first by
                # re-playing cached audio, then we listen. Because the in-flight
                # utterance was drained into the buffer in full (impl-drain-restart),
                # the first press restarts the CURRENT utterance from its start. A
                # press *during* recording loops us back to replay again. The cursor
                # persists across the whole turn so successive presses step further
                # back through the history buffer.
                replay_cursor = 0
                while True:
                    # Replay any queued skip_back(s) before listening.
                    replay_cursor = await _drain_skip_back(control_state, replay_cursor)

                    control_snapshot = control_state.snapshot()
                    # VM-1763: a skip_forward pressed during/around the replay is a
                    # transport barge-in. play_cached_utterance already cut the replay
                    # audio (is_skip_forward aborts playback like a stop), but the
                    # sticky STATE_SKIP_FORWARD is still latched -- _drain_skip_back only
                    # consumes the one-shot skip_back pending_transport, never this state.
                    # Consume the edge HERE (reset, mirroring the playback consume at
                    # ~2066) and advance to the record/listen turn, instead of carrying
                    # the latched state into recording -- where it would otherwise defer
                    # the turn-advance to the post-record consume at ~2197 and batch with
                    # the next press (the "first press dropped, second works" symptom).
                    # Checked BEFORE is_stopped: the two are mutually exclusive states,
                    # and a racing stop dominates the latch upstream (request_stop
                    # overrides skip_forward), so a stop already reads is_stopped here.
                    if control_snapshot.is_skip_forward:
                        logger.info("Converse skip-forward via control channel during skip-back replay")
                        control_state.reset()
                    # A stop (possibly during a replay) ends the turn cleanly.
                    elif control_snapshot.is_stopped:
                        logger.info("Converse stopped via control channel during skip-back replay")
                        success = True
                        return _build_control_stop_result(control_snapshot, timings)

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

                    listen_duration_max = _clamp_listen(listen_duration_max)
                    effective_release = _resolve_silence_release(silence_release_sec, disable_silence_detection)
                    record_start = time.perf_counter()
                    logger.debug(f"About to call record_audio_with_silence_detection with duration={listen_duration_max}, effective_release={effective_release}, min_duration={listen_duration_min}, vad_aggressiveness={vad_aggressiveness}")
                    audio_data, speech_detected, silence_prof = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio_with_silence_detection, listen_duration_max, effective_release, listen_duration_min, vad_aggressiveness
                    )
                    timings['record'] = time.perf_counter() - record_start

                    # Log recording end
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_END, {
                            "duration": timings['record'],
                            "samples": len(audio_data)
                        })

                    # VM-1676: a control-channel stop that arrived while we were
                    # listening also ends the turn cleanly -- skip STT and return the
                    # control marker normally (again, NOT the ESC/CancelledError path).
                    control_snapshot = control_state.snapshot()
                    if control_snapshot.is_stopped:
                        logger.info("Converse stopped via control channel during recording")
                        success = True
                        return _build_control_stop_result(control_snapshot, timings)

                    # VM-1754: a skip_forward pressed while listening is the manual
                    # "I'm done, go now" end-of-turn (and the VAD fallback when
                    # silence detection isn't firing). Consume the sticky-state edge
                    # (reset, mirroring the playback consume above) and fall through
                    # to the normal STT + return path: transcribe whatever was
                    # captured and return it as the user's response. Distinct from
                    # both siblings -- NOT a [control: stop] marker (stop) and NOT a
                    # replay (skip_back). Checked before skip_back: skip_forward is a
                    # sticky terminal STATE (softer than stop, but harder than the
                    # one-shot skip_back transport), so a decisive "advance" wins
                    # over a "replay" if both happened to be pressed. The
                    # skip_forward_ended flag tells the empty-buffer guard below that
                    # an empty capture here is intentional ("go now"), not an error.
                    skip_forward_ended = False
                    if control_snapshot.is_skip_forward:
                        logger.info("skip_forward received during recording -- ending turn, transcribing captured audio")
                        control_state.reset()
                        skip_forward_ended = True
                    # VM-1685: a skip_back pressed while listening -> replay the
                    # cached audio, then listen again. Otherwise this recording is
                    # the user's real response; proceed to STT.
                    elif control_state.pending_transport == COMMAND_SKIP_BACK:
                        logger.info("skip_back received during recording -- replaying then re-listening")
                        continue
                    break

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
                    # VM-1754: under skip_forward an empty buffer is intentional --
                    # the user pressed "go now" before any audio was captured (the
                    # VAD-fallback edge). Don't surface it as a recording error;
                    # fall through to the graceful no-speech path so the turn simply
                    # advances (returns "No speech detected", success=True).
                    if not skip_forward_ended:
                        result = "Error: Could not record audio"
                        return result
                    logger.info("skip_forward ended recording before any audio was captured -- advancing with no speech")
                    speech_detected = False
                
                # Track STT-specific metrics (defined here to be in scope for event logging later)
                stt_metrics = None

                # Check if no speech was detected
                if not speech_detected:
                    logger.info("No speech detected during recording - skipping STT processing")
                    response_text = None
                    stt_words = None
                    timings['stt'] = 0.0

                    # Still save the audio if configured (skip an empty buffer --
                    # e.g. a skip_forward fired before any audio was captured).
                    if SAVE_AUDIO and AUDIO_DIR and len(audio_data) > 0:
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
                    want_words = _want_words_for_turn(silence_prof, effective_measure_blocks, SIGNIFICANCE_THRESHOLD_SEC)
                    stt_result = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None, transport, word_timestamps=want_words)
                    stt_words = stt_result.get("words") if isinstance(stt_result, dict) else None
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
                                with DJDucker():
                                    tts_success, new_tts_metrics, _ = await text_to_speech_with_failover(
                                        message=message,
                                        voice=voice,
                                        model=tts_model,
                                        instructions=tts_instructions,
                                        audio_format=audio_format,
                                        initial_provider=tts_provider,
                                        speed=speed,
                                        ref_text=resolved_ref_text
                                    )
                                if not tts_success:
                                    logger.error("Failed to replay audio via TTS regeneration")
                        else:
                            # No cached audio, regenerate TTS
                            logger.info("No cached audio available, regenerating...")
                            with DJDucker():
                                tts_success, new_tts_metrics, _ = await text_to_speech_with_failover(
                                    message=message,
                                    voice=voice,
                                    model=tts_model,
                                    instructions=tts_instructions,
                                    audio_format=audio_format,
                                    initial_provider=tts_provider,
                                    speed=speed,
                                    ref_text=resolved_ref_text
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
                        audio_data, speech_detected, silence_prof = await asyncio.get_event_loop().run_in_executor(
                            None, record_audio_with_silence_detection, listen_duration_max, effective_release, listen_duration_min, vad_aggressiveness
                        )
                        stt_words = None  # reset: re-listen doesn't request word timestamps
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
                        audio_data, speech_detected, silence_prof = await asyncio.get_event_loop().run_in_executor(
                            None, record_audio_with_silence_detection, listen_duration_max, effective_release, listen_duration_min, vad_aggressiveness
                        )
                        stt_words = None  # reset: re-listen doesn't request word timestamps
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
                result = _assemble_voice_result(
                    response_text, stt_info, timing_str, effective_metrics_level,
                    silence_prof, stt_words, SIGNIFICANCE_THRESHOLD_SEC,
                    measure_blocks=effective_measure_blocks)
                if effective_metrics_level == "verbose":
                    # Append additional verbose-only STT detail fields
                    extra_verbose_parts = []
                    if 'stt_request_ms' in timings:
                        extra_verbose_parts.append(f"STT request: {timings['stt_request_ms']:.0f}ms")
                    if 'stt_file_size_bytes' in timings:
                        extra_verbose_parts.append(f"STT file: {timings['stt_file_size_bytes']/1024:.0f}KB")
                    if 'stt_is_local' in timings:
                        extra_verbose_parts.append(f"STT local: {timings['stt_is_local']}")
                    if extra_verbose_parts:
                        result = result + " | " + " | ".join(extra_verbose_parts)
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
        
    except asyncio.CancelledError:
        # Tool call was cancelled by the MCP client (e.g. user pressed ESC).
        #
        # We intentionally DO NOT re-raise. Under FastMCP 2.x stdio transport,
        # an uncaught CancelledError escaping the tool handler tears down the
        # MCP server process, leaving the client with a failed connection that
        # requires `/mcp` reconnect. That surfaces to the user as VoiceMode
        # "disappearing" after every ESC (see VM-1026 / GH issue #337).
        #
        # Swallowing cancellation here is safe because this function is a leaf
        # coroutine invoked by FastMCP -- there is no outer task that needs to
        # observe the cancellation signal. The `finally` block below still
        # releases the conch, logs TOOL_REQUEST_END, and updates timing state,
        # so cleanup invariants hold.
        logger.info("Converse cancelled by client (ESC or tool-call cancel)")
        if event_logger:
            event_logger.log_event("TOOL_CANCELLED", {
                "tool_name": "converse",
                "reason": "client_cancel",
            })
        result = "Cancelled by user."
        success = False
        return result

    except Exception as e:
        logger.error(f"Unexpected error in converse: {e}")
        if DEBUG:
            logger.error(f"Full traceback: {traceback.format_exc()}")
        result = f"Unexpected error: {str(e)}"
        return result

    finally:
        # Release the conch to signal voice conversation has ended. With
        # hold_conch=true, keep the floor between turns (re-stamped hold,
        # flock dropped, file left) instead of a full release.
        if CONCH_ENABLED and conch._acquired:
            held_seconds = conch.release(hold=hold_conch)
            if event_logger:
                event_logger.log_event("CONCH_RELEASE", {
                    "pid": os.getpid(),
                    "held_seconds": held_seconds,
                    "hold_active": bool(hold_conch)
                })
        else:
            # Don't call release() when not acquired — it would delete the lock
            # file belonging to the agent that IS holding the conch, defeating
            # the flock coordination (they'd end up locking different inodes).
            pass

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


@mcp.tool()
async def pause_conversation(
    seconds: float,
    message: Optional[str] = None,
) -> str:
    """Pause the conversation for a duration while KEEPING the floor (conch hold).

    Use when you want to step away from the mic to do background work and then
    resume speaking without another agent slipping in. Queued agents
    (wait_for_conch) keep waiting for the duration; your turn is preserved.

    The hold is re-stamped throughout the pause so it never idle-expires, and is
    left in place when the pause ends — you reclaim it on your next converse
    call. If you never return, the idle-expiry safety valve clears it.

    Args:
        seconds: How long to pause, in seconds.
        message: Optional note shown in the tool-call display while pausing.
                 Tip: pre-compute the resume time, e.g. "Resuming at 22:09:45".

    Returns:
        A message indicating the pause completed and the floor is still held.
    """
    end_str = datetime.fromtimestamp(time.time() + seconds).strftime("%H:%M:%S")

    if not CONCH_ENABLED:
        logger.info(f"pause_conversation: conch disabled; sleeping {seconds:.0f}s")
        await asyncio.sleep(max(0.0, seconds))
        return f"Pause complete (conch disabled). Resumed at {end_str}."

    # Refuse to pause if another LIVE agent currently holds the floor — we must
    # not clobber its payload (write_hold takes no flock).
    holder = Conch.get_holder()
    if holder:
        holder_pid = holder.get("pid")
        if holder_pid not in (None, os.getpid()):
            try:
                os.kill(holder_pid, 0)
                return (f"Cannot pause: {holder.get('agent', 'another agent')} "
                        f"(pid {holder_pid}) currently holds the conch.")
            except (ProcessLookupError, PermissionError, TypeError, OSError):
                pass  # holder dead/unknown — safe to take the floor

    resolved_session_id = (
        os.environ.get("VOICEMODE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
    )
    try:
        project_path = os.getcwd()
    except OSError:
        project_path = None
    # Preserve the voice already recorded by our own prior converse hold (if
    # any) so a pause doesn't blank it out.
    holder_voice = holder.get("voice") if holder else None

    logger.info(
        f"pause_conversation: holding for {seconds:.0f}s, resuming at {end_str}"
        + (f" — {message}" if message else "")
    )

    # Re-stamp well within the hold TTL so a maintained pause never lapses.
    # The TTL is now short (~10s, VM-1649), so the old fixed 10s interval would
    # leave no headroom; re-stamp at most every half-TTL (min 1s). When idle-
    # expiry is disabled (ttl <= 0) the hold never lapses, so the original 10s
    # cadence is fine.
    hold_ttl = _get_hold_expiry()
    interval = max(1.0, min(10.0, hold_ttl / 2)) if hold_ttl > 0 else 10.0
    elapsed = 0.0
    while elapsed < seconds:
        # Re-stamp the hold each chunk so a long pause never idle-expires.
        Conch.write_hold(
            "pause_conversation",
            session_id=resolved_session_id,
            project_path=project_path,
            voice=holder_voice,
            hold_timeout=hold_ttl if hold_ttl > 0 else None,
        )
        chunk = min(interval, seconds - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk

    return (
        f"Pause complete. Resumed at {end_str} (after {seconds:.0f}s). "
        "Floor still held — speak to continue, or it will idle-expire."
    )




