"""
Push-to-Talk (PTT) recording for VoiceMode.

Instead of keeping the microphone open continuously with VAD,
PTT lets the user press a key to start recording and press again to stop.

Configuration:
  VOICEMODE_PTT_MODE=toggle     (default: off)
      off    → disabled, use VAD as usual
      toggle → first keypress starts, second keypress stops
  VOICEMODE_PTT_KEY=F9          (default: F9)
      Any pynput-compatible key name: F1-F12, space, ctrl, alt, etc.

Requires: pynput  (pip install pynput)
"""

import logging
import os
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


def _resolve_pynput_key(key_name: str):
    """Convert a string key name to a pynput Key or KeyCode."""
    try:
        from pynput import keyboard as pk
    except ImportError:
        return None

    # Try special keys first (F1-F12, ctrl, alt, space, etc.)
    upper = key_name.upper()
    # Map common names
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

    # F-keys
    if upper.startswith("F") and upper[1:].isdigit():
        attr = "f" + upper[1:]
        key = getattr(pk.Key, attr, None)
        if key:
            return key

    # Named keys
    key = getattr(pk.Key, mapped, None)
    if key:
        return key

    # Single character
    if len(key_name) == 1:
        return pk.KeyCode.from_char(key_name)

    logger.warning(f"PTT: unknown key '{key_name}', falling back to F9")
    return pk.Key.f9


class PushToTalkRecorder:
    """
    Toggle-mode PTT recorder.

    Usage:
        recorder = PushToTalkRecorder()
        audio_data, speech_detected = recorder.record()
    """

    def __init__(self, sample_rate: int = 24000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stop_event = threading.Event()
        self._start_event = threading.Event()
        self._listener = None

    def _make_key_handler(self):
        """Returns an on_press handler that toggles recording state."""
        target_key = _resolve_pynput_key(PTT_KEY_NAME)
        recording = [False]  # mutable reference

        def on_press(key):
            if key == target_key:
                if not recording[0]:
                    # First press: start recording
                    recording[0] = True
                    self._start_event.set()
                else:
                    # Second press: stop recording
                    recording[0] = False
                    self._stop_event.set()
                    return False  # Stop listener

        return on_press

    def record(self, max_duration: float = 120.0) -> Tuple[np.ndarray, bool]:
        """
        Wait for the user to press PTT key (start), record audio, wait for
        second key press (stop), then return the audio data.

        Returns:
            (audio_data, speech_detected) — speech_detected is True if any
            audio was captured above silence threshold.
        """
        try:
            import sounddevice as sd
            from pynput import keyboard as pk
        except ImportError as exc:
            logger.error(f"PTT: missing dependency ({exc}), falling back to VAD")
            return np.array([]), False

        self._stop_event.clear()
        self._start_event.clear()

        target_key = _resolve_pynput_key(PTT_KEY_NAME)

        logger.info(f"🎤 PTT: press [{PTT_KEY_NAME}] to start recording...")

        # Phase 1: wait for first keypress to START
        recording_active = [False]

        def on_press_start(key):
            if key == target_key:
                recording_active[0] = True
                self._start_event.set()
                return False  # Stop this listener

        start_listener = pk.Listener(on_press=on_press_start)
        start_listener.start()
        self._start_event.wait()  # Blocks until key pressed
        start_listener.stop()

        logger.info(f"🔴 PTT: recording... press [{PTT_KEY_NAME}] again to stop")

        # Phase 2: record audio until second keypress or max_duration
        chunks = []
        stop_flag = threading.Event()

        def on_press_stop(key):
            if key == target_key:
                stop_flag.set()
                return False

        def audio_callback(indata, frames, _time, status):
            if status:
                logger.debug(f"PTT audio callback status: {status}")
            chunks.append(indata.copy())

        stop_listener = pk.Listener(on_press=on_press_stop)
        stop_listener.start()

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                callback=audio_callback,
                blocksize=int(self.sample_rate * 0.02),  # 20ms chunks
            ):
                deadline = time.time() + max_duration
                while not stop_flag.is_set() and time.time() < deadline:
                    time.sleep(0.05)
        finally:
            stop_listener.stop()

        logger.info("⏹ PTT: recording stopped")

        if not chunks:
            return np.array([], dtype=np.int16), False

        audio_data = np.concatenate(chunks).flatten()

        # Simple speech detection: RMS above threshold
        rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
        speech_detected = rms > 100  # Rough threshold for speech vs silence
        logger.info(f"PTT: captured {len(audio_data)} samples, RMS={rms:.1f}, speech={speech_detected}")

        return audio_data, speech_detected
