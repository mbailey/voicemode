from voice_mode.tools.silence_profile import SilenceProfile


def test_blocks_alternate_speech_and_gap():
    # pre-speech 0.7s, speech to 6.0, gap 6.0-11.3, speech to 12.9
    p = SilenceProfile(
        pre_speech_delay=0.7, longest_gap=5.3, total_silence=6.0,
        speech_active=6.9, gaps=[(6.0, 11.3)],
        first_speech_start=0.7, recording_end=12.9,
    )
    assert p.blocks() == [
        ("gap", 0.0, 0.7),
        ("speech", 0.7, 6.0),
        ("gap", 6.0, 11.3),
        ("speech", 11.3, 12.9),
    ]


def test_blocks_no_pre_speech_no_gap_single_block():
    p = SilenceProfile(
        pre_speech_delay=0.0, longest_gap=0.0, total_silence=0.0,
        speech_active=3.0, gaps=[], first_speech_start=0.0, recording_end=3.0,
    )
    assert p.blocks() == [("speech", 0.0, 3.0)]
