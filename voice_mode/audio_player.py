"""Non-blocking audio player using callback-based playback.

This module provides a queue-based audio playback system that allows multiple
concurrent audio streams without blocking or interference.
"""

import logging
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger("voicemode.audio_player")


class NonBlockingAudioPlayer:
    """Non-blocking audio player using callback-based playback.

    This player uses a queue-based callback system to play audio without blocking
    the calling thread. It allows multiple instances to play audio concurrently
    by leveraging the system's audio mixing capabilities (Core Audio on macOS,
    PulseAudio/ALSA on Linux).

    Example:
        player = NonBlockingAudioPlayer()
        player.play(audio_samples, sample_rate=24000)
        player.wait()  # Wait for playback to complete
    """

    def __init__(self, buffer_size: int = 2048):
        """Initialize the audio player.

        Args:
            buffer_size: Size of audio buffer chunks for callback (default: 2048)
        """
        self.buffer_size = buffer_size
        self.audio_queue: Optional[queue.Queue] = None
        self.stream: Optional[sd.OutputStream] = None
        self.playback_complete = threading.Event()
        self.playback_error: Optional[Exception] = None

    def _audio_callback(self, outdata, frames, time_info, status):
        """Callback function called by sounddevice for each audio buffer.

        Args:
            outdata: Output buffer to fill with audio data
            frames: Number of frames requested
            time_info: Timing information
            status: Status flags
        """
        if status:
            logger.warning(f"Audio callback status: {status}")

        try:
            # Get audio chunk from queue
            chunk = self.audio_queue.get_nowait()

            # Handle end-of-stream marker
            if chunk is None:
                outdata[:] = 0
                self.playback_complete.set()
                raise sd.CallbackStop()

            # Fill output buffer
            chunk_len = len(chunk)
            if chunk_len < frames:
                # Partial chunk - pad with zeros
                if chunk.ndim == 1:
                    # Mono audio - reshape for sounddevice
                    outdata[:chunk_len, 0] = chunk
                    outdata[chunk_len:, 0] = 0
                else:
                    # Multi-channel audio
                    outdata[:chunk_len] = chunk
                    outdata[chunk_len:] = 0
                # Mark playback complete after this chunk
                self.playback_complete.set()
                raise sd.CallbackStop()
            else:
                if chunk.ndim == 1:
                    # Mono audio - reshape for sounddevice
                    outdata[:, 0] = chunk[:frames]
                else:
                    # Multi-channel audio
                    outdata[:] = chunk[:frames]

        except queue.Empty:
            # No data available - output silence
            outdata[:] = 0
            logger.debug("Audio queue empty - outputting silence")

    def play(self, samples: np.ndarray, sample_rate: int, blocking: bool = False):
        """Play audio samples using non-blocking callback system.

        Args:
            samples: Audio samples to play (numpy array)
            sample_rate: Sample rate in Hz
            blocking: If True, wait for playback to complete before returning

        Raises:
            Exception: If playback error occurs
        """
        # Reset state
        self.playback_complete.clear()
        self.playback_error = None

        # Ensure samples are float32
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32)

        # Determine number of channels
        if samples.ndim == 1:
            channels = 1
        else:
            channels = samples.shape[1]

        # Create queue and fill with audio chunks
        self.audio_queue = queue.Queue()

        # Split samples into chunks
        for i in range(0, len(samples), self.buffer_size):
            chunk = samples[i:i + self.buffer_size]
            self.audio_queue.put(chunk)

        # Add end-of-stream marker
        self.audio_queue.put(None)

        # Create and start output stream
        try:
            self.stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                callback=self._audio_callback,
                blocksize=self.buffer_size,
                dtype=np.float32
            )
            self.stream.start()

            if blocking:
                self.wait()

        except Exception as e:
            self.playback_error = e
            logger.error(f"Error starting audio playback: {e}")
            raise

    def wait(self, timeout: Optional[float] = None):
        """Wait for playback to complete.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Raises:
            Exception: If playback error occurred
        """
        # Wait for playback to complete
        if not self.playback_complete.wait(timeout=timeout):
            logger.warning("Playback wait timed out")

        # Stop and close stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Raise any error that occurred during playback
        if self.playback_error:
            raise self.playback_error

    def stop(self):
        """Stop playback immediately."""
        self.playback_complete.set()
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Clear queue
        if self.audio_queue:
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
