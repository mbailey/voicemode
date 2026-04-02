"""
Push-to-Talk (PTT) recording for VoiceMode.

Hold the PTT key while speaking; release to send. If the key is pressed while
the assistant is speaking, playback is interrupted immediately and recording
starts right away.

Configuration:
  VOICEMODE_PTT_MODE=hold       (default: off)
      off  → disabled, use VAD as usual
      hold → hold key to record, release to send
  VOICEMODE_PTT_KEY=F9          (default: F9)
      Any pynput-compatible key name: F1-F12, space, ctrl, alt, etc.

Requires: pynput  (pip install pynput)
"""

import logging
import os
import platform
import threading
import time
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger("voicemode")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PTT_MODE = os.environ.get("VOICEMODE_PTT_MODE", "off").lower()
PTT_KEY_NAME = os.environ.get("VOICEMODE_PTT_KEY", "F9")

PTT_ENABLED = PTT_MODE != "off"

# ---------------------------------------------------------------------------
# Global key state
# ---------------------------------------------------------------------------

_key_held = threading.Event()    # Set while PTT key is physically held down
_key_pressed = threading.Event() # Pulses on each new press (used to wake waiting recorders)
_global_listener = None          # Single persistent pynput Listener


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

def _resolve_pynput_key(key_name: str):
    """Convert a string key name to a pynput Key or KeyCode."""
    try:
        from pynput import keyboard as pk
    except ImportError:
        return None

    upper = key_name.upper()
    aliases = {
        "SPACE": "space",
        "ENTER": "enter",
        "RETURN": "enter",
        "ESC": "esc",
        "ESCAPE": "esc",
        "TAB": "tab",
        "BACKSPACE": "backspace",
        "DELETE": "delete",
        "HOME": "home",
        "END": "end",
        "PAGEUP": "page_up",
        "PAGEDOWN": "page_down",
        "UP": "up",
        "DOWN": "down",
        "LEFT": "left",
        "RIGHT": "right",
    }
    mapped = aliases.get(upper, key_name.lower())

    if upper.startswith("F") and upper[1:].isdigit():
        attr = "f" + upper[1:]
        key = getattr(pk.Key, attr, None)
        if key:
            return key

    key = getattr(pk.Key, mapped, None)
    if key:
        return key

    if len(key_name) == 1:
        return pk.KeyCode.from_char(key_name)

    logger.warning(f"PTT: unknown key '{key_name}', falling back to F9")
    return pk.Key.f9


# ---------------------------------------------------------------------------
# Streaming TTS interruption
# ---------------------------------------------------------------------------

# Set by the PTT listener when the user presses the key during streaming TTS.
# Checked inside stream_pcm_audio / stream_with_buffering to abort the loop.
interrupt_streaming = threading.Event()

# Reference to the active sounddevice OutputStream during streaming TTS.
# Set by streaming.py so we can call stream.abort() immediately.
_active_sd_stream = None


def set_active_sd_stream(stream) -> None:
    """Called by streaming.py when a sounddevice stream starts."""
    global _active_sd_stream
    _active_sd_stream = stream
    interrupt_streaming.clear()


def clear_active_sd_stream() -> None:
    """Called by streaming.py when the stream ends normally."""
    global _active_sd_stream
    _active_sd_stream = None
    interrupt_streaming.clear()


# ---------------------------------------------------------------------------
# TTS interruption helper
# ---------------------------------------------------------------------------

def _stop_active_player():
    """Stop all active TTS playback (streaming and buffered)."""
    # 1. Interrupt streaming TTS (stream_pcm_audio / stream_with_buffering)
    interrupt_streaming.set()
    stream = _active_sd_stream
    if stream is not None:
        try:
            logger.info("PTT: aborting active sounddevice stream")
            stream.abort()
        except Exception as exc:
            logger.debug(f"PTT: could not abort sd stream: {exc}")

    # 2. Stop NonBlockingAudioPlayer (buffered path)
    try:
        import voice_mode.audio_player as _ap
        player = getattr(_ap, '_current_playback', None)
        if player is not None:
            logger.info("PTT: stopping active NonBlockingAudioPlayer")
            player.stop()
    except Exception as exc:
        logger.debug(f"PTT: could not stop buffered player: {exc}")


