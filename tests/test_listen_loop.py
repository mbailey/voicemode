"""Capture, "the ears" (VM-2274 do-001, spec task 3.0 as split into M1).

Each test names the criterion it proves. Synthetic audio, a fake STT,
unpaced sources, and Pip's real ``heard`` writer pointed at tmp_path: no
device, no server, no sound, and nothing written under ~/.voicemode.
"""

from __future__ import annotations

import threading
import time

import pytest

from voice_mode import heard
from voice_mode.listen import FRAME_S, Chunker, capture
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


@pytest.fixture(autouse=True)
def _no_real_voicemode_dir(tmp_path, monkeypatch):
    # heard reads VOICEMODE_BASE_DIR at call time: anything not given a
    # directory lands in tmp_path, never in the live ~/.voicemode.
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / "vm"))


def run(tmp_path, segments, *, tail=0.0, **kw):
    source = CountingSource(synth(segments), tail_silence_s=tail, realtime=kw.pop("realtime", False))
    sink = RecordingSink(tmp_path / "logs", source)
    kw.setdefault("stt_workers", 0)
    result = capture(source, kw.pop("stt", FakeSTT()), sink, detector=kw.pop("detector", energy_detector()), **kw)
    return result, read_lines(tmp_path / "logs"), sink


def of_kind(lines, kind, event=None):
    return [ln for ln in lines if ln["kind"] == kind and (event is None or ln.get("event") == event)]


def stopped(lines):
    ends = of_kind(lines, "event", heard.EV_LISTEN_STOPPED)
    assert len(ends) == 1 and ends[0] is lines[-1], "exactly one listen-stopped, and it is the last line"
    return ends[0]


# -- started within 1 s --------------------------------------------------------


def test_started_event_is_written_within_one_second_of_arming(tmp_path):
    source = CountingSource(synth([("silence", 1.5)]), realtime=True)
    sink = RecordingSink(tmp_path / "logs", source)
    armed = time.monotonic()
    capture(source, FakeSTT(), sink, detector=energy_detector(), stt_workers=0)
    lines = read_lines(tmp_path / "logs")

    first = lines[0]
    assert first["kind"] == "event" and first["event"] == heard.EV_LISTEN_STARTED
    assert first["source"] == "file" and first["device"] == "synthetic"
    assert sink.at_wall[first["seq"]] - armed < 1.0
    assert sink.at_frames[first["seq"]] == 0, "written before the source delivered a frame"


# -- partials (chunks) before the turn, as they come ----------------------------


def test_partials_are_written_while_speech_is_still_going(tmp_path):
    # Two phrases split by a short (0.5 s) gap: a chunk is cut on the gap,
    # so the first partial must land while the second phrase is still playing.
    segments = [("silence", 0.3), ("speech", 1.0), ("silence", 0.5), ("speech", 2.0)]
    result, lines, sink = run(tmp_path, segments, tail=3.0)

    partials = of_kind(lines, "partial")
    turns = of_kind(lines, "turn")
    assert len(partials) >= 2 and len(turns) == 1
    assert all(p["seq"] < turns[0]["seq"] for p in partials)
    assert all(p["final"] is False for p in partials)
    speech_end = 0.3 + 1.0 + 0.5 + 2.0
    assert stream_s_at(sink, partials[0]["seq"]) < speech_end, "first partial was buffered to the end"
    # Partials are CHUNKS, not cumulative: the turn is their join.
    assert turns[0]["text"] == " ".join(p["text"] for p in partials)
    assert turns[0]["final"] is True and turns[0]["detector"] == "vad-silence"


def test_partials_come_during_one_long_unbroken_utterance(tmp_path):
    # No gap at all for 12 s: the max-chunk cut still yields partials mid-speech.
    result, lines, sink = run(tmp_path, [("speech", 12.0)], tail=3.0, chunker=Chunker(max_s=5.0))
    partials = of_kind(lines, "partial")
    assert len(partials) >= 2
    assert stream_s_at(sink, partials[0]["seq"]) < 12.0


# -- 2 s of silence makes a turn line, with its detector ------------------------


def test_two_seconds_of_silence_writes_a_turn_line_with_detector(tmp_path):
    result, lines, sink = run(tmp_path, [("silence", 0.5), ("speech", 1.0), ("silence", 2.5)])
    turns = of_kind(lines, "turn")
    assert len(turns) == 1 and turns[0]["detector"] == "vad-silence"
    # The turn line is written 2.0 s after speech stopped (to the frame).
    assert stream_s_at(sink, turns[0]["seq"]) == pytest.approx(1.5 + 2.0, abs=2 * FRAME_S)
    assert turns[0]["t1"] == pytest.approx(1.5, abs=2 * FRAME_S)


def test_a_pause_shorter_than_the_silence_threshold_stays_inside_the_turn(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 1.0), ("silence", 1.8), ("speech", 1.0), ("silence", 2.5)])
    assert len(of_kind(lines, "turn")) == 1


