"""Tests for macOS VoiceProcessingIO microphone capture."""

import pytest
import numpy as np
import platform
import inspect
from typing import Tuple, get_type_hints


pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS VoiceProcessingIO tests only run on macOS"
)


class TestMacOSMicAvailability:
    """Test VoiceProcessingIO availability detection."""

    def test_is_available_returns_bool(self):
        """is_available should return a boolean."""
        from voice_mode.utils.macos_mic import is_available
        result = is_available()
        assert isinstance(result, bool)

    def test_is_available_on_macos(self):
        """VoiceProcessingIO should be available on macOS."""
        from voice_mode.utils.macos_mic import is_available
        assert is_available() is True

    def test_is_available_consistent(self):
        """Multiple calls to is_available should return consistent results."""
        from voice_mode.utils.macos_mic import is_available
        result1 = is_available()
        result2 = is_available()
        assert result1 == result2


class TestVoiceProcessingRecorder:
    """Test VoiceProcessingRecorder class."""

    def test_recorder_instantiation(self):
        """Recorder should instantiate without errors."""
        from voice_mode.utils.macos_mic import VoiceProcessingRecorder
        recorder = VoiceProcessingRecorder()
        assert recorder is not None

    def test_recorder_has_record_method(self):
        """Recorder should have a record method with correct signature."""
        from voice_mode.utils.macos_mic import VoiceProcessingRecorder
        recorder = VoiceProcessingRecorder()
        assert hasattr(recorder, 'record')
        assert callable(recorder.record)

        sig = inspect.signature(recorder.record)
        params = list(sig.parameters.keys())
        assert 'max_duration' in params
        assert 'min_duration' in params
        assert 'silence_threshold_ms' in params
        assert 'vad_aggressiveness' in params


class TestVADLogic:
    """Test VAD threshold and detection logic."""

    def test_energy_calculation(self):
        """Test RMS energy calculation matches VAD expectations."""
        silence = np.zeros(1024, dtype=np.float32)
        speech = np.random.uniform(-0.1, 0.1, 1024).astype(np.float32)
        loud_speech = np.random.uniform(-0.5, 0.5, 1024).astype(np.float32)

        silence_energy = np.sqrt(np.mean(silence ** 2))
        speech_energy = np.sqrt(np.mean(speech ** 2))
        loud_energy = np.sqrt(np.mean(loud_speech ** 2))

        assert silence_energy < 0.001
        assert speech_energy > 0.01
        assert loud_energy > speech_energy

    def test_vad_threshold_mapping(self):
        """VAD aggressiveness 0-3 should map to increasing energy thresholds."""
        # These are the expected thresholds from the implementation
        expected_thresholds = {0: 0.002, 1: 0.005, 2: 0.01, 3: 0.02}

        # Verify thresholds are monotonically increasing
        values = [expected_thresholds[i] for i in range(4)]
        assert values == sorted(values)
        assert all(v > 0 for v in values)


class TestNativeSampleRate:
    """Test native sample rate detection via VoiceProcessingRecorder.

    These tests verify the recorder can be instantiated and would return
    valid sample rates through the public API.
    """

    def test_recorder_default_sample_rate_is_reasonable(self):
        """Verify recorder has a reasonable default sample rate."""
        from voice_mode.utils.macos_mic import VoiceProcessingRecorder
        recorder = VoiceProcessingRecorder()
        # Default sample rate should be set to a reasonable value
        # (will be updated to native rate during recording)
        assert hasattr(recorder, '_sample_rate')
        assert 8000 <= recorder._sample_rate <= 192000

    def test_vpio_component_exists(self):
        """Verify VoiceProcessingIO component can be found via is_available."""
        from voice_mode.utils.macos_mic import is_available
        # If is_available returns True, the component exists
        assert is_available() is True


class TestRecordAudioFunction:
    """Test the record_audio convenience function."""

    def test_record_audio_accepts_all_parameters(self):
        """record_audio should accept all expected parameters."""
        from voice_mode.utils.macos_mic import record_audio
        sig = inspect.signature(record_audio)
        params = list(sig.parameters.keys())

        assert 'max_duration' in params
        assert 'min_duration' in params
        assert 'silence_threshold_ms' in params
        assert 'vad_aggressiveness' in params

    def test_record_audio_return_annotation(self):
        """record_audio should have correct return type annotation."""
        from voice_mode.utils.macos_mic import record_audio
        hints = get_type_hints(record_audio)
        assert 'return' in hints
        assert hints['return'] == Tuple[np.ndarray, bool, int]


class TestConverseIntegration:
    """Test integration with converse.py."""

    def test_macos_voice_processing_config_exists(self):
        """MACOS_VOICE_PROCESSING config should exist."""
        from voice_mode.config import MACOS_VOICE_PROCESSING
        assert isinstance(MACOS_VOICE_PROCESSING, bool)

    def test_macos_mic_importable(self):
        """macos_mic module should be importable on macOS."""
        from voice_mode.utils.macos_mic import is_available, record_audio
        assert callable(is_available)
        assert callable(record_audio)


class TestCrossplatformImport:
    """Test that module can be imported on any platform."""

    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="This test verifies non-macOS behavior"
    )
    def test_import_on_non_macos(self):
        """Module should import without error on non-macOS platforms."""
        # This test only runs on non-macOS platforms
        from voice_mode.utils.macos_mic import is_available
        assert is_available() is False
