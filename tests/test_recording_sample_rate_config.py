#!/usr/bin/env python
"""
Test that microphone recording rate is decoupled from TTS playback rate.

See https://github.com/mbailey/voicemode/issues/491 -- SAMPLE_RATE (24000, tuned for
TTS/playback) was also used as the *microphone capture* rate everywhere, with no way to
override it independently. On hardware whose native rate differs (e.g. many USB mics are
44.1kHz/48kHz-native, never 24kHz), some audio backends resample transparently and some do
not, producing corrupted/aliased recordings. RECORDING_SAMPLE_RATE defaults to SAMPLE_RATE
(no behavior change) but can be overridden independently via VOICEMODE_RECORDING_SAMPLE_RATE.
"""

import importlib


class TestRecordingSampleRateConfig:
    def test_recording_sample_rate_defaults_to_sample_rate(self):
        """With no override, RECORDING_SAMPLE_RATE must equal SAMPLE_RATE -- zero behavior change."""
        import voice_mode.config as config
        importlib.reload(config)

        assert config.RECORDING_SAMPLE_RATE == config.SAMPLE_RATE
        assert config.SAMPLE_RATE == 24000

    def test_recording_sample_rate_override_is_decoupled_from_tts_rate(self, monkeypatch):
        """Overriding VOICEMODE_RECORDING_SAMPLE_RATE must NOT change the TTS SAMPLE_RATE."""
        monkeypatch.setenv("VOICEMODE_RECORDING_SAMPLE_RATE", "48000")

        import voice_mode.config as config
        importlib.reload(config)

        try:
            assert config.RECORDING_SAMPLE_RATE == 48000
            assert config.SAMPLE_RATE == 24000, "TTS sample rate must be unaffected by the override"
        finally:
            monkeypatch.delenv("VOICEMODE_RECORDING_SAMPLE_RATE", raising=False)
            importlib.reload(config)

    def test_module_reload_restores_default_after_override_cleared(self):
        """Sanity check on the reload-based test pattern itself: after clearing the env var and
        reloading again, we're back to the unchanged-default state (no test pollution)."""
        import voice_mode.config as config
        importlib.reload(config)
        assert config.RECORDING_SAMPLE_RATE == config.SAMPLE_RATE
