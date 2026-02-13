"""Tests for DuplexBargeInPlayer barge-in detection logic.

Tests cover:
- Energy threshold detection with synthetic data
- Ring buffer size management (deque-based)
- Echo suppression logic
- Thread-safety of shared state
- skip_playback parameter propagation through streaming functions
"""

import sys
import threading
import time
from collections import deque
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Mock hardware-dependent modules before importing voice_mode modules
sys.modules['webrtcvad'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()
sys.modules['livekit'] = MagicMock()


class TestDuplexBargeInPlayerInit:
    """Test DuplexBargeInPlayer initialization and defaults."""

    def test_default_parameters(self):
        """Verify default parameter values match config constants."""
        from voice_mode.tools.converse import DuplexBargeInPlayer
        from voice_mode.config import (
            SAMPLE_RATE, CHANNELS,
            BARGE_IN_ENERGY_THRESHOLD, BARGE_IN_MIN_SPEECH_MS,
        )

        player = DuplexBargeInPlayer()

        assert player.sample_rate == SAMPLE_RATE
        assert player.channels == CHANNELS
        assert player.energy_threshold == BARGE_IN_ENERGY_THRESHOLD
        assert player.min_speech_ms == BARGE_IN_MIN_SPEECH_MS

    def test_custom_parameters(self):
        """Verify custom parameters are accepted."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(
            sample_rate=16000,
            channels=2,
            energy_threshold=500.0,
            min_speech_ms=50,
        )

        assert player.sample_rate == 16000
        assert player.channels == 2
        assert player.energy_threshold == 500.0
        assert player.min_speech_ms == 50

    def test_ring_buffer_is_deque(self):
        """Ring buffer must use collections.deque for O(1) popleft."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer()
        assert isinstance(player._ring_buffer, deque)

    def test_lock_exists(self):
        """Thread lock must be initialized for shared state protection."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer()
        assert isinstance(player._lock, type(threading.Lock()))


class TestEnergyThresholdDetection:
    """Test barge-in energy detection with synthetic audio data."""

    def _make_player(self, energy_threshold=300.0, min_speech_ms=0):
        """Create a player with controllable thresholds."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        return DuplexBargeInPlayer(
            sample_rate=24000,
            channels=1,
            energy_threshold=energy_threshold,
            min_speech_ms=min_speech_ms,
        )

    def _make_audio_chunk(self, amplitude: float, samples: int = 240) -> np.ndarray:
        """Create a float32 audio chunk with given amplitude (0.0 - 1.0)."""
        return np.full((samples, 1), amplitude, dtype=np.float32)

    def test_silence_does_not_trigger(self):
        """Silent input should not trigger barge-in."""
        player = self._make_player(energy_threshold=300.0, min_speech_ms=0)
        silence = self._make_audio_chunk(0.0)

        player._monitor_callback(silence, len(silence), None, None)

        assert not player._barge_in_detected

    def test_loud_input_triggers_barge_in(self):
        """Loud input exceeding threshold should trigger barge-in."""
        player = self._make_player(energy_threshold=100.0, min_speech_ms=0)
        # Amplitude of 0.5 -> energy = 0.5 * 32768 = 16384, well above 100
        loud = self._make_audio_chunk(0.5)

        player._monitor_callback(loud, len(loud), None, None)

        assert player._barge_in_detected

    def test_min_speech_duration_enforced(self):
        """Barge-in should only confirm after min_speech_ms is met."""
        player = self._make_player(energy_threshold=100.0, min_speech_ms=50)
        loud = self._make_audio_chunk(0.5)

        # First callback - starts timing but shouldn't confirm yet
        player._monitor_callback(loud, len(loud), None, None)
        assert not player._barge_in_detected
        assert player._speech_start_time is not None

        # Simulate enough time passing
        player._speech_start_time = time.time() - 0.1  # 100ms ago
        player._monitor_callback(loud, len(loud), None, None)

        assert player._barge_in_detected

    def test_speech_reset_on_silence(self):
        """Speech timer should reset when input drops below threshold."""
        player = self._make_player(energy_threshold=100.0, min_speech_ms=50)
        loud = self._make_audio_chunk(0.5)
        silence = self._make_audio_chunk(0.0)

        # Start speech detection
        player._monitor_callback(loud, len(loud), None, None)
        assert player._speech_start_time is not None

        # Silence resets
        player._monitor_callback(silence, len(silence), None, None)
        assert player._speech_start_time is None
        assert player._collected_audio == []


