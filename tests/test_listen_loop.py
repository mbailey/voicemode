"""The listen loop's contract (VM-2274, spec task 3.0).

Each test names the success criterion it proves. Synthetic audio, a fake
STT, unpaced sources: no device, no server, no sound.
"""

from __future__ import annotations

import threading
import time

import pytest

from voice_mode.listen import FRAME_S, Chunker, listen
from tests.listen_helpers import (
    CountingSource,
    FakeSTT,
    RecordingSink,
    energy_detector,
    parse_ts,
    read_lines,
    stream_s_at,
    synth,
)

SPEECH_PAUSE_SPEECH = [("silence", 0.5), ("speech", 1.5), ("silence", 3.0), ("speech", 1.5)]


def run(tmp_path, segments, *, tail=None, **kw):
    source = CountingSource(synth(segments), tail_silence_s=tail, realtime=kw.pop("realtime", False))
    sink = RecordingSink(tmp_path / "heard.jsonl", source)
    kw.setdefault("stt_workers", 0)
    result = listen(source, sink, kw.pop("stt", FakeSTT()), detector=kw.pop("detector", energy_detector()), **kw)
    return result, read_lines(sink.path), sink


def of_kind(lines, kind, event=None):
    return [ln for ln in lines if ln["kind"] == kind and (event is None or ln.get("event") == event)]


# -- started within 1 s --------------------------------------------------------


def test_started_event_is_written_within_one_second_of_arming(tmp_path):
    source = CountingSource(synth([("silence", 1.5)]), realtime=True, tail_silence_s=0)
    sink = RecordingSink(tmp_path / "heard.jsonl", source)
    armed = time.monotonic()
    listen(source, sink, FakeSTT(), detector=energy_detector(), stt_workers=0)
    lines = read_lines(sink.path)

    first = lines[0]
    assert first["kind"] == "event" and first["event"] == "listen started"
    assert first["seq"] == 1
    assert first["source"] == "file" and first["device"] == "synthetic"
    assert sink.at_wall[1] - armed < 1.0
    # Written before the source delivered a single frame.
    assert sink.at_frames[1] == 0


# -- partials before the turn, as they come ------------------------------------


def test_partials_are_written_while_speech_is_still_going(tmp_path):
    # Two phrases split by a short (0.5 s) gap: a chunk is cut on the gap,
    # so the first partial must land while the second phrase is still playing.
    segments = [("silence", 0.3), ("speech", 1.0), ("silence", 0.5), ("speech", 2.0)]
    result, lines, sink = run(tmp_path, segments, tail=12.0)

    partials = of_kind(lines, "partial")
    turns = of_kind(lines, "turn")
    assert len(partials) >= 2 and len(turns) == 1
    assert all(p["seq"] < turns[0]["seq"] for p in partials)
    assert all(p["final"] is False for p in partials)
    speech_end = 0.3 + 1.0 + 0.5 + 2.0
    assert stream_s_at(sink, partials[0]["seq"]) < speech_end, "first partial was buffered to the end"
    assert turns[0]["text"] == " ".join(p["text"] for p in partials)
    assert turns[0]["final"] is True and turns[0]["detector"] == "vad-silence"


def test_partials_come_during_one_long_unbroken_utterance(tmp_path):
    # No gap at all for 12 s: the max-chunk cut still yields partials mid-speech.
    result, lines, sink = run(tmp_path, [("speech", 12.0)], tail=12.0, chunker=Chunker(max_s=5.0))
    partials = of_kind(lines, "partial")
    assert len(partials) >= 2
    assert stream_s_at(sink, partials[0]["seq"]) < 12.0


# -- 2 s of silence makes a turn line ------------------------------------------


def test_two_seconds_of_silence_writes_a_turn_line(tmp_path):
    result, lines, sink = run(tmp_path, [("silence", 0.5), ("speech", 1.0), ("silence", 2.5)], tail=0)
    turns = of_kind(lines, "turn")
    assert len(turns) == 1
    # The turn line is written 2.0 s after speech stopped (to the frame).
    written_at = stream_s_at(sink, turns[0]["seq"])
    assert written_at == pytest.approx(1.5 + 2.0, abs=2 * FRAME_S)
    assert turns[0]["t1"] == pytest.approx(1.5, abs=2 * FRAME_S)


