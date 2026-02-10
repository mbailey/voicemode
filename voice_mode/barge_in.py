"""Barge-in detection module for interrupting TTS playback.

This module provides the BargeInMonitor class which monitors the microphone
for voice activity during TTS playback. When speech is detected, it signals
to interrupt playback and captures the initial speech buffer for seamless
handoff to STT.

The barge-in feature allows users to interrupt Claude mid-response for more
natural, human-like turn-taking in conversations.
"""

import logging
import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

# Optional webrtcvad for voice activity detection
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    VAD_AVAILABLE = False

from voice_mode.config import (
    SAMPLE_RATE,
    CHANNELS,
    VAD_CHUNK_DURATION_MS,
    BARGE_IN_VAD_AGGRESSIVENESS,
    BARGE_IN_MIN_SPEECH_MS,
)

logger = logging.getLogger("voicemode.barge_in")


class BargeInMonitor:
    """Monitor microphone for voice activity during TTS playback.

    This class runs a background thread that listens to the microphone and
    uses WebRTC VAD to detect when the user starts speaking. When speech is
    detected (after the minimum duration threshold), it signals that TTS
    should be interrupted and captures the audio buffer for handoff to STT.

    Attributes:
        vad_aggressiveness: WebRTC VAD aggressiveness level (0-3).
            0 = most permissive (may trigger on background noise)
            3 = most aggressive (only triggers on clear speech)
        min_speech_ms: Minimum speech duration in milliseconds before
            triggering barge-in. Helps prevent false positives.

    Example:
        monitor = BargeInMonitor()

        def on_interrupt():
            player.stop()
            print("Barge-in detected!")

        monitor.start_monitoring(on_voice_detected=on_interrupt)
        # ... TTS playback happens ...
        monitor.stop_monitoring()

        captured = monitor.get_captured_audio()
        if captured is not None:
            # Pass to STT for transcription
            transcribe(captured)
    """

    def __init__(
        self,
        vad_aggressiveness: Optional[int] = None,
        min_speech_ms: Optional[int] = None
    ):
        """Initialize the barge-in monitor.

        Args:
            vad_aggressiveness: VAD aggressiveness level (0-3).
                If None, uses BARGE_IN_VAD_AGGRESSIVENESS from config.
            min_speech_ms: Minimum speech duration in milliseconds.
                If None, uses BARGE_IN_MIN_SPEECH_MS from config.
        """
        self.vad_aggressiveness = (
            vad_aggressiveness if vad_aggressiveness is not None
            else BARGE_IN_VAD_AGGRESSIVENESS
        )
        self.min_speech_ms = (
            min_speech_ms if min_speech_ms is not None
            else BARGE_IN_MIN_SPEECH_MS
        )

        # Threading state
        self._stop_event = threading.Event()
        self._voice_detected_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[], None]] = None
        self._callback_fired = False

        # Audio capture state
        self._audio_buffer: list = []
        self._buffer_lock = threading.Lock()

        # VAD state
        self._vad = None
        self._speech_ms_accumulated = 0

        logger.debug(
            f"BargeInMonitor initialized: vad_aggressiveness={self.vad_aggressiveness}, "
            f"min_speech_ms={self.min_speech_ms}"
        )

    def start_monitoring(self, on_voice_detected: Optional[Callable[[], None]] = None):
        """Start background monitoring thread.

        Begins listening to the microphone and checking for voice activity.
        When speech is detected (after min_speech_ms threshold), the
        on_voice_detected callback is invoked.

        Args:
            on_voice_detected: Callback to invoke when voice is detected.
                This should typically stop TTS playback.

        Raises:
            RuntimeError: If monitoring is already active.
            ImportError: If webrtcvad is not available.
        """
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Monitoring is already active")

        if not VAD_AVAILABLE:
            raise ImportError(
                "webrtcvad is required for barge-in detection. "
                "Install with: pip install webrtcvad"
            )

        # Reset state
        self._stop_event.clear()
        self._voice_detected_event.clear()
        self._callback = on_voice_detected
        self._callback_fired = False
        self._speech_ms_accumulated = 0

        with self._buffer_lock:
            self._audio_buffer.clear()

        # Initialize VAD
        self._vad = webrtcvad.Vad(self.vad_aggressiveness)

        logger.info(
            f"Starting barge-in monitoring (VAD={self.vad_aggressiveness}, "
            f"min_speech={self.min_speech_ms}ms)"
        )

        # Start monitoring thread
        self._thread = threading.Thread(
            target=self._monitoring_loop,
            name="BargeInMonitor",
            daemon=True
        )
        self._thread.start()

    def stop_monitoring(self):
        """Stop monitoring and clean up resources.

        This method is safe to call multiple times or even if monitoring
        was never started.
        """
        if self._thread is None:
            return

        logger.debug("Stopping barge-in monitoring")
        self._stop_event.set()

        # Wait for thread to finish (with timeout)
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                logger.warning("Monitoring thread did not stop cleanly")

        self._thread = None
        self._vad = None

        logger.info(
            f"Barge-in monitoring stopped. Voice detected: "
            f"{self._voice_detected_event.is_set()}"
        )

    def get_captured_audio(self) -> Optional[np.ndarray]:
        """Return audio captured from voice onset.

        Returns the audio buffer that was captured from the point when
        speech was first detected. This can be prepended to subsequent
        recording to avoid losing the initial speech.

        Returns:
            Numpy array of captured audio samples, or None if no speech
            was detected or no audio was captured.
        """
        with self._buffer_lock:
            if not self._audio_buffer:
                return None

            captured = np.concatenate(self._audio_buffer)
            logger.debug(f"Returning captured audio: {len(captured)} samples")
            return captured

    def voice_detected(self) -> bool:
        """Check if voice has been detected.

        Returns:
            True if voice activity triggered barge-in, False otherwise.
        """
        return self._voice_detected_event.is_set()

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active.

        Returns:
            True if the monitoring thread is running, False otherwise.
        """
        return self._thread is not None and self._thread.is_alive()

    def _monitoring_loop(self):
        """Background thread that monitors microphone for voice activity."""
        # Calculate chunk size for VAD
        # VAD requires 10, 20, or 30ms chunks at 8000, 16000, or 32000 Hz
        chunk_samples = int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)

        # WebRTC VAD only supports specific sample rates
        vad_sample_rate = 16000
        vad_chunk_samples = int(vad_sample_rate * VAD_CHUNK_DURATION_MS / 1000)

        # Audio queue for thread-safe communication
        audio_queue = queue.Queue()

        def audio_callback(indata, _frames, _time_info, status):
            """Callback for continuous audio stream."""
            if status:
                logger.warning(f"Barge-in audio callback status: {status}")
            audio_queue.put(indata.copy())

        try:
            # Create continuous input stream
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.int16,
                callback=audio_callback,
                blocksize=chunk_samples
            ):
                logger.debug("Barge-in audio stream started")

                while not self._stop_event.is_set():
                    try:
                        # Get audio chunk with timeout
                        chunk = audio_queue.get(timeout=0.1)
                        chunk_flat = chunk.flatten()

                        # Check for voice activity
                        is_speech = self._check_vad(chunk_flat, vad_sample_rate, vad_chunk_samples)

                        if is_speech:
                            # Accumulate speech duration
                            self._speech_ms_accumulated += VAD_CHUNK_DURATION_MS

                            # Capture audio from first speech detection
                            with self._buffer_lock:
                                self._audio_buffer.append(chunk_flat.copy())

                            # Check if we've exceeded the threshold
                            if (
                                self._speech_ms_accumulated >= self.min_speech_ms
                                and not self._callback_fired
                            ):
                                logger.info(
                                    f"Barge-in triggered after {self._speech_ms_accumulated}ms of speech"
                                )
                                self._voice_detected_event.set()
                                self._callback_fired = True

                                # Invoke callback
                                if self._callback:
                                    try:
                                        self._callback()
                                    except Exception as e:
                                        logger.error(f"Barge-in callback error: {e}")

                                # Continue capturing for a short while after trigger
                                # to get complete utterance start
                        else:
                            # Reset if we get silence (no partial speech counting)
                            # Only reset if we haven't triggered yet
                            if not self._callback_fired:
                                self._speech_ms_accumulated = 0
                                with self._buffer_lock:
                                    self._audio_buffer.clear()
                            else:
                                # After trigger, keep capturing
                                with self._buffer_lock:
                                    self._audio_buffer.append(chunk_flat.copy())

                    except queue.Empty:
                        # No audio data available, continue waiting
                        continue
                    except Exception as e:
                        logger.error(f"Error in barge-in monitoring loop: {e}")
                        break

        except Exception as e:
            logger.error(f"Failed to start barge-in audio stream: {e}")

        logger.debug("Barge-in monitoring loop ended")

    def _check_vad(
        self,
        chunk: np.ndarray,
        vad_sample_rate: int,
        vad_chunk_samples: int
    ) -> bool:
        """Check if audio chunk contains speech using VAD.

        Args:
            chunk: Audio samples at SAMPLE_RATE
            vad_sample_rate: Target sample rate for VAD (16000)
            vad_chunk_samples: Number of samples VAD expects

        Returns:
            True if speech is detected, False otherwise.
        """
        try:
            # Resample from SAMPLE_RATE to vad_sample_rate
            from scipy import signal
            resampled_length = int(len(chunk) * vad_sample_rate / SAMPLE_RATE)
            vad_chunk = signal.resample(chunk, resampled_length)

            # Take exactly the number of samples VAD expects
            vad_chunk = vad_chunk[:vad_chunk_samples].astype(np.int16)
            chunk_bytes = vad_chunk.tobytes()

            # Check for speech
            is_speech = self._vad.is_speech(chunk_bytes, vad_sample_rate)
            return is_speech

        except Exception as e:
            logger.warning(f"VAD error: {e}, treating as no speech")
            return False


def is_barge_in_available() -> bool:
    """Check if barge-in feature is available.

    Returns:
        True if webrtcvad is installed and barge-in can be used.
    """
    return VAD_AVAILABLE
