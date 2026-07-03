from voice_mode.tools.silence_profile import SilenceProfile
from voice_mode.tools.block_timeline import render_block_timeline


def _profile():
    return SilenceProfile(
        pre_speech_delay=0.7, longest_gap=5.3, total_silence=6.0,
        speech_active=6.9, gaps=[(6.0, 11.3)],
        first_speech_start=0.7, recording_end=12.9,
    )


def test_render_assigns_words_to_blocks():
    words = [
        {"word": "모델은", "start": 0.9, "end": 5.9},
        {"word": "그러니까", "start": 11.4, "end": 12.7},
    ]
    out = render_block_timeline(_profile(), words, "모델은 그러니까")
    assert out == "(gap 0.7s) 모델은 (5.3s) (gap 5.3s) 그러니까 (1.6s)"


def test_render_gapless_single_block_uses_full_text():
    p = SilenceProfile(0.0, 0.0, 0.0, 3.0, [], 0.0, 3.0)
    assert render_block_timeline(p, None, "네 그렇게 해주세요") == "네 그렇게 해주세요 (3.0s)"


def test_render_without_words_falls_back_to_gap_shape():
    # gap present but no word timestamps: whole text in first speech block.
    out = render_block_timeline(_profile(), None, "모델은 그러니까")
    assert out == "(gap 0.7s) 모델은 그러니까 (5.3s) (gap 5.3s)  (1.6s)".replace("  ", " ")