class TestRingBuffer:
    """Test ring buffer management."""

    def _make_player(self, ring_buffer_duration=0.5):
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(sample_rate=24000, min_speech_ms=999999)
        # Override ring buffer size for testing
        player.ring_buffer_size = int(ring_buffer_duration * 24000)
        return player

    def test_ring_buffer_accumulates(self):
        """Ring buffer should accumulate pre-trigger audio chunks."""
        player = self._make_player()
        silence = np.full((240, 1), 0.0001, dtype=np.float32)  # Very quiet

        for _ in range(5):
            player._monitor_callback(silence, 240, None, None)

        assert len(player._ring_buffer) == 5
        assert player._ring_buffer_samples == 240 * 5

    def test_ring_buffer_trims_to_size(self):
        """Ring buffer should not exceed configured size."""
        # Small ring buffer: 240 samples (10ms at 24kHz)
        player = self._make_player(ring_buffer_duration=0.01)
        silence = np.full((240, 1), 0.0001, dtype=np.float32)

        # Add many chunks
        for _ in range(20):
            player._monitor_callback(silence, 240, None, None)

        # Should be trimmed to approximately ring_buffer_size
        assert player._ring_buffer_samples <= player.ring_buffer_size + 240

    def test_ring_buffer_prepended_on_barge_in(self):
        """On barge-in confirmation, ring buffer contents should be prepended."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(
            sample_rate=24000, energy_threshold=100.0, min_speech_ms=0
        )
        silence = np.full((240, 1), 0.0001, dtype=np.float32)
        loud = np.full((240, 1), 0.5, dtype=np.float32)

        # Accumulate ring buffer with 3 silence chunks
        for _ in range(3):
            player._monitor_callback(silence, 240, None, None)

        ring_count_before = len(player._ring_buffer)
        assert ring_count_before == 3

        # Trigger barge-in with loud chunk
        # The loud chunk is first appended to ring buffer (now 4),
        # then appended to collected_audio (1), then on confirmation:
        # collected_audio = ring_buffer(4) + collected_audio(1) = 5
        player._monitor_callback(loud, 240, None, None)

        assert player._barge_in_detected
        # Ring buffer should be cleared after prepending
        assert len(player._ring_buffer) == 0
        # Collected audio = ring_buffer (3 silence + 1 loud) + collected (1 loud)
        assert len(player._collected_audio) == ring_count_before + 2


class TestEchoSuppression:
    """Test echo suppression logic."""

    def test_echo_suppression_raises_threshold(self):
        """Output energy should raise the effective threshold via echo margin."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(
            sample_rate=24000, energy_threshold=100.0, min_speech_ms=0
        )

        # Set high output energy (simulating loud TTS playback)
        player._set_output_energy(1000.0)

        # Input that exceeds base threshold but not echo-adjusted threshold
        # Echo threshold = max(100, 1000 * 1.3) = 1300
        # Input energy for amplitude 0.03 = 0.03 * 32768 ~ 983 < 1300
        medium = np.full((240, 1), 0.03, dtype=np.float32)
        player._monitor_callback(medium, 240, None, None)

        assert not player._barge_in_detected

    def test_loud_input_overrides_echo(self):
        """Very loud input should override echo suppression."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(
            sample_rate=24000, energy_threshold=100.0, min_speech_ms=0
        )

        player._set_output_energy(500.0)
        # Echo threshold = max(100, 500 * 1.3) = 650
        # Input energy for amplitude 0.5 = 0.5 * 32768 ~ 16384 >> 650
        loud = np.full((240, 1), 0.5, dtype=np.float32)
        player._monitor_callback(loud, 240, None, None)

        assert player._barge_in_detected


class TestThreadSafety:
    """Test thread-safe property access."""

    def test_barge_in_detected_property(self):
        """barge_in_detected property should provide thread-safe reads."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer()
        assert player.barge_in_detected is False

        with player._lock:
            player._barge_in_detected = True
        assert player.barge_in_detected is True

    def test_stop_monitoring_property(self):
        """stop_monitoring property should provide thread-safe reads/writes."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer()
        assert player.stop_monitoring is False

        player.stop_monitoring = True
        assert player.stop_monitoring is True

    def test_concurrent_callback_access(self):
        """Simulate concurrent access to verify no crashes under threading."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        player = DuplexBargeInPlayer(
            sample_rate=24000, energy_threshold=100.0, min_speech_ms=0
        )

        errors = []
        loud = np.full((240, 1), 0.5, dtype=np.float32)

        def callback_thread():
            try:
                for _ in range(50):
                    player._monitor_callback(loud, 240, None, None)
            except Exception as e:
                errors.append(e)

        def energy_thread():
            try:
                for i in range(50):
                    player._set_output_energy(float(i * 10))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=callback_thread)
        t2 = threading.Thread(target=energy_thread)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert errors == [], f"Thread errors: {errors}"


