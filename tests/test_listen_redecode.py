"""Turn text: ``--turn-text joined|redecode`` (VM-2274 do-008).

``joined`` is the default and the spec's (conversation-log:12-13): the turn
line is the join of its partials, byte for byte as before. ``redecode``
writes a re-decode of the turn's whole audio, launched at the last quiet cut
so it runs inside the silence wait. Partials are the same in both modes.

Synthetic audio, fake STT, no device, no server, no sound.
"""

from __future__ import annotations

import pytest

from voice_mode.listen import capture
from voice_mode.listen.__main__ import build_parser
from voice_mode.listen.sources import SAMPLE_RATE
from tests.listen_helpers import CountingSource, RecordingSink, energy_detector, read_lines, synth

PRE, QUIET = 0.15, 0.35  # the chunker's default pre-roll and quiet cut


class DurationSTT:
    """Names each call by the length of the audio it got, so text depends only on audio."""

    name = "duration"

    def __init__(self, fail_calls=(), texts=None):
        self.calls: list[float] = []
        self.fail_calls = set(fail_calls)
        self.texts = dict(texts or {})

    def transcribe(self, audio):
        self.calls.append(len(audio) / SAMPLE_RATE)
        n = len(self.calls)
        if n in self.fail_calls:
            raise RuntimeError("fake whisper restarted")
        if n in self.texts:
            return self.texts[n]
        return f"d{len(audio) / SAMPLE_RATE:.2f}"


def run(tmp_path, segments, *, stt=None, tail=3.0, **kw):
    source = CountingSource(synth(segments), tail_silence_s=tail)
    sink = RecordingSink(tmp_path / "logs", source)
    kw.setdefault("stt_workers", 0)
    stt = stt or DurationSTT()
    result = capture(source, stt, sink, detector=energy_detector(), heartbeat=0, **kw)
    lines = read_lines(tmp_path / "logs")
    return result, lines, stt


def kind(lines, k):
    return [ln for ln in lines if ln["kind"] == k]


def dur(text: str) -> float:
    assert text.startswith("d"), text
    return float(text[1:])


# -- the default is joined, and unchanged ---------------------------------------


def test_default_is_joined_and_the_turn_line_carries_no_new_fields(tmp_path):
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 3.0)])
    (turn,) = kind(lines, "turn")
    assert turn["text"] == " ".join(p["text"] for p in kind(lines, "partial"))
    assert not {"text_from", "joined", "redecode", "redecode_wait_s", "speculative"} & set(turn)


def test_parser_default_is_joined_and_only_the_two_modes_parse():
    p = build_parser()
    assert p.parse_args(["capture"]).turn_text == "joined"
    assert p.parse_args(["capture", "--turn-text", "redecode"]).turn_text == "redecode"
    with pytest.raises(SystemExit):
        p.parse_args(["capture", "--turn-text", "cumulative"])


def test_an_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        run(tmp_path, [("speech", 1.0)], turn_text="rolling")


# -- redecode -------------------------------------------------------------------


def test_redecode_writes_the_whole_turn_audio_as_the_turn_text(tmp_path):
    # 3 s of speech: the 2 s soft max cuts it into two partials; the turn is ONE decode.
    _, lines, stt = run(tmp_path, [("silence", 0.5), ("speech", 3.0)], turn_text="redecode")
    partials, (turn,) = kind(lines, "partial"), kind(lines, "turn")
    assert len(partials) == 2
    assert turn["text_from"] == "redecode" and turn["speculative"] is True
    assert turn["joined"] == " ".join(p["text"] for p in partials)
    # the whole turn: pre-roll + all the speech + the quiet it was launched on
    assert 3.0 + QUIET - 0.05 <= dur(turn["text"]) <= 3.0 + PRE + QUIET + 0.1
    assert len(stt.calls) == 3, "two partials and one re-decode"


