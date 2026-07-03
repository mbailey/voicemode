from voice_mode.tools.silence_profile import SilenceProfile
from voice_mode.tools.silence_markers import insert_markers, format_silence_field


WORDS = [
    {"word": "결제하려는데", "start": 3.2, "end": 4.2},
    {"word": "카드가", "start": 9.3, "end": 9.9},
    {"word": "안돼요", "start": 9.9, "end": 10.5},
]


def test_insert_pause_between_bracketing_words():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert "결제하려는데 ⟨pause 5.1s⟩ 카드가" in out


def test_insert_pre_speech_prefix():
    prof = SilenceProfile(3.2, 0.0, 3.2, 3.0, gaps=[])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert out.startswith("⟨pre-speech 3.2s⟩ ")


def test_no_significant_no_change():
    prof = SilenceProfile(0.5, 0.8, 1.3, 5.0, gaps=[(4.2, 5.0)])
    out = insert_markers("결제하려는데 카드가 안돼요", WORDS, prof, 2.0)
    assert out == "결제하려는데 카드가 안돼요"


def test_missing_words_fallback_unchanged():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    assert insert_markers("결제하려는데 카드가", [], prof, 2.0) == "결제하려는데 카드가"


def test_format_field_only_significant():
    prof = SilenceProfile(3.2, 0.8, 4.0, 6.0, gaps=[(1.0, 1.8)])
    # pre 3.2 significant, gap 0.8 not
    assert format_silence_field(prof, 2.0) == "pre 3.2s, speech 6.0s"


def test_format_field_none_when_clean():
    prof = SilenceProfile(0.3, 0.5, 0.8, 4.0, gaps=[])
    assert format_silence_field(prof, 2.0) is None
