import pytest
from voice_mode.tools.converse import _build_silence_profile


def test_build_profile_sets_boundaries():
    prof = _build_silence_profile(
        pre_speech_delay_s=0.7, total_silence_s=6.0, speech_active_s=6.9,
        gaps=[(6.0, 11.3)], first_speech_start=0.7, recording_end=12.9,
    )
    assert prof.first_speech_start == 0.7
    assert prof.recording_end == 12.9
    assert prof.blocks()[0] == ("gap", 0.0, 0.7)
    assert prof.longest_gap == pytest.approx(5.3)
