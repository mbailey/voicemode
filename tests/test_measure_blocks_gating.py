from voice_mode.tools.converse import _want_words_for_turn
from voice_mode.tools.silence_profile import SilenceProfile


def _gapless():
    return SilenceProfile(0.0, 0.0, 0.0, 3.0, [], 0.0, 3.0)


def _withgap():
    return SilenceProfile(0.7, 5.3, 6.0, 6.9, [(6.0, 11.3)], 0.7, 12.9)


def test_measure_blocks_off_uses_significance():
    # off + no significant gap -> no words
    assert _want_words_for_turn(_gapless(), measure_blocks=False, threshold=2.0) is False


def test_measure_blocks_on_gapless_skips_words():
    assert _want_words_for_turn(_gapless(), measure_blocks=True, threshold=2.0) is False


def test_measure_blocks_on_with_gap_requests_words():
    assert _want_words_for_turn(_withgap(), measure_blocks=True, threshold=2.0) is True