class TestSkipPlaybackPropagation:
    """Test that skip_playback parameter propagates through the streaming stack."""

    def test_stream_pcm_audio_accepts_skip_playback(self):
        """stream_pcm_audio function signature includes skip_playback."""
        import inspect
        from voice_mode.streaming import stream_pcm_audio

        sig = inspect.signature(stream_pcm_audio)
        assert "skip_playback" in sig.parameters

    def test_stream_tts_audio_accepts_skip_playback(self):
        """stream_tts_audio function signature includes skip_playback."""
        import inspect
        from voice_mode.streaming import stream_tts_audio

        sig = inspect.signature(stream_tts_audio)
        assert "skip_playback" in sig.parameters

    def test_stream_with_buffering_accepts_skip_playback(self):
        """stream_with_buffering function signature includes skip_playback."""
        import inspect
        from voice_mode.streaming import stream_with_buffering

        sig = inspect.signature(stream_with_buffering)
        assert "skip_playback" in sig.parameters

    def test_text_to_speech_accepts_skip_playback(self):
        """text_to_speech function signature includes skip_playback."""
        import inspect
        from voice_mode.core import text_to_speech

        sig = inspect.signature(text_to_speech)
        assert "skip_playback" in sig.parameters


class TestNamedConstants:
    """Verify named constants replace magic numbers."""

    def test_class_constants_defined(self):
        """DuplexBargeInPlayer should expose named constants."""
        from voice_mode.tools.converse import DuplexBargeInPlayer

        assert hasattr(DuplexBargeInPlayer, 'ECHO_MARGIN')
        assert hasattr(DuplexBargeInPlayer, 'MONITOR_CHUNK_MS')
        assert hasattr(DuplexBargeInPlayer, 'RING_BUFFER_DURATION')
        assert hasattr(DuplexBargeInPlayer, 'PLAYBACK_CHUNK_SIZE')
        assert hasattr(DuplexBargeInPlayer, 'POLL_INTERVAL')

    def test_echo_margin_value(self):
        """Echo margin should be 1.3 (30% louder than output)."""
        from voice_mode.tools.converse import DuplexBargeInPlayer
        assert DuplexBargeInPlayer.ECHO_MARGIN == 1.3

    def test_post_barge_in_duration_default(self):
        """play_with_monitoring default post_barge_in_duration should be 0.3."""
        import inspect
        from voice_mode.tools.converse import DuplexBargeInPlayer

        sig = inspect.signature(DuplexBargeInPlayer.play_with_monitoring)
        default = sig.parameters['post_barge_in_duration'].default
        assert default == 0.3
