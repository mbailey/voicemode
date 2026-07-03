from voice_mode.tools.converse import _assemble_voice_result
from voice_mode.tools.silence_profile import SilenceProfile


def _withgap():
    return SilenceProfile(0.7, 5.3, 6.0, 6.9, [(6.0, 11.3)], 0.7, 12.9)


def test_measure_blocks_summary_uses_timeline_and_drops_silence_field():
    words = [
        {"word": "모델은", "start": 0.9, "end": 5.9},
        {"word": "그러니까", "start": 11.4, "end": 12.7},
    ]
    out = _assemble_voice_result(
        "모델은 그러니까", "", "1.2s", "summary", _withgap(), words, 2.0,
        measure_blocks=True,
    )
    assert "(gap 0.7s) 모델은 (5.3s) (gap 5.3s) 그러니까 (1.6s)" in out
    assert "Silence:" not in out
    assert "⟨" not in out
    assert out.endswith("Timing: 1.2s")


def test_measure_blocks_off_unchanged_marker_path():
    words = [{"word": "네", "start": 0.1, "end": 0.4}]
    out = _assemble_voice_result(
        "네", "", "0.5s", "summary", SilenceProfile(0.0, 0.0, 0.0, 0.4, [], 0.0, 0.4),
        words, 2.0, measure_blocks=False,
    )
    assert out == "Voice response: 네 | Timing: 0.5s"
