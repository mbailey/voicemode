from voice_mode.tools.converse import _assemble_voice_result
from voice_mode.tools.silence_profile import SilenceProfile

WORDS = [
    {"word": "결제하려는데", "start": 3.2, "end": 4.2},
    {"word": "카드가", "start": 9.3, "end": 9.9},
]


def test_summary_includes_markers_and_silence_field():
    prof = SilenceProfile(0.0, 5.1, 5.1, 2.2, gaps=[(4.2, 9.3)])
    out = _assemble_voice_result(
        response_text="결제하려는데 카드가", stt_info="", timing_str="record 10.0s",
        metrics_level="summary", profile=prof, words=WORDS, threshold=2.0)
    assert "⟨pause 5.1s⟩" in out
    assert "| Silence: gap 5.1s, speech 2.2s" in out
    assert "| Timing: record 10.0s" in out


def test_clean_turn_no_silence_field_no_markers():
    prof = SilenceProfile(0.2, 0.5, 0.7, 5.0, gaps=[])
    out = _assemble_voice_result(
        response_text="네 맞아요", stt_info="", timing_str="record 3.0s",
        metrics_level="summary", profile=prof, words=None, threshold=2.0)
    assert "⟨" not in out
    assert "Silence:" not in out
    assert out == "Voice response: 네 맞아요 | Timing: record 3.0s"