# -- a 3 s pause: capture goes on, both sides are in the log -------------------


def test_a_three_second_pause_does_not_stop_capture_and_both_sides_are_logged(tmp_path):
    result, lines, sink = run(tmp_path, SPEECH_PAUSE_SPEECH, tail=3.0)

    second_speech_starts = 0.5 + 1.5 + 3.0
    # Capture ran to the end of the source: nothing in the pause stopped it.
    assert result.reason == "eof"
    assert stopped(lines)["stream_s"] == pytest.approx(second_speech_starts + 1.5 + 3.0, abs=2 * FRAME_S)
    # The words on both sides of the pause are in the log as partials.
    partials = of_kind(lines, "partial")
    assert any(p["t1"] <= 2.0 + 0.5 for p in partials)
    assert any(p["t0"] >= second_speech_starts - 0.5 for p in partials)
    # The spec's 2 s silence (inside the 3 s pause) ends the first turn:
    # a turn LINE, not a stop.
    turns = of_kind(lines, "turn")
    assert len(turns) == 2
    assert stream_s_at(sink, turns[0]["seq"]) < second_speech_starts
    assert result.text == "\n".join(t["text"] for t in turns)


# -- capture KEEPS RUNNING after a turn, and after an aged one -----------------


def test_capture_keeps_running_after_an_aged_turn(tmp_path):
    # A turn, then 20 s of quiet (the turn is well past the 8 s age), then
    # new speech: capture is still there to hear it.
    segments = [("speech", 1.0), ("silence", 20.0), ("speech", 1.0)]
    result, lines, sink = run(tmp_path, segments, tail=3.0)

    turns = of_kind(lines, "turn")
    assert len(turns) == 2
    first_at, second_at = (stream_s_at(sink, t["seq"]) for t in turns)
    assert second_at - first_at > 8.0 + 10.0
    assert result.reason == "eof"  # it stopped because the file ended, not on a turn


def test_with_no_ceiling_capture_never_stops_on_its_own(tmp_path):
    # An endless quiet room after one utterance: only the stop request ends it.
    source = CountingSource(synth([("speech", 1.0)]), tail_silence_s=None)
    sink = RecordingSink(tmp_path / "logs", source)
    result = capture(
        source, FakeSTT(), sink, detector=energy_detector(), stt_workers=0,
        stop=lambda: source.yielded * FRAME_S >= 120.0,
    )
    lines = read_lines(tmp_path / "logs")
    assert result.reason == "stop"
    assert stopped(lines)["stream_s"] == pytest.approx(120.0, abs=0.5)
    assert len(of_kind(lines, "turn")) == 1


# -- stop => a stopped event with its reason ----------------------------------


def test_stop_request_writes_stopped_with_reason_stop(tmp_path):
    stop = threading.Event()

    class StopAtFirstChunk(FakeSTT):
        def transcribe(self, audio):
            stop.set()
            return super().transcribe(audio)

    result, lines, _ = run(tmp_path, [("speech", 1.0)], tail=None, stop=stop, stt=StopAtFirstChunk())
    assert result.reason == "stop"
    end = stopped(lines)
    assert end["reason"] == "stop" and result.cursor == end["seq"]
    assert end["stream_s"] < 2.0


def test_a_stop_file_stops_capture(tmp_path):
    flag = tmp_path / "stop-listen"
    source = CountingSource(synth([]), tail_silence_s=None)

    def frames():
        for frame in CountingSource.frames(source):
            if source.yielded == 100:
                flag.touch()
            yield frame

    source.frames = frames
    sink = RecordingSink(tmp_path / "logs", source)
    result = capture(source, FakeSTT(), sink, detector=energy_detector(), stt_workers=0, stop_file=flag)
    assert result.reason == "stop"
    assert stopped(read_lines(tmp_path / "logs"))["stream_s"] == pytest.approx(100 * FRAME_S, abs=0.35)


def test_an_optional_ceiling_stops_mid_speech_and_keeps_the_partials(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 30.0)], ceiling=7.0, chunker=Chunker(max_s=3.0))
    assert result.reason == "ceiling"
    end = stopped(lines)
    assert end["reason"] == "ceiling" and end["stream_s"] == pytest.approx(7.0, abs=2 * FRAME_S)
    # Nothing already heard is lost: the open chunk is flushed to a partial,
    # and the turn the ceiling cut into is closed.
    partials = of_kind(lines, "partial")
    assert len(partials) == 3 and partials[-1]["t1"] == pytest.approx(7.0, abs=2 * FRAME_S)
    assert len(of_kind(lines, "turn")) == 1


# -- every line carries ts, seq, kind, source, device ---------------------------