def test_partials_are_the_same_in_both_modes(tmp_path):
    seg = [("silence", 0.5), ("speech", 2.6), ("silence", 0.5), ("speech", 1.2)]
    _, joined, _ = run(tmp_path / "j", seg)
    _, redec, _ = run(tmp_path / "r", seg, turn_text="redecode")
    strip = lambda ls: [(p["text"], p["t0"], p["t1"]) for p in kind(ls, "partial")]
    assert strip(joined) == strip(redec)
    assert [t["t0"] for t in kind(joined, "turn")] == [t["t0"] for t in kind(redec, "turn")]
    assert [t["t1"] for t in kind(joined, "turn")] == [t["t1"] for t in kind(redec, "turn")]


def test_speech_resuming_after_the_quiet_cut_drops_the_early_decode(tmp_path):
    # a 0.8 s pause: past the 0.35 s quiet cut (a decode launches), inside the 2 s
    # silence (same turn). The turn text must cover BOTH phrases.
    _, lines, stt = run(tmp_path, [("silence", 0.5), ("speech", 1.0), ("silence", 0.8), ("speech", 1.0)],
                        turn_text="redecode")
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "redecode"
    assert dur(turn["text"]) >= 1.0 + 0.8 + 1.0 + QUIET - 0.05
    early = [d for d in stt.calls if 1.0 + QUIET - 0.05 <= d <= 1.0 + PRE + QUIET + 0.1]
    assert early, "a speculative decode was launched at the first quiet cut"


def test_two_turns_each_get_their_own_audio(tmp_path):
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 1.0), ("silence", 3.0), ("speech", 1.5)],
                      turn_text="redecode")
    a, b = kind(lines, "turn")
    assert dur(a["text"]) < 1.0 + PRE + QUIET + 0.1
    assert 1.5 + QUIET - 0.05 <= dur(b["text"]) <= 1.5 + PRE + QUIET + 0.1


def test_a_failed_redecode_keeps_the_joined_text(tmp_path):
    # call 1 is the partial cut on the quiet; call 2 is the speculative re-decode
    stt = DurationSTT(fail_calls={2})
    result, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 1.0)], stt=stt, turn_text="redecode")
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "joined" and turn["redecode"].startswith("error")
    assert turn["text"] == kind(lines, "partial")[0]["text"]
    assert result.reason == "eof", "a re-decode failure is not a capture error"


def test_an_empty_redecode_keeps_the_joined_text(tmp_path):
    stt = DurationSTT(texts={2: "  "})
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 1.0)], stt=stt, turn_text="redecode")
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "joined" and turn["redecode"] == "empty"


def test_redecode_never_turns_a_discarded_turn_into_a_turn(tmp_path):
    # the partials heard nothing (noise), the whole-audio decode "hears" something:
    # the turn is still discarded, so the mode changes turn text, never turn count
    stt = DurationSTT(texts={1: "", 2: "Thank you."})
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 1.0)], stt=stt, turn_text="redecode")
    assert not kind(lines, "turn")
    assert [ln for ln in lines if ln.get("event") == "turn-discarded"]


def test_a_turn_longer_than_the_cap_keeps_the_joined_text(tmp_path):
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 3.0)], turn_text="redecode", redecode_max_s=2.0)
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "joined" and turn["redecode"] == "too-long"
    assert turn["text"] == " ".join(p["text"] for p in kind(lines, "partial"))


def test_a_file_ending_mid_turn_still_gets_a_redecode(tmp_path):
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 1.0)], tail=0.0, turn_text="redecode")
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "redecode" and turn["speculative"] is False


def test_threaded_stt_redecodes_too(tmp_path):
    _, lines, _ = run(tmp_path, [("silence", 0.5), ("speech", 3.0)], turn_text="redecode", stt_workers=1)
    (turn,) = kind(lines, "turn")
    assert turn["text_from"] == "redecode"
    assert [p["text"] for p in kind(lines, "partial")] == turn["joined"].split(" ")
