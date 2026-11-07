"""mouth: say returns at once, one player, saying/said on the heard log, stop, device-bound.

No sound and no server: the ``silence`` backend and the ``null`` device,
paced in real time so a stop cuts as it would live.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_mode import heard, mouth
from voice_mode.mouth import output, player


@pytest.fixture
def box(tmp_path, monkeypatch):
    d, logs = tmp_path / "mouth", tmp_path / "logs"
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(logs))
    monkeypatch.setenv("VOICEMODE_AGENT", "pip")
    monkeypatch.setenv("VOICEMODE_SESSION_ID", "s-test")
    return SimpleNamespace(d=d, logs=logs)


def lines(logs: Path) -> list[dict]:
    return [json.loads(x) for f in sorted(logs.glob("heard_*.jsonl")) for x in f.read_text().splitlines()]


def run_player(d: Path, idle: float = 0.3) -> threading.Thread:
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": idle}, daemon=True)
    t.start()
    return t


def say(text, **kw):
    kw.setdefault("device", "null")
    kw.setdefault("backend", "silence")
    return mouth.say(text, spawn=False, **kw)


# -- heard: the two new kinds ------------------------------------------------

def test_saying_and_said_are_kinds_with_final_like_partial_and_turn(tmp_path):
    a = heard.saying("hello", utt="u1", directory=tmp_path)
    b = heard.said(utt="u1", played_s=0.4, reason="done", directory=tmp_path)
    assert (a["kind"], a["final"], a["source"]) == ("saying", False, "mouth")
    assert (b["kind"], b["final"]) == ("said", True)
    assert b["seq"] == a["seq"] + 1


def test_saying_needs_text_and_both_need_an_utt(tmp_path):
    with pytest.raises(ValueError):
        heard.append("saying", utt="u", directory=tmp_path)
    with pytest.raises(ValueError):
        heard.append("said", directory=tmp_path)


def test_collapse_shows_another_sessions_said_and_hides_saying_and_its_own(tmp_path):
    heard.saying("hi there", utt="u1", session="cora-s", agent="cora", directory=tmp_path)
    heard.said(utt="u1", session="cora-s", agent="cora", text_played_est="hi there",
               played_s=0.5, reason="done", directory=tmp_path)
    heard.said(utt="u2", session="me", agent="pip", text_played_est="mine",
               played_s=0.5, reason="done", directory=tmp_path)
    recs, _ = heard._scan(heard.log_path(directory=tmp_path))
    shown = [i.text for i in heard.collapse(recs, session="me") if i.text]
    assert len(shown) == 1 and shown[0].startswith("[said cora mouth") and shown[0].endswith("hi there")


def test_format_record_renders_both():
    assert "utt u1" in heard.format_record({"seq": 1, "kind": "saying", "text": "x", "utt": "u1"})
    out = heard.format_record({"seq": 2, "kind": "said", "text_played_est": "x", "utt": "u1",
                               "reason": "stop", "played_s": 0.4, "dur_s": 2.0})
    assert "stop 0.4/2.0s" in out


# -- the mouth ---------------------------------------------------------------

def test_say_returns_at_once_and_the_player_writes_saying_then_said(box):
    t0 = time.monotonic()
    item = say("Hello Mike.")  # 11 chars: ~0.7 s of audio
    assert time.monotonic() - t0 < 0.2
    run_player(box.d).join(5)
    got = lines(box.logs)
    assert [r["kind"] for r in got] == ["saying", "said"]
    saying, said = got
    for k in ("utt", "text", "voice", "backend", "device", "requested_ts", "gen_s", "agent", "session"):
        assert k in saying, k
    assert saying["utt"] == said["utt"] == item["utt"]
    assert (said["reason"], said["cut"], said["text_played_est"]) == ("done", False, "Hello Mike.")
    assert said["played_s"] == pytest.approx(said["dur_s"], abs=0.01)
    assert said["played_s"] == pytest.approx(11 / 15, abs=0.06)


def test_one_at_a_time_oldest_first(box):
    a, b = say("first one"), say("second one")
    run_player(box.d).join(8)
    order = [(r["kind"], r["utt"]) for r in lines(box.logs)]
    assert order == [("saying", a["utt"]), ("said", a["utt"]), ("saying", b["utt"]), ("said", b["utt"])]


def test_stop_cuts_within_a_block_and_flushes_the_queue(box):
    long = say("word " * 20)          # ~6.7 s
    queued = say("never heard")
    th = run_player(box.d)
    time.sleep(0.5)
    mouth.stop()
    th.join(5)
    got = lines(box.logs)
    said = {r["utt"]: r for r in got if r["kind"] == "said"}
    assert said[long["utt"]]["reason"] == "stop" and said[long["utt"]]["cut"] is True
    assert 0.3 < said[long["utt"]]["cut_at_s"] < 0.75
    est = said[long["utt"]]["text_played_est"]  # ~0.5 s at 15 chars/s: about one word
    assert est.startswith("word") and len(est) < 15
    assert said[long["utt"]]["dur_s"] == pytest.approx(100 / 15, abs=0.06)  # synthesis ran ahead
    assert said[queued["utt"]]["played_s"] == 0.0 and said[queued["utt"]]["reason"] == "stop"
    assert not [r for r in got if r["kind"] == "saying" and r["utt"] == queued["utt"]]


def test_stop_current_keeps_the_queue_and_reason_passes_through(box):
    long, nxt = say("word " * 20), say("next")
    th = run_player(box.d)
    time.sleep(0.4)
    mouth.stop("barge-in", flush=False)
    th.join(5)
    said = {r["utt"]: r for r in lines(box.logs) if r["kind"] == "said"}
    assert said[long["utt"]]["reason"] == "barge-in"
    assert said[nxt["utt"]]["reason"] == "done"


def test_a_stop_never_touches_a_later_say(box):
    mouth.stop()
    time.sleep(0.01)
    item = say("after the stop")
    run_player(box.d).join(5)
    said = [r for r in lines(box.logs) if r["kind"] == "said"]
    assert said[0]["utt"] == item["utt"] and said[0]["reason"] == "done"


def test_an_absent_device_refuses_and_never_falls_back(box, monkeypatch):
    def absent(name, sr):
        raise output.DeviceAbsent(f"output device {name!r} is not present")
    monkeypatch.setattr(output, "open_output", absent)
    item = say("hello", device="airpods")
    run_player(box.d).join(5)
    got = lines(box.logs)
    assert [r["kind"] for r in got] == ["said"]
    assert (got[0]["reason"], got[0]["played_s"], got[0]["utt"]) == ("device-absent", 0.0, item["utt"])


def test_wait_returns_the_said_record(box):
    run_player(box.d, idle=1.0)
    rec = say("short", wait=True, timeout=5)
    assert rec["kind"] == "said" and rec["reason"] == "done"


def test_no_device_is_an_error_not_a_default(box, monkeypatch):
    monkeypatch.delenv("VOICEMODE_MOUTH_DEVICE", raising=False)
    with pytest.raises(ValueError, match="no device"):
        mouth.say("hi", backend="silence", spawn=False)


# -- device names: exact, never a substring ------------------------------------

class FakeSd:
    default = SimpleNamespace(device=(0, 1))

    def _terminate(self):
        pass

    def _initialize(self):
        pass

    def query_devices(self, i=None):
        devs = [{"name": "MacBook Pro Microphone", "max_output_channels": 0},
                {"name": "MacBook Pro Speakers", "max_output_channels": 2},
                {"name": "Speakers + AirPods", "max_output_channels": 2}]
        return devs if i is None else devs[i]


def test_airpods_never_matches_the_speakers_plus_airpods_aggregate(monkeypatch):
    monkeypatch.setattr(output, "_sd", lambda: FakeSd())
    with pytest.raises(output.DeviceAbsent, match="not present"):
        output.resolve("airpods")
    assert output.resolve("speakers + airpods") == (2, "Speakers + AirPods")
    assert output.resolve("default") == (None, "MacBook Pro Speakers")


def test_text_at_cuts_back_to_a_word():
    assert player.text_at("hello there world", 0.5) == "hello"
    assert player.text_at("hello there", 1.0) == "hello there"
    assert player.text_at("hello there", 0.0) == ""


# -- a device that stops taking audio mid-play (Cora's review, 20:16) ---------

class PullingSd(FakeSd):
    """A fake PortAudio whose stream pulls in real time, until ``stall`` is set."""

    def __init__(self):
        self.stall = threading.Event()
        self.streams = []

    def OutputStream(self, *, device, samplerate, channels, dtype, callback):
        import numpy as np

        fake = self

        class S:
            latency = 0.01

            def __init__(s):
                s.run = True
                s.channels = channels
                s.peak = np.zeros(channels)
                fake.streams.append(s)

            def start(s):
                def loop():
                    buf = np.zeros((1200, channels), dtype="float32")
                    while s.run:
                        if not fake.stall.is_set():
                            callback(buf, 1200, None, None)
                            s.peak = np.maximum(s.peak, np.abs(buf).max(axis=0))
                        time.sleep(1200 / samplerate)
                threading.Thread(target=loop, daemon=True).start()

            def abort(s):
                s.run = False

            def close(s):
                s.run = False

        return S()


@pytest.fixture
def fake_device(monkeypatch):
    sd = PullingSd()
    monkeypatch.setattr(output, "_sd", lambda: sd)
    monkeypatch.setattr(output.DeviceOut, "lost_after_s", 0.3)
    return sd


def test_a_healthy_device_counts_what_it_pulled(box, fake_device):
    item = say("Hello Mike.", device="MacBook Pro Speakers")
    run_player(box.d).join(5)
    said = [r for r in lines(box.logs) if r["kind"] == "said"][0]
    assert (said["utt"], said["reason"], said["device"]) == (item["utt"], "done", "MacBook Pro Speakers")
    assert said["played_s"] == pytest.approx(said["dur_s"], abs=0.06)


def test_a_device_that_stops_pulling_is_lost_not_a_hang(box, fake_device):
    lost = say("word " * 20, device="MacBook Pro Speakers")
    after = say("next one", device="null")
    th = run_player(box.d)
    time.sleep(0.4)
    fake_device.stall.set()          # the AirPods go into the case
    th.join(5)
    assert not th.is_alive()
    said = {r["utt"]: r for r in lines(box.logs) if r["kind"] == "said"}
    assert said[lost["utt"]]["reason"] == "device-lost" and said[lost["utt"]]["cut"] is True
    assert 0.2 < said[lost["utt"]]["played_s"] < 0.7
    assert said[after["utt"]]["reason"] == "done"  # the queue did not stall


def test_one_bad_utterance_never_stalls_the_queue(box, monkeypatch):
    real = player.play_one
    calls = []

    def flaky(item, d, *a):
        calls.append(item["utt"])
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(item, d, *a)
    monkeypatch.setattr(player, "play_one", flaky)
    a, b = say("first"), say("second")
    run_player(box.d).join(5)
    said = {r["utt"]: r for r in lines(box.logs) if r["kind"] == "said"}
    assert said[a["utt"]]["reason"] == "error" and "boom" in said[a["utt"]]["detail"]
    assert said[b["utt"]]["reason"] == "done"


# -- prefetch: the next line is synthesised while this one plays (Cora, 20:43) --

def test_the_next_line_is_ready_when_this_one_ends(box, monkeypatch):
    from voice_mode.mouth import backends
    monkeypatch.setattr(backends.Silence, "__init__",
                        lambda self, chars_per_s=15.0, gen_s=0.3: (setattr(self, "chars_per_s", chars_per_s),
                                                                  setattr(self, "gen_s", gen_s))[0])
    a, b = say("first line here"), say("second line")   # each takes 0.3 s to "synthesise"
    run_player(box.d).join(8)
    got = lines(box.logs)
    said_a = next(r for r in got if r["kind"] == "said" and r["utt"] == a["utt"])
    saying_b = next(r for r in got if r["kind"] == "saying" and r["utt"] == b["utt"])
    saying_a = next(r for r in got if r["kind"] == "saying" and r["utt"] == a["utt"])
    from datetime import datetime
    gap = (datetime.fromisoformat(saying_b["ts"]) - datetime.fromisoformat(said_a["ts"])).total_seconds()
    assert gap < 0.1, gap                      # was gen_s (0.3 s) of dead air
    assert saying_b.get("prefetched") is True and "prefetched" not in saying_a
    assert saying_b["gen_s"] == pytest.approx(0.3, abs=0.05)


def test_a_stop_cancels_the_prefetched_line_too(box):
    long, queued = say("word " * 20), say("prefetched but never heard")
    th = run_player(box.d)
    time.sleep(0.5)
    mouth.stop()
    th.join(5)
    got = lines(box.logs)
    assert not [r for r in got if r["kind"] == "saying" and r["utt"] == queued["utt"]]
    said = {r["utt"]: r for r in got if r["kind"] == "said"}
    assert said[queued["utt"]]["reason"] == "stop" and said[queued["utt"]]["played_s"] == 0.0


# -- one ear: --pan / --channel (Mike, voice 20:43) ---------------------------

class Tone:
    name, sample_rate = "tone", 24000

    def stream(self, text, voice, speed):
        import numpy as np
        for _ in range(6):
            yield np.full(1200, 0.5, dtype=np.float32)


@pytest.fixture
def tone(monkeypatch):
    from voice_mode.mouth import backends
    monkeypatch.setattr(backends, "resolve", lambda b, v: (Tone(), v))


@pytest.mark.parametrize("pan,left,right", [(-1.0, 0.5, 0.0), (1.0, 0.0, 0.5), (0.0, 0.3536, 0.3536)])
def test_pan_puts_the_voice_in_one_ear(box, fake_device, tone, pan, left, right):
    say("hi", device="MacBook Pro Speakers", pan=pan)
    run_player(box.d).join(5)
    s = fake_device.streams[-1]
    assert s.channels == 2
    assert s.peak[0] == pytest.approx(left, abs=1e-3) and s.peak[1] == pytest.approx(right, abs=1e-3)
    saying = next(r for r in lines(box.logs) if r["kind"] == "saying")
    assert saying["pan"] == pan


def test_no_pan_is_mono_as_before(box, fake_device, tone):
    say("hi", device="MacBook Pro Speakers")
    run_player(box.d).join(5)
    assert fake_device.streams[-1].channels == 1
    assert "pan" not in next(r for r in lines(box.logs) if r["kind"] == "saying")


def test_channel_names_and_the_env_default(monkeypatch):
    from voice_mode.mouth import pan_value
    assert (pan_value("left"), pan_value("right"), pan_value("both")) == (-1.0, 1.0, None)
    monkeypatch.setenv("VOICEMODE_MOUTH_PAN", "right")
    assert pan_value(None) == 1.0 and pan_value("both") is None  # 'both' overrides the env
    with pytest.raises(ValueError):
        pan_value(1.5)


def test_a_term_leaves_no_stale_pid(tmp_path):
    import os, signal, subprocess, sys
    d = tmp_path / "mouth"
    env = {**os.environ, "VOICEMODE_MOUTH_DIR": str(d), "PYTHONPATH": os.pathsep.join(sys.path)}
    p = subprocess.Popen([sys.executable, "-m", "voice_mode.mouth", "serve", "--idle", "30"], env=env)
    for _ in range(100):
        if (d / "player.pid").exists():
            break
        time.sleep(0.05)
    assert (d / "player.pid").read_text() == str(p.pid)
    p.send_signal(signal.SIGTERM)
    assert p.wait(5) == 0
    assert not (d / "player.pid").exists()


# -- underruns: synthesis slower than real time (21:05-21:08, measured) ---------

class Slow:
    """Half real time: a 50 ms block every 100 ms."""
    name, sample_rate = "slow", 24000

    def __init__(self, blocks=10):
        self.n = blocks

    def stream(self, text, voice, speed):
        import numpy as np
        for _ in range(self.n):
            time.sleep(0.1)
            yield np.full(1200, 0.5, dtype=np.float32)


def test_a_fast_line_has_no_underrun(box):
    say("Hello Mike.")
    run_player(box.d).join(5)
    said = next(r for r in lines(box.logs) if r["kind"] == "said")
    assert said["underrun_s"] == 0 and said["underruns"] == 0


def test_a_slow_synthesis_is_logged_as_underrun_on_null(box, monkeypatch):
    from voice_mode.mouth import backends
    monkeypatch.setattr(backends, "resolve", lambda b, v: (Slow(), v))
    say("slow")
    run_player(box.d).join(5)
    said = next(r for r in lines(box.logs) if r["kind"] == "said")
    assert said["played_s"] == pytest.approx(0.5, abs=0.01)
    assert 0.3 < said["underrun_s"] < 0.7 and said["underruns"] >= 5


def _slow_on_device(box, monkeypatch, blocks=20):
    from voice_mode.mouth import backends
    monkeypatch.setattr(backends, "resolve", lambda b, v: (Slow(blocks), v))
    say("slow", device="MacBook Pro Speakers")
    run_player(box.d).join(10)
    return next(r for r in lines(box.logs) if r["kind"] == "said")


def test_a_slow_synthesis_is_logged_as_underrun_on_a_device(box, fake_device, monkeypatch):
    said = _slow_on_device(box, monkeypatch)
    assert said["reason"] == "done" and said["underrun_s"] > 0.5 and said["underruns"] >= 5


def test_rebuffer_turns_many_stutters_into_few_pauses(box, fake_device, monkeypatch, tmp_path):
    plain = _slow_on_device(box, monkeypatch)
    monkeypatch.setenv("VOICEMODE_MOUTH_REBUFFER_S", "0.3")
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(tmp_path / "logs2"))
    from voice_mode.mouth import backends
    say("slow again", device="MacBook Pro Speakers")
    run_player(box.d).join(10)
    held = next(r for r in lines(tmp_path / "logs2") if r["kind"] == "said")
    assert held["reason"] == "done"
    assert held["underruns"] < plain["underruns"] / 2, (held["underruns"], plain["underruns"])


# -- amend, retract, --next, --now (Mike, voice 21:21-21:25) -------------------

def _said(logs):
    return {r["utt"]: r for r in lines(logs) if r["kind"] == "said"}


def test_next_jumps_the_queue(box):
    a, b = say("aaa"), say("bbb")
    c = say("ccc", priority="next")
    run_player(box.d).join(8)
    order = [r["utt"] for r in lines(box.logs) if r["kind"] == "saying"]
    assert order == [c["utt"], a["utt"], b["utt"]]


def test_now_interrupts_only_the_line_playing(box):
    a, b = say("word " * 20), say("queued behind")
    th = run_player(box.d)
    time.sleep(0.4)
    c = say("urgent", priority="now")
    th.join(8)
    said = _said(box.logs)
    assert said[a["utt"]]["reason"] == "interrupted" and said[a["utt"]]["cut"] is True
    assert said[c["utt"]]["reason"] == "done" and said[b["utt"]]["reason"] == "done"
    order = [r["utt"] for r in lines(box.logs) if r["kind"] == "saying"]
    assert order == [a["utt"], c["utt"], b["utt"]]


def test_amend_rewrites_a_queued_line_even_if_prefetched(box):
    a, b = say("word " * 10), say("the old words")
    th = run_player(box.d)
    time.sleep(0.3)                       # b is prefetched by now (silence synthesises at once)
    mouth.amend(b["utt"], "the new words")
    th.join(8)
    saying_b = next(r for r in lines(box.logs) if r["kind"] == "saying" and r["utt"] == b["utt"])
    assert saying_b["text"] == "the new words"
    assert _said(box.logs)[b["utt"]]["text_played_est"] == "the new words"


def test_amend_refuses_a_line_already_playing(box):
    a = say("word " * 20)
    th = run_player(box.d)
    time.sleep(0.3)
    with pytest.raises(ValueError, match="already playing"):
        mouth.amend(a["utt"], "too late")
    mouth.stop()
    th.join(5)


def test_retract_a_queued_line_and_a_playing_one(box):
    a, b, c = say("word " * 20), say("never mind"), say("after")
    th = run_player(box.d)
    time.sleep(0.3)
    mouth.retract(b["utt"])               # queued: dropped, closed with a said
    time.sleep(0.2)
    mouth.retract(a["utt"])               # playing: cut
    th.join(8)
    said = _said(box.logs)
    assert said[b["utt"]]["reason"] == "retracted" and said[b["utt"]]["played_s"] == 0.0
    assert said[a["utt"]]["reason"] == "retracted" and said[a["utt"]]["cut"] is True
    assert said[c["utt"]]["reason"] == "done"
    assert not [r for r in lines(box.logs) if r["kind"] == "saying" and r["utt"] == b["utt"]]


def test_amend_or_retract_an_unknown_line_is_an_error(box):
    with pytest.raises(ValueError):
        mouth.amend("nope", "x")
    with pytest.raises(ValueError):
        mouth.retract("nope")


# -- sounds and ducking (Mike, voice 21:21-21:25) --------------------------------

def _tone_wav(path, seconds=1.0, rate=24000):
    import wave
    import numpy as np
    x = (0.3 * np.sin(2 * np.pi * 440 * np.arange(int(seconds * rate)) / rate) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(x.tobytes())
    return path


needs_ffmpeg = pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="no ffmpeg")


@needs_ffmpeg
def test_play_a_section_of_a_file(box, tmp_path):
    wav = _tone_wav(tmp_path / "tone.wav", seconds=1.0)
    item = mouth.play(str(wav), start=0.25, end=0.75, device="null", spawn=False)
    run_player(box.d).join(5)
    got = lines(box.logs)
    saying = next(r for r in got if r["kind"] == "saying")
    said = next(r for r in got if r["kind"] == "said")
    assert saying["text"] == "[sound tone.wav 0.25-0.75s]" and saying["file"] == str(wav)
    assert (said["utt"], said["reason"], said["backend"]) == (item["utt"], "done", "file")
    assert said["dur_s"] == pytest.approx(0.5, abs=0.03)


@needs_ffmpeg
def test_a_sound_is_cut_by_stop_like_a_line(box, tmp_path):
    wav = _tone_wav(tmp_path / "long.wav", seconds=3.0)
    mouth.play(str(wav), device="null", spawn=False)
    th = run_player(box.d)
    time.sleep(0.5)
    mouth.stop()
    th.join(5)
    said = next(r for r in lines(box.logs) if r["kind"] == "said")
    assert said["reason"] == "stop" and 0.3 < said["played_s"] < 0.8


def test_play_refuses_a_missing_file(box):
    with pytest.raises(ValueError, match="no such file"):
        mouth.play("/nope/missing.wav", device="null", spawn=False)


def test_ducking_lowers_the_dj_once_per_run_and_restores_after(box, monkeypatch):
    import voice_mode.dj as dj
    calls = []

    class FakeDJ:
        vol = 70

        def volume(self, level=None):
            if level is not None:
                FakeDJ.vol = level
                calls.append(level)
            return FakeDJ.vol

    monkeypatch.setattr(dj, "DJController", FakeDJ)
    monkeypatch.setenv("VOICEMODE_MOUTH_DUCK", "20")
    say("one"), say("two")
    run_player(box.d, idle=0.5).join(5)
    assert calls == [20, 70]              # down once for both lines, back up once


def test_no_duck_setting_means_the_dj_is_never_touched(box, monkeypatch):
    import voice_mode.dj as dj

    class Boom:
        def __init__(self):
            raise AssertionError("touched the DJ")

    monkeypatch.setattr(dj, "DJController", Boom)
    monkeypatch.delenv("VOICEMODE_MOUTH_DUCK", raising=False)
    say("quiet")
    run_player(box.d).join(5)
    assert next(r for r in lines(box.logs) if r["kind"] == "said")["reason"] == "done"
