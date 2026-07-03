from voice_mode.tools.silence_profile import SilenceProfile


def test_fields_and_speech_active():
    p = SilenceProfile(pre_speech_delay=3.2, longest_gap=5.1,
                       total_silence=8.3, speech_active=4.0,
                       gaps=[(4.2, 9.3)])
    assert p.pre_speech_delay == 3.2
    assert p.longest_gap == 5.1
    assert p.total_silence == 8.3
    assert p.speech_active == 4.0
    assert p.gaps == [(4.2, 9.3)]


def test_significant_gaps_filters_by_threshold():
    p = SilenceProfile(0.0, 5.1, 6.0, 10.0,
                       gaps=[(1.0, 1.9), (4.2, 9.3)])  # 0.9s and 5.1s
    assert p.significant_gaps(2.0) == [(4.2, 9.3)]


def test_pre_speech_significant():
    p = SilenceProfile(3.2, 0.0, 3.2, 5.0, gaps=[])
    assert p.pre_speech_significant(2.0) is True
    assert p.pre_speech_significant(4.0) is False


def test_empty_profile():
    p = SilenceProfile.empty()
    assert p.pre_speech_delay == 0.0
    assert p.gaps == []
    assert p.significant_gaps(2.0) == []