def test_every_line_carries_ts_seq_kind_source_device(tmp_path):
    result, lines, _ = run(tmp_path, SPEECH_PAUSE_SPEECH, tail=3.0, heartbeat=2.0, session="s-1", agent="cora")
    assert {ln["kind"] for ln in lines} == {"event", "partial", "turn"}
    assert [ln["seq"] for ln in lines] == list(range(1, len(lines) + 1))
    for ln in lines:
        for key in ("ts", "seq", "kind", "source", "device"):
            assert key in ln, f"{key} missing from {ln}"
        assert parse_ts(ln["ts"]).tzinfo is not None, "ts must carry an offset"
        assert ln["source"] == "file" and ln["device"] == "synthetic"
        assert ln["session"] == "s-1" and ln["agent"] == "cora"
        assert ln["v"] == heard.SCHEMA, "written by heard, not a second writer"
        if ln["kind"] in ("partial", "turn"):
            assert ln["text"]
        else:
            assert ln["event"]


def test_default_sink_is_heard_under_voicemode_base_dir(tmp_path):
    source = CountingSource(synth([("speech", 1.0)]))
    result = capture(source, FakeSTT(), detector=energy_detector(), stt_workers=0)
    lines = read_lines(tmp_path / "vm" / "logs" / "conversations")
    assert lines and lines[-1]["event"] == heard.EV_LISTEN_STOPPED and result.cursor == lines[-1]["seq"]
    assert heard.log_path(directory=tmp_path / "vm" / "logs" / "conversations").exists()


# -- alive: heartbeats with the input level -----------------------------------


def test_heartbeats_on_the_configured_period_with_the_input_level(tmp_path):
    # 2.2 s quiet, 0.6 s tone, 2.2 s quiet (off the beat boundaries): the
    # level is zero, then not, then zero.
    segments = [("silence", 2.2), ("speech", 0.6), ("silence", 2.2)]
    result, lines, _ = run(tmp_path, segments, heartbeat=1.0, detector=energy_detector(silence_s=10.0))
    beats = of_kind(lines, "event", heard.EV_HEARTBEAT)
    assert [b["stream_s"] for b in beats] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0], abs=2 * FRAME_S)
    peaks = [b["peak"] for b in beats]
    assert peaks[0] == 0 and peaks[1] == 0 and peaks[4] == 0, "a zero mic reads zero, visibly"
    assert peaks[2] >= 3900 and beats[2]["rms"] > 2000 and beats[2]["rms_dbfs"] < 0
    assert beats[0]["rms"] == 0 and "rms_dbfs" not in beats[0]  # log(0): no dBFS, not -inf


# -- failure is loud ------------------------------------------------------------


def test_a_failing_source_is_an_error_and_still_writes_stopped(tmp_path):
    class Broken(CountingSource):
        def frames(self):
            yield from list(super().frames())[:10]
            raise OSError("device unplugged")

    source = Broken(synth([("silence", 1.0)]))
    sink = RecordingSink(tmp_path / "logs", source)
    result = capture(source, FakeSTT(), sink, detector=energy_detector(), stt_workers=0)
    end = stopped(read_lines(tmp_path / "logs"))
    assert result.reason == "error" and "device unplugged" in result.error
    assert end["reason"] == "error" and "device unplugged" in end["error"]


def test_stt_that_keeps_failing_is_an_error(tmp_path):
    segments = [("speech", 0.5), ("silence", 0.5)] * 5
    result, lines, _ = run(tmp_path, segments, stt=FakeSTT(fail_always=True))
    assert result.reason == "error" and "STT failed 3 times" in result.error
    assert len(of_kind(lines, "event", "stt-error")) == 3


def test_an_unwritable_log_is_an_error_not_a_silent_listener(tmp_path):
    class Full:
        def write(self, line):
            raise OSError(28, "No space left on device")

    result = capture(CountingSource(synth([("speech", 1.0)])), FakeSTT(), Full(), detector=energy_detector(), stt_workers=0)
    assert result.reason == "error" and "No space left" in result.error


def test_a_turn_with_no_recognised_text_is_discarded(tmp_path):
    # Whisper returning "" for a noise burst must not become a turn.
    result, lines, _ = run(tmp_path, [("speech", 1.0)], stt=FakeSTT(texts=[""]))
    assert not of_kind(lines, "turn")
    assert of_kind(lines, "event", "turn-discarded")


def test_a_file_ending_mid_turn_closes_the_turn(tmp_path):
    result, lines, _ = run(tmp_path, [("speech", 1.0)])
    assert result.reason == "eof"
    assert len(of_kind(lines, "turn")) == 1


# -- threaded STT: same contract, off the frame loop ---------------------------


def test_threaded_stt_keeps_order_and_joins_before_the_turn(tmp_path):
    class SlowSTT(FakeSTT):
        def transcribe(self, audio):
            time.sleep(0.05)
            return super().transcribe(audio)

    segments = [("speech", 0.8), ("silence", 0.5), ("speech", 0.8), ("silence", 0.5), ("speech", 0.8)]
    result, lines, _ = run(tmp_path, segments, tail=3.0, stt=SlowSTT(), stt_workers=1)
    assert [p["text"] for p in of_kind(lines, "partial")] == ["w1", "w2", "w3"]
    assert [t["text"] for t in of_kind(lines, "turn")] == ["w1 w2 w3"]