# ---------------------------------------------------------------------------
# Global listener lifecycle
# ---------------------------------------------------------------------------

def _start_global_listener():
    """Start the persistent background listener. Safe to call multiple times."""
    global _global_listener
    if _global_listener is not None and _global_listener.is_alive():
        return
    # Listener died or was never started — (re)create it
    _global_listener = None

    try:
        from pynput import keyboard as pk
    except ImportError:
        logger.warning("PTT: pynput not installed — key listener unavailable")
        return

    target_key = _resolve_pynput_key(PTT_KEY_NAME)

    def on_press(key):
        try:
            if key == target_key and not _key_held.is_set():
                # New press (guard against key-repeat events)
                _key_held.set()
                _key_pressed.set()
                _stop_active_player()
        except Exception as exc:
            logger.debug(f"PTT on_press error (ignored): {exc}")

    def on_release(key):
        try:
            if key == target_key:
                _key_held.clear()
        except Exception as exc:
            logger.debug(f"PTT on_release error (ignored): {exc}")

    _global_listener = pk.Listener(on_press=on_press, on_release=on_release)
    _global_listener.daemon = True
    _global_listener.start()
    logger.info(f"PTT: global listener started, key={PTT_KEY_NAME!r}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if PTT_ENABLED:
    if platform.system() == "Darwin":
        logger.warning(
            "PTT: on macOS, pynput requires Accessibility permissions to capture keys.\n"
            "  If PTT does not respond, go to:\n"
            "  System Settings > Privacy & Security > Accessibility\n"
            "  and add your terminal app (Terminal, iTerm2, WezTerm, etc.) to the list.\n"
            f"  Current PTT key: {PTT_KEY_NAME!r} — change with VOICEMODE_PTT_KEY env var."
        )
    _start_global_listener()


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------

class PushToTalkRecorder:
    """
    Hold-mode PTT recorder.

    Hold the PTT key to record; release to stop and send audio.
    If the key is already held (e.g., the user pressed it to interrupt TTS),
    recording starts immediately without waiting.

    Usage:
        recorder = PushToTalkRecorder()
        audio_data, speech_detected = recorder.record()
    """

    def __init__(self, sample_rate: int = 24000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels

    def record(self, max_duration: float = 120.0) -> Tuple[np.ndarray, bool]:
        """
        Wait for the PTT key to be held, record while held, stop on release.

        Returns:
            (audio_data, speech_detected)
        """
        try:
            import sounddevice as sd
        except ImportError as exc:
            logger.error(f"PTT: missing dependency ({exc}), falling back to VAD")
            return np.array([]), False

        # Restart listener if it died (e.g., unhandled exception in a callback)
        if _global_listener is None or not _global_listener.is_alive():
            logger.warning("PTT: listener not running, restarting...")
            _start_global_listener()

        # If key not already held, wait for user to press it
        if not _key_held.is_set():
            _key_pressed.clear()
            logger.info(f"🎤 PTT: hold [{PTT_KEY_NAME}] to speak...")
            # Wait up to 5 minutes for a key press
            if not _key_pressed.wait(timeout=300.0):
                logger.warning("PTT: timed out waiting for key press")
                return np.array([], dtype=np.int16), False
        else:
            logger.info("🔴 PTT: key already held — starting recording immediately")

        logger.info(f"🔴 PTT: recording... release [{PTT_KEY_NAME}] to send")

        chunks = []

        def audio_callback(indata, frames, _time, status):
            if status:
                logger.debug(f"PTT audio callback status: {status}")
            chunks.append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                callback=audio_callback,
                blocksize=int(self.sample_rate * 0.02),  # 20ms chunks
            ):
                deadline = time.time() + max_duration
                while _key_held.is_set() and time.time() < deadline:
                    time.sleep(0.02)
        except Exception as exc:
            logger.error(f"PTT: recording error: {exc}")

        logger.info("⏹ PTT: key released — sending")

        if not chunks:
            return np.array([], dtype=np.int16), False

        audio_data = np.concatenate(chunks).flatten()

        rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
        speech_detected = rms > 100
        logger.info(f"PTT: captured {len(audio_data)} samples, RMS={rms:.1f}, speech={speech_detected}")

        return audio_data, speech_detected
