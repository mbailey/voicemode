"""The listen spike's parts (VM-2274): sources, detector, chunker, sink, STT, CLI.

No device, no server, no sound: the WAVs are written to tmp_path, the STT
talks to an httpx MockTransport, and the CLI's whisper is a fake.
"""

from __future__ import annotations

import json
import time
import wave

import httpx
import numpy as np
import pytest

from voice_mode.listen import (
    FRAME_S,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    ArraySource,
    Chunker,
    EnergyClassifier,
    FileSource,
    HeardSink,
    MemorySink,
    SilenceTurnDetector,
    SourceError,
    WebRtcClassifier,
    WhisperSTT,
    make_detector,
    open_source,
)
from voice_mode.listen import __main__ as cli
from voice_mode.listen import detector as detector_mod
from tests.listen_helpers import FakeSTT, read_lines, synth


@pytest.fixture(autouse=True)
def _no_real_voicemode_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / "vm"))


def write_wav(path, samples, rate=SAMPLE_RATE, channels=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return path


# -- sources -------------------------------------------------------------------


def test_array_source_yields_fixed_16k_frames_and_pads_the_last():
    src = ArraySource(np.ones(FRAME_SAMPLES * 2 + 7, dtype=np.int16), realtime=False, tail_silence_s=0)
    frames = list(src.frames())
    assert len(frames) == 3
    assert all(f.dtype == np.int16 and f.shape == (FRAME_SAMPLES,) for f in frames)
    assert frames[2][7:].sum() == 0


def test_array_source_tail_of_silence():
    src = ArraySource(np.ones(FRAME_SAMPLES, dtype=np.int16), realtime=False, tail_silence_s=0.3)
    frames = list(src.frames())
    assert len(frames) == 1 + 10
    assert all(not f.any() for f in frames[1:])


def test_array_source_is_paced_at_real_time():
    src = ArraySource(np.zeros(int(0.6 * SAMPLE_RATE), dtype=np.int16), realtime=True, tail_silence_s=0)
    start = time.monotonic()
    n = sum(1 for _ in src.frames())
    elapsed = time.monotonic() - start
    assert n == 20
    assert elapsed == pytest.approx((n - 1) * FRAME_S, abs=0.15)


def test_file_source_reads_a_wav_and_names_it(tmp_path):
    path = write_wav(tmp_path / "speech.wav", synth([("speech", 0.3)]))
    src = FileSource(path, realtime=False, tail_silence_s=0)
    assert src.name == "file" and src.device == "speech.wav"
    assert sum(1 for _ in src.frames()) == 10


def test_file_source_converts_stereo_44k_to_16k_mono(tmp_path):
    rate = 44100
    mono = (3000 * np.sin(2 * np.pi * 220 * np.arange(rate) / rate)).astype(np.int16)
    path = write_wav(tmp_path / "stereo.wav", np.repeat(mono, 2), rate=rate, channels=2)
    src = FileSource(path, realtime=False, tail_silence_s=0)
    assert src.duration_s == pytest.approx(1.0, abs=FRAME_S)


def test_file_source_ends_with_the_wav_by_default_and_can_pad_silence(tmp_path):
    path = write_wav(tmp_path / "s.wav", synth([("speech", 0.09)]))
    assert sum(1 for _ in FileSource(path, realtime=False).frames()) == 3
    padded = list(FileSource(path, realtime=False, tail_silence_s=0.3).frames())
    assert len(padded) == 13 and not padded[-1].any()
    endless = FileSource(path, realtime=False, tail_silence_s=None).frames()
    assert len([next(endless) for _ in range(500)]) == 500


def test_bad_wav_and_unknown_source_raise_source_error(tmp_path):
    (tmp_path / "nope.wav").write_bytes(b"not a wav")
    with pytest.raises(SourceError):
        FileSource(tmp_path / "nope.wav")
    with pytest.raises(SourceError):
        open_source("tape:/dev/null")


def test_open_source_file_spec(tmp_path):
    path = write_wav(tmp_path / "x.wav", synth([("speech", 0.1)]))
    src = open_source(f"file:{path}", realtime=False)
    assert isinstance(src, FileSource) and src.realtime is False


# -- detector ------------------------------------------------------------------


def test_silence_detector_opens_on_a_run_of_speech_and_closes_after_silence_s():
    det = SilenceTurnDetector(0.3, classifier=EnergyClassifier(500))
    speech, quiet = synth([("speech", FRAME_S)]), np.zeros(FRAME_SAMPLES, dtype=np.int16)
    verdicts = [det.feed(speech) for _ in range(3)]
    assert [v.turn_started for v in verdicts] == [False, False, True]
    closes = [det.feed(quiet) for _ in range(10)]
    assert [v.end_of_turn for v in closes].index(True) == 9  # 10 frames = 0.3 s
    assert not det.in_turn


def test_a_click_does_not_open_a_turn():
    det = SilenceTurnDetector(2.0, classifier=EnergyClassifier(500))
    speech, quiet = synth([("speech", FRAME_S)]), np.zeros(FRAME_SAMPLES, dtype=np.int16)
    for frame in [speech, speech, quiet, speech, quiet]:
        assert not det.feed(frame).turn_started
    assert not det.in_turn


def test_detector_defaults_to_two_seconds_and_is_named_vad_silence():
    det = make_detector("vad-silence", classifier=EnergyClassifier())
    assert det.name == "vad-silence" and det.silence_s == 2.0
    with pytest.raises(ValueError):
        make_detector("silero")


def test_webrtc_classifier_hears_silence_as_silence():
    import webrtcvad

    if not hasattr(webrtcvad, "__file__"):
        # tests/test_silence_detection.py:10 replaces sys.modules['webrtcvad']
        # with a MagicMock at collection, for the whole session (pre-existing).
        pytest.skip("webrtcvad is a session-wide MagicMock (tests/test_silence_detection.py:10)")
    assert WebRtcClassifier()(np.zeros(FRAME_SAMPLES, dtype=np.int16)) is False


def test_default_classifier_falls_back_to_energy_without_webrtcvad(monkeypatch):
    def no_webrtc(*a, **k):
        raise ImportError("no webrtcvad")

    monkeypatch.setattr(detector_mod, "WebRtcClassifier", no_webrtc)
    assert isinstance(detector_mod.default_classifier(), EnergyClassifier)


# -- chunker -------------------------------------------------------------------


def feed_all(chunker, samples, classifier=EnergyClassifier(500)):
    chunks = []
    for i in range(len(samples) // FRAME_SAMPLES):
        frame = samples[i * FRAME_SAMPLES:(i + 1) * FRAME_SAMPLES]
        c = chunker.feed(frame, classifier(frame), i * FRAME_S)
        if c is not None:
            chunks.append(c)
    return chunks


def test_chunker_cuts_on_a_short_quiet_with_preroll():
    samples = synth([("silence", 0.5), ("speech", 0.6), ("silence", 0.5), ("speech", 0.6), ("silence", 0.5)])
    chunks = feed_all(Chunker(quiet_s=0.35, preroll_s=0.15), samples)
    assert len(chunks) == 2
    assert chunks[0].t0 == pytest.approx(0.5 - 0.15, abs=FRAME_S)
    assert chunks[0].t1 == pytest.approx(0.5 + 0.6 + 0.35, abs=FRAME_S)


def test_chunker_cuts_long_speech_at_max_s():
    # a one-frame cut window is the hard edge: every chunk is exactly max_s
    chunks = feed_all(Chunker(max_s=1.0, cut_window_s=FRAME_S), synth([("speech", 3.2)]))
    assert [c.t1 - c.t0 for c in chunks] == pytest.approx([1.0, 1.0, 1.0], abs=FRAME_S)  # 33 frames


def _speech_with_dip(total_s, dip_at_s, dip_s=0.06, loud=4000, soft=900):
    """A loud tone with one quieter stretch (still speech to EnergyClassifier(500))."""
    from tests.listen_helpers import SAMPLE_RATE
    n = int(round(total_s * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    amp = np.full(n, float(loud))
    a, b = int(round(dip_at_s * SAMPLE_RATE)), int(round((dip_at_s + dip_s) * SAMPLE_RATE))
    amp[a:b] = soft
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.int16)


def test_soft_cut_lands_on_the_quietest_frame_in_the_window():
    # do-007: max 2.0 s, window 0.4 s; the dip at 1.75 s is inside the window, so the
    # first chunk ends just after the dip, not at the hard 2.0 s edge
    samples = _speech_with_dip(3.0, dip_at_s=1.75)
    chunks = feed_all(Chunker(max_s=2.0, cut_window_s=0.4, preroll_s=0.0), samples)
    assert chunks, "no chunk was cut"
    assert 1.75 <= chunks[0].t1 <= 1.75 + 0.06 + FRAME_S


def test_soft_cut_chunks_tile_the_speech_without_gap_or_overlap():
    samples = np.concatenate([_speech_with_dip(2.5, dip_at_s=1.7), synth([("silence", 0.5)])])
    ch = Chunker(max_s=2.0, cut_window_s=0.4, preroll_s=0.0)
    chunks = feed_all(ch, samples)
    assert len(chunks) == 2
    assert chunks[1].t0 == pytest.approx(chunks[0].t1)          # the carried frames open chunk 2
    total = sum(len(c.audio) for c in chunks)
    assert total == int(round((chunks[-1].t1 - chunks[0].t0) / FRAME_S)) * FRAME_SAMPLES


def test_first_partial_chunk_is_cut_while_speech_goes_on():
    # the M1 miss (F1): a 3.3 s unbroken utterance used to yield its first chunk only
    # at its end; with the 2 s default it is cut at <= 2 s after onset
    samples = synth([("silence", 1.0), ("speech", 3.3), ("silence", 1.0)])
    chunks = feed_all(Chunker(), samples)
    assert chunks[0].t1 <= 1.0 + 2.0 + FRAME_S
    assert chunks[0].t1 < 1.0 + 3.3                              # before the utterance ends


def test_chunker_drops_a_click():
    samples = synth([("speech", 2 * FRAME_S), ("silence", 1.0)])
    assert feed_all(Chunker(min_speech_s=0.12), samples) == []


def test_chunker_flush():
    ch = Chunker()
    assert ch.flush(0.0) is None
    feed_all(ch, synth([("speech", 0.5)]))
    assert ch.open and ch.start_t == 0.0
    c = ch.flush(0.5)
    assert c is not None and c.t1 == 0.5 and not ch.open


# -- sink ----------------------------------------------------------------------


def test_heard_sink_writes_through_heard_and_returns_its_seq(tmp_path):
    from voice_mode import heard

    sink = HeardSink(tmp_path)
    assert sink.write({"kind": "event", "event": "a", "source": "mic", "device": "airpods"}) == 1
    assert sink.write({"kind": "partial", "text": "hi", "source": "mic", "device": "airpods", "session": None}) == 2
    assert HeardSink(tmp_path).write({"kind": "turn", "text": "hi", "detector": "vad-silence", "source": "mic", "device": "airpods"}) == 3
    lines = read_lines(tmp_path)
    assert [ln["seq"] for ln in lines] == [1, 2, 3]
    assert heard.log_path(directory=tmp_path).exists()
    assert lines[1]["final"] is False and "session" not in lines[1]  # heard drops None
    assert lines[2]["final"] is True and lines[2]["detector"] == "vad-silence"


def test_memory_sink():
    sink = MemorySink()
    assert sink.write({"kind": "event"}) == 1
    assert sink.lines[0]["seq"] == 1 and "ts" in sink.lines[0]


# -- whisper STT (mocked transport; no server) ----------------------------------


def test_whisper_stt_posts_a_wav_to_the_openai_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json={"text": "  hello there "})

    stt = WhisperSTT("http://127.0.0.1:2022/v1/")
    stt._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert stt.transcribe(synth([("speech", 0.3)])) == "hello there"
    assert seen["url"] == "http://127.0.0.1:2022/v1/audio/transcriptions"
    assert b"RIFF" in seen["body"] and b"whisper-1" in seen["body"]


def test_whisper_stt_raises_stt_error_on_http_failure():
    from voice_mode.listen.stt import STTError

    stt = WhisperSTT()
    stt._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(STTError):
        stt.transcribe(synth([("speech", 0.3)]))


# -- the CLI -------------------------------------------------------------------


@pytest.fixture
def cli_fakes(monkeypatch):
    monkeypatch.setattr(cli, "WhisperSTT", lambda *a, **k: type("S", (FakeSTT,), {"close": lambda self: None})())
    monkeypatch.setattr(detector_mod, "default_classifier", lambda: EnergyClassifier(500))


def test_cli_capture_runs_a_file_to_its_end_and_prints_the_result_json(tmp_path, capsys, cli_fakes):
    wav = write_wav(tmp_path / "t.wav", synth([("silence", 0.5), ("speech", 1.5), ("silence", 2.5), ("speech", 1.0)]))
    logs = tmp_path / "logs"
    rc = cli.main(["capture", "--source", f"file:{wav}", "--log-dir", str(logs), "--no-pace", "--tail-silence", "3"])
    out = json.loads(capsys.readouterr().out)
    lines = read_lines(logs)
    assert rc == 0
    assert out["reason"] == "eof" and out["cursor"] == lines[-1]["seq"]
    assert [ln["kind"] for ln in lines].count("turn") == 2  # it did not return on the first


def test_cli_capture_writes_to_voicemode_base_dir_by_default(tmp_path, capsys, cli_fakes):
    wav = write_wav(tmp_path / "t.wav", synth([("speech", 1.0)]))
    assert cli.main(["capture", "--source", f"file:{wav}", "--no-pace"]) == 0
    assert read_lines(tmp_path / "vm" / "logs" / "conversations")[0]["event"] == "listen-started"


def test_cli_capture_ceiling_and_stop_file(tmp_path, capsys, cli_fakes):
    wav = write_wav(tmp_path / "quiet.wav", synth([("silence", 0.5)]))
    args = ["capture", "--source", f"file:{wav}", "--log-dir", str(tmp_path / "l"), "--no-pace", "--tail-silence", "30"]
    assert cli.main(args + ["--ceiling", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "ceiling"
    (tmp_path / "stop").touch()
    assert cli.main(args + ["--stop-file", str(tmp_path / "stop")]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "stop"


def test_cli_bad_source_is_an_error_json(tmp_path, capsys):
    rc = cli.main(["capture", "--source", "file:/no/such.wav"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and out["reason"] == "error"


def test_cli_needs_the_capture_subcommand(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--source", "mic"])
    assert exc.value.code == 2


# -- the mic, through a fake sounddevice at the one seam (no device) ------------


class FakeSD:
    """Stands in for ``sounddevice`` at ``voice_mode.listen.sources._sd``: input only."""

    def __init__(self, *, name="airpods", default_rate=48000, refuse_rates=(), blocks=3):
        self.name, self.default_rate, self.refuse_rates, self.blocks = name, default_rate, set(refuse_rates), blocks
        self.opened: list[dict] = []
        test = self

        class InputStream:
            def __init__(self, **kw):
                if kw["samplerate"] in test.refuse_rates:
                    raise ValueError(f"Invalid sample rate {kw['samplerate']}")
                test.opened.append(kw)
                self.kw = kw

            def start(self):
                n = self.kw["blocksize"]
                for _ in range(test.blocks):
                    self.kw["callback"](np.full((n, 1), 1000, dtype=np.int16), n, None, None)

            def stop(self):
                test.stopped = True

            def close(self):
                pass

        self.InputStream = InputStream
        self.stopped = False

    DEVICES = [
        {"name": "MacBook Pro Microphone", "max_input_channels": 1, "default_samplerate": 48000},
        {"name": "MacBook Pro Speakers", "max_input_channels": 0, "default_samplerate": 48000},
        {"name": "Logitech Webcam C930e", "max_input_channels": 2, "default_samplerate": 32000},
        {"name": "airpods", "max_input_channels": 1, "default_samplerate": 24000},
        {"name": "airpods pro", "max_input_channels": 1, "default_samplerate": 24000},
    ]

    def query_devices(self, device=None, kind=None):
        if device is None and kind is None:
            return self.DEVICES
        if device is None:
            return {"name": self.name, "default_samplerate": self.default_rate, "max_input_channels": 1}
        return self.DEVICES[device]


@pytest.fixture
def fake_sd(monkeypatch):
    from voice_mode.listen import sources

    sd = FakeSD()
    monkeypatch.setattr(sources, "_sd", lambda: sd)
    return sd


def test_mic_source_names_the_device_and_yields_16k_frames(fake_sd):
    from voice_mode.listen import MicSource

    mic = MicSource(stall_s=0.05)
    assert mic.name == "mic" and mic.device == "airpods"
    frames = mic.frames()
    got = [next(frames) for _ in range(3)]
    assert all(f.shape == (FRAME_SAMPLES,) and f.dtype == np.int16 for f in got)
    assert fake_sd.opened[0]["samplerate"] == SAMPLE_RATE and fake_sd.opened[0]["channels"] == 1
    mic.close()
    assert fake_sd.stopped


def test_mic_source_falls_back_to_the_device_rate_and_resamples(fake_sd):
    from voice_mode.listen import MicSource

    fake_sd.refuse_rates = {SAMPLE_RATE}
    mic = MicSource(stall_s=0.05)
    frames = mic.frames()
    got = [next(frames) for _ in range(3)]
    assert fake_sd.opened[0]["samplerate"] == 48000
    assert all(f.shape == (FRAME_SAMPLES,) for f in got)
    mic.close()


def test_a_mic_that_goes_quiet_at_the_driver_is_an_error_not_a_silent_room(fake_sd, tmp_path):
    from voice_mode.listen import MicSource, capture

    fake_sd.blocks = 2  # then nothing, ever
    mic = MicSource(stall_s=0.1)
    result = capture(mic, FakeSTT(), HeardSink(tmp_path), stt_workers=0)
    lines = read_lines(tmp_path)
    assert result.reason == "error" and "delivered no audio" in result.error
    assert lines[0]["source"] == "mic" and lines[0]["device"] == "airpods"


def test_a_mic_that_cannot_open_is_a_source_error(fake_sd):
    from voice_mode.listen import MicSource

    fake_sd.refuse_rates = {SAMPLE_RATE, 48000}
    with pytest.raises(SourceError):
        next(MicSource().frames())


def test_an_unknown_mic_device_is_a_source_error(monkeypatch):
    from voice_mode.listen import sources

    class NoDevice(FakeSD):
        def query_devices(self, device=None, kind=None):
            raise ValueError("PortAudio is gone")

    monkeypatch.setattr(sources, "_sd", lambda: NoDevice())
    with pytest.raises(SourceError, match="PortAudio is gone"):
        open_source("mic")


@pytest.mark.parametrize(
    "want, index, name",
    [
        ("C930e", 2, "Logitech Webcam C930e"),
        ("c930E", 2, "Logitech Webcam C930e"),
        ("macbook", 0, "MacBook Pro Microphone"),  # the speakers have no input channels
        ("airpods", 3, "airpods"),  # an exact name beats the longer substring match
        ("2", 2, "Logitech Webcam C930e"),
        (3, 3, "airpods"),
    ],
)
def test_device_is_an_index_or_a_substring_of_an_input_name(fake_sd, want, index, name):
    from voice_mode.listen import MicSource, resolve_input_device

    assert resolve_input_device(want) == (index, name)
    mic = MicSource(want)
    assert mic.device == name
    next(mic.frames())
    assert fake_sd.opened[0]["device"] == index
    mic.close()


@pytest.mark.parametrize("want, why", [("walkman", "no input device matches"), ("pro", "more than one"), ("1", "no input channels")])
def test_a_device_that_matches_nothing_or_too_much_is_an_error_naming_the_inputs(fake_sd, want, why):
    with pytest.raises(SourceError, match=why):
        open_source("mic", device=want)


def test_default_device_is_the_system_input(fake_sd):
    from voice_mode.listen import resolve_input_device

    assert resolve_input_device(None) == (None, "airpods")


@pytest.mark.parametrize(
    "raw, clean",
    [
        ("(static)", ""),
        ("[BLANK_AUDIO]", ""),
        ("[BEEP] (upbeat music)", ""),
        ("the weather (static) in Sydney", "the weather in Sydney"),
        ("*sighs* okay", "okay"),
        ("Hey, can you check the build?", "Hey, can you check the build?"),
    ],
)
def test_whisper_annotations_are_not_heard_as_words(raw, clean):
    from voice_mode.listen.stt import strip_annotations

    assert strip_annotations(raw) == clean
    stt = WhisperSTT()
    stt._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": raw})))
    assert stt.transcribe(synth([("speech", 0.3)])) == clean


def test_whisper_annotations_can_be_kept():
    stt = WhisperSTT(drop_annotations=False)
    stt._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "(static)"})))
    assert stt.transcribe(synth([("speech", 0.3)])) == "(static)"


def test_whisper_retries_a_refused_connection_once():
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json={"text": "the weather tomorrow in Sydney"})

    stt = WhisperSTT(retry_delay_s=0)
    stt._client = httpx.Client(transport=httpx.MockTransport(flaky))
    assert stt.transcribe(synth([("speech", 0.3)])) == "the weather tomorrow in Sydney"
    assert len(calls) == 2


def test_whisper_gives_up_after_the_retry():
    from voice_mode.listen.stt import STTError

    def down(request):
        raise httpx.ConnectError("Connection refused")

    stt = WhisperSTT(retry_delay_s=0)
    stt._client = httpx.Client(transport=httpx.MockTransport(down))
    with pytest.raises(STTError, match="refused"):
        stt.transcribe(synth([("speech", 0.3)]))
