#!/usr/bin/env python
"""
Test that prepare_audio_for_stt() and record_audio() honor RECORDING_SAMPLE_RATE
(not the TTS SAMPLE_RATE) -- see tests/test_recording_sample_rate_config.py for
background on why this is decoupled (issue #491).
"""

import io
import wave
from unittest.mock import patch

import numpy as np
import pytest

from voice_mode.tools import converse as converse_module
from voice_mode.tools.converse import prepare_audio_for_stt, record_audio


class TestPrepareAudioForSttHonorsRecordingRate:
    def test_wav_export_uses_overridden_recording_rate_not_tts_rate(self, monkeypatch):
        """The WAV bytes prepare_audio_for_stt produces must reflect whatever rate the audio
        was ACTUALLY captured at (RECORDING_SAMPLE_RATE), not the unrelated TTS SAMPLE_RATE --
        a mismatch here silently pitch/speed-shifts the audio Whisper receives."""
        overridden_rate = 48000
        monkeypatch.setattr(converse_module, "RECORDING_SAMPLE_RATE", overridden_rate)

        one_second_of_silence = np.zeros(overridden_rate, dtype=np.int16)
        wav_bytes = prepare_audio_for_stt(one_second_of_silence, output_format="wav")

        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            # prepare_audio_for_stt downsamples to Whisper's native 16kHz regardless of
            # capture rate -- the exported file's rate should be 16000, and (critically)
            # the audio's actual DURATION should still be ~1 second. If the frame_rate used
            # to build the AudioSegment were wrong (e.g. still hardcoded to 24000 while the
            # real capture was 48000), the duration would come out wrong instead.
            assert wav_file.getframerate() == 16000
            duration_s = wav_file.getnframes() / wav_file.getframerate()
            assert duration_s == pytest.approx(1.0, abs=0.01)

    def test_wav_export_at_default_rate_matches_prior_behavior(self, monkeypatch):
        """With no override, behavior is unchanged from before this fix."""
        from voice_mode.config import SAMPLE_RATE
        monkeypatch.setattr(converse_module, "RECORDING_SAMPLE_RATE", SAMPLE_RATE)

        one_second_of_silence = np.zeros(SAMPLE_RATE, dtype=np.int16)
        wav_bytes = prepare_audio_for_stt(one_second_of_silence, output_format="wav")

        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            assert wav_file.getframerate() == 16000
            duration_s = wav_file.getnframes() / wav_file.getframerate()
            assert duration_s == pytest.approx(1.0, abs=0.01)


class TestRecordAudioUsesRecordingRate:
    def test_record_audio_requests_overridden_recording_rate_from_sounddevice(self, monkeypatch):
        """record_audio() must open the input device at RECORDING_SAMPLE_RATE, not SAMPLE_RATE."""
        overridden_rate = 48000
        monkeypatch.setattr(converse_module, "RECORDING_SAMPLE_RATE", overridden_rate)

        fake_recording = np.zeros((overridden_rate, 1), dtype=np.int16)
        with (
            patch.object(converse_module.sd, "rec", return_value=fake_recording) as mock_rec,
            patch.object(converse_module.sd, "wait"),
        ):
            record_audio(1.0)

        assert mock_rec.call_args.kwargs["samplerate"] == overridden_rate
        assert mock_rec.call_args.args[0] == overridden_rate  # samples_to_record == 1s worth


class TestVadResamplingMathAtOverriddenRates:
    """record_audio_with_silence_detection() resamples each 30ms capture chunk down to
    WebRTC VAD's fixed 16kHz frame size. WebRTC VAD requires an EXACT 10/20/30ms frame at
    8k/16k/32kHz -- if the resample math doesn't land on exactly 480 samples (30ms @ 16kHz)
    for a given RECORDING_SAMPLE_RATE, vad.is_speech() raises (caught non-fatally, but it
    silently disables silence detection for that call). This replicates the exact formula
    from converse.py's record_audio_with_silence_detection() to guard the invariant
    independently of the full threaded/queue-based recording path, which isn't practical
    to unit test directly.
    """

    @pytest.mark.parametrize("recording_rate", [8000, 16000, 24000, 32000, 44100, 48000])
    def test_resampled_chunk_matches_exact_vad_frame_size(self, recording_rate):
        from voice_mode.config import VAD_CHUNK_DURATION_MS

        vad_sample_rate = 16000
        vad_chunk_samples = int(vad_sample_rate * VAD_CHUNK_DURATION_MS / 1000)
        assert vad_chunk_samples == 480  # WebRTC VAD's fixed 30ms/16kHz frame size

        chunk_samples = int(recording_rate * VAD_CHUNK_DURATION_MS / 1000)
        resampled_length = int(chunk_samples * vad_sample_rate / recording_rate)

        assert resampled_length == vad_chunk_samples, (
            f"at RECORDING_SAMPLE_RATE={recording_rate}, resampled_length={resampled_length} "
            f"!= the exact {vad_chunk_samples}-sample VAD frame size WebRTC VAD requires"
        )