def test_a_pause_shorter_than_the_silence_threshold_stays_inside_the_turn(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 1.0), ("silence", 1.8), ("speech", 1.0), ("silence", 2.5)], tail=0)
    assert len(of_kind(lines, "turn")) == 1


# -- a 3 s pause does not return -----------------------------------------------


def test_a_three_second_pause_does_not_return(tmp_path):
    result, lines, sink = run(tmp_path, SPEECH_PAUSE_SPEECH, tail=15.0, age=8.0)

    second_speech_starts = 0.5 + 1.5 + 3.0
    second_speech_ends = second_speech_starts + 1.5
    stopped = of_kind(lines, "event", "listen stopped")[0]
    # It did not return in the pause; it returned on the SECOND turn, aged.
    assert result.reason == "turn"
    assert stopped["stream_s"] > second_speech_starts
    assert stopped["stream_s"] == pytest.approx(second_speech_ends + 2.0 + 8.0, abs=2 * FRAME_S)
    # The words on both sides of the pause are in the log as partials.
    partials = of_kind(lines, "partial")
    assert any(p["t1"] <= 2.0 + 0.5 for p in partials)
    assert any(p["t0"] >= second_speech_starts - 0.5 for p in partials)
    # The 2 s silence inside the 3 s pause ended the first turn -- a turn
    # line, not a return.
    turns = of_kind(lines, "turn")
    assert len(turns) == 2
    assert stream_s_at(sink, turns[0]["seq"]) < second_speech_starts
    assert result.text == "\n".join(t["text"] for t in turns)


# -- the aged turn returns {reason: turn, text, cursor} ------------------------


def test_aged_turn_returns_reason_text_and_cursor(tmp_path):
    result, lines, sink = run(tmp_path, [("silence", 0.5), ("speech", 1.5)], tail=20.0, age=8.0)

    turns = of_kind(lines, "turn")
    assert len(turns) == 1
    assert result.reason == "turn"
    assert result.text == turns[0]["text"] and result.text
    # The cursor is the seq of the last line written: the `listen stopped` line.
    assert result.cursor == lines[-1]["seq"]
    assert lines[-1]["event"] == "listen stopped" and lines[-1]["reason"] == "turn"
    # It waited for the turn to be `age` old, not less.
    aged_for = lines[-1]["stream_s"] - stream_s_at(sink, turns[0]["seq"])
    assert aged_for == pytest.approx(8.0, abs=2 * FRAME_S)
    assert result.to_dict() == {"reason": "turn", "text": result.text, "cursor": result.cursor}


def test_new_speech_before_the_turn_ages_holds_the_return(tmp_path):
    # A second utterance 5 s after the first turn: age restarts from the new turn.
    segments = [("speech", 1.0), ("silence", 7.0), ("speech", 1.0)]
    result, lines, _ = run(tmp_path, segments, tail=20.0, age=8.0)
    assert result.reason == "turn"
    assert len(of_kind(lines, "turn")) == 2
    assert lines[-1]["stream_s"] == pytest.approx(1.0 + 7.0 + 1.0 + 2.0 + 8.0, abs=2 * FRAME_S)


# -- the ceiling returns reason ceiling ----------------------------------------


def test_ceiling_returns_reason_ceiling_mid_speech_with_partials_kept(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 30.0)], tail=0, ceiling=7.0, chunker=Chunker(max_s=3.0))
    assert result.reason == "ceiling"
    assert result.cursor == lines[-1]["seq"]
    assert lines[-1]["event"] == "listen stopped" and lines[-1]["reason"] == "ceiling"
    assert lines[-1]["stream_s"] == pytest.approx(7.0, abs=2 * FRAME_S)
    # Nothing already heard is lost: the open chunk was flushed to a partial.
    partials = of_kind(lines, "partial")
    assert len(partials) == 3
    assert partials[-1]["t1"] == pytest.approx(7.0, abs=2 * FRAME_S)
    assert not of_kind(lines, "turn")


def test_ceiling_in_a_silent_room(tmp_path):
    result, lines, _ = run(tmp_path, [], tail=None, ceiling=4.0, heartbeat=1.0)
    assert result.reason == "ceiling" and result.text == ""
    assert not of_kind(lines, "partial") and not of_kind(lines, "turn")


# -- every line carries ts, seq, kind, source, device ---------------------------


