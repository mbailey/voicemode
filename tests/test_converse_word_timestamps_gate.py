from voice_mode.tools.converse import _needs_word_timestamps
from voice_mode.tools.silence_profile import SilenceProfile


def test_needs_true_on_significant_gap():
    p = SilenceProfile(0.0, 5.1, 5.1, 2.0, gaps=[(4.2, 9.3)])
    assert _needs_word_timestamps(p, 2.0) is True


def test_needs_true_on_significant_pre_speech():
    p = SilenceProfile(3.2, 0.0, 3.2, 3.0, gaps=[])
    assert _needs_word_timestamps(p, 2.0) is True


def test_needs_false_when_clean():
    p = SilenceProfile(0.3, 0.8, 1.1, 5.0, gaps=[(1.0, 1.8)])
    assert _needs_word_timestamps(p, 2.0) is False