def test_every_line_carries_ts_seq_kind_source_device(tmp_path):
    result, lines, _ = run(tmp_path, SPEECH_PAUSE_SPEECH, tail=15.0, heartbeat=2.0, session="s-1", agent="cora")
    kinds = {ln["kind"] for ln in lines}
    assert kinds == {"event", "partial", "turn"}
    seqs = [ln["seq"] for ln in lines]
    assert seqs == list(range(1, len(lines) + 1))
    for ln in lines:
        for key in ("ts", "seq", "kind", "source", "device"):
            assert key in ln, f"{key} missing from {ln}"
        assert parse_ts(ln["ts"]).tzinfo is not None, "ts must carry an offset"
        assert ln["source"] == "file" and ln["device"] == "synthetic"
        assert ln["session"] == "s-1" and ln["agent"] == "cora"
        if ln["kind"] in ("partial", "turn"):
            assert ln["text"]
        if ln["kind"] == "event":
            assert ln["event"]


# -- alive: heartbeats, stopped on every exit ----------------------------------


def test_heartbeats_on_the_configured_period(tmp_path):
    result, lines, _ = run(tmp_path, [], tail=None, ceiling=5.0, heartbeat=1.0)
    beats = of_kind(lines, "event", "heartbeat")
    assert [b["stream_s"] for b in beats] == pytest.approx([1.0, 2.0, 3.0, 4.0], abs=2 * FRAME_S)


def test_stop_request_returns_reason_stop(tmp_path):
    stop = threading.Event()
    stt = FakeSTT()

    class StopAfterFirstPartial(FakeSTT):
        def transcribe(self, audio):
            stop.set()
            return stt.transcribe(audio)

    result, lines, _ = run(tmp_path, [("speech", 1.0)], tail=None, stop=stop, stt=StopAfterFirstPartial())
    assert result.reason == "stop"
    assert lines[-1]["event"] == "listen stopped" and lines[-1]["reason"] == "stop"


def test_a_callable_stop_request_is_honoured(tmp_path):
    result, lines, _ = run(tmp_path, [], tail=None, stop=lambda: True)
    assert result.reason == "stop"


def test_a_failing_source_returns_error_and_still_writes_stopped(tmp_path):
    class Broken(CountingSource):
        def frames(self):
            yield from list(super().frames())[:10]
            raise OSError("device unplugged")

    source = Broken(synth([("silence", 1.0)]), tail_silence_s=0)
    sink = RecordingSink(tmp_path / "heard.jsonl", source)
    result = listen(source, sink, FakeSTT(), detector=energy_detector(), stt_workers=0)
    lines = read_lines(sink.path)
    assert result.reason == "error" and "device unplugged" in result.error
    assert lines[-1]["event"] == "listen stopped" and lines[-1]["reason"] == "error"
    assert result.cursor == lines[-1]["seq"]


def test_stt_that_keeps_failing_returns_error(tmp_path):
    segments = [("speech", 0.5), ("silence", 0.5)] * 5
    result, lines, _ = run(tmp_path, segments, tail=None, stt=FakeSTT(fail_always=True))
    assert result.reason == "error" and "STT failed 3 times" in result.error
    assert len(of_kind(lines, "event", "stt-error")) == 3


def test_a_turn_with_no_recognised_text_is_discarded_not_returned(tmp_path):
    # Whisper returning "" for a noise burst must not wake an agent.
    result, lines, _ = run(tmp_path, [("speech", 1.0)], tail=0, stt=FakeSTT(texts=[""]))
    assert not of_kind(lines, "turn")
    assert of_kind(lines, "event", "turn-discarded")


def test_a_finite_source_ending_returns_eof_and_closes_the_open_turn(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 1.0)], tail=0)
    assert result.reason == "eof"
    assert len(of_kind(lines, "turn")) == 1


# -- threaded STT: same contract, off the frame loop ---------------------------


def test_threaded_stt_keeps_order_and_joins_before_the_turn(tmp_path):
    class SlowSTT(FakeSTT):
        def transcribe(self, audio):
            time.sleep(0.05)
            return super().transcribe(audio)

    segments = [("speech", 0.8), ("silence", 0.5), ("speech", 0.8), ("silence", 0.5), ("speech", 0.8)]
    result, lines, _ = run(tmp_path, segments, tail=12.0, stt=SlowSTT(), stt_workers=1)
    partials = of_kind(lines, "partial")
    assert [p["text"] for p in partials] == ["w1", "w2", "w3"]
    assert result.reason == "turn" and result.text == "w1 w2 w3"
