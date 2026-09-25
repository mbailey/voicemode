"""The mouth keeps what it says (audio.py): a WAV and a JSON note per line.

No sound and no server: the ``null`` device and a fake tone backend.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from voice_mode import mouth
from voice_mode.mouth import audio, backends, player
from voice_mode.mouth.__main__ import main


class Tone:
    name, sample_rate = "tone", 24000

    def stream(self, text, voice, speed):
        for _ in range(6):
            yield np.full(1200, 0.5, dtype=np.float32)


@pytest.fixture
def box(tmp_path, monkeypatch):
    d, logs = tmp_path / "mouth", tmp_path / "logs"
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(logs))
    monkeypatch.setenv("VOICEMODE_AGENT", "pip")
    monkeypatch.setenv("VOICEMODE_SESSION_ID", "s-test")
    monkeypatch.delenv("VOICEMODE_MOUTH_AUDIO_DIR", raising=False)
    monkeypatch.delenv("VOICEMODE_MOUTH_KEEP_AUDIO", raising=False)
    monkeypatch.setitem(audio._last_prune, "t", 0.0)
    return SimpleNamespace(d=d, logs=logs, audio=d / "audio")


@pytest.fixture
def tone(monkeypatch):
    monkeypatch.setattr(backends, "resolve", lambda b, v: (Tone(), v))


def lines(logs: Path) -> list[dict]:
    return [json.loads(x) for f in sorted(logs.glob("heard_*.jsonl")) for x in f.read_text().splitlines()]


def speak(d: Path, text: str, **kw) -> dict:
    kw.setdefault("device", "null")
    item = mouth.say(text, spawn=False, **kw)
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": 0.3}, daemon=True)
    t.start()
    t.join(10)
    return item


def said(logs: Path, utt: str) -> dict:
    return next(r for r in lines(logs) if r["kind"] == "said" and r["utt"] == utt)


ITEM = {"utt": "u1", "voice": "pip", "speed": 0.88, "agent": "pip", "session": "s",
        "text": "hello there", "requested_ts": "2026-09-26T04:00:00+10:00"}


# -- the unit ------------------------------------------------------------------

def test_pcm16_clips_and_joins_blocks():
    b = audio.pcm16([np.array([0.0, 2.0], dtype=np.float32), None,
                     np.array([-2.0, 0.5], dtype=np.float32)])
    assert np.frombuffer(b, dtype="<i2").tolist() == [0, 32767, -32767, 16384]
    assert audio.pcm16([]) == b""


def test_keep_writes_a_wav_and_its_note_under_the_day(tmp_path):
    now = dt.datetime(2026, 9, 26, 4, 20).timestamp()
    wav = audio.keep(ITEM, [np.full(2400, 0.25, dtype=np.float32)] * 3, 24000, "clone",
                     root=tmp_path, now=now)
    assert wav == tmp_path / "2026-09-26" / "u1.wav"
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 7200)
    note = json.loads(wav.with_suffix(".json").read_text())
    assert note["voice"] == "pip" and note["backend"] == "clone" and note["text"] == "hello there"
    assert note["dur_s"] == 0.3 and note["sample_rate"] == 24000 and note["wav"] == str(wav)
    assert not list(wav.parent.glob(".*.tmp"))  # written whole, then renamed


@pytest.mark.parametrize("item,backend,env", [
    ({**ITEM, "file": "/x.wav"}, "file", None),   # mouth play: the file already exists
    (ITEM, "silence", None),                     # tests and dry runs
    (ITEM, "clone", "0"),                        # switched off
    (ITEM, "clone", "off"),
])
def test_keep_skips_files_silence_and_off(tmp_path, monkeypatch, item, backend, env):
    if env is not None:
        monkeypatch.setenv("VOICEMODE_MOUTH_KEEP_AUDIO", env)
    assert audio.keep(item, [np.ones(10, dtype=np.float32)], 24000, backend, root=tmp_path) is None
    assert not list(tmp_path.rglob("*.wav"))


def test_keep_never_raises(tmp_path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    assert audio.keep(ITEM, [np.ones(10, dtype=np.float32)], 24000, "clone", root=blocker) is None
    assert audio.keep({"text": "no utt"}, [np.ones(10, dtype=np.float32)], 24000, "clone",
                      root=tmp_path) is None


def test_prune_drops_old_days_only_and_leaves_other_names(tmp_path):
    root = tmp_path / "audio"
    now = dt.datetime(2026, 9, 26, 12, 0).timestamp()
    for name in ("2026-09-10", "2026-09-18", "2026-09-19", "2026-09-26", "pinned"):
        (root / name).mkdir(parents=True)
    gone = audio.prune(root, 7, now=now)
    assert sorted(p.name for p in gone) == ["2026-09-10", "2026-09-18"]
    assert sorted(p.name for p in root.iterdir()) == ["2026-09-19", "2026-09-26", "pinned"]
    assert audio.prune(root, 0, now=now) == []  # 0 never prunes


def test_prune_runs_at_most_once_an_hour(tmp_path, monkeypatch):
    monkeypatch.setitem(audio._last_prune, "t", 0.0)
    now = dt.datetime(2026, 9, 26, 12, 0).timestamp()
    (tmp_path / "2026-09-01").mkdir()
    assert audio.maybe_prune(tmp_path, now=now)
    (tmp_path / "2026-09-02").mkdir()
    assert audio.maybe_prune(tmp_path, now=now + 60) == []
    assert audio.maybe_prune(tmp_path, now=now + 3601)


def test_kept_lists_newest_first_by_voice_and_last(tmp_path):
    t = dt.datetime(2026, 9, 25, 23, 0).timestamp()
    for i, (voice, dt_s) in enumerate([("pip", 0), ("am_santa", 60), ("pip", 3 * 3600)]):
        audio.keep({**ITEM, "utt": f"u{i}", "voice": voice}, [np.ones(10, dtype=np.float32)],
                   24000, "clone", root=tmp_path, now=t + dt_s)
    assert [m["utt"] for m in audio.kept(tmp_path)] == ["u2", "u1", "u0"]
    assert [m["utt"] for m in audio.kept(tmp_path, voice="pip")] == ["u2", "u0"]
    assert [m["utt"] for m in audio.kept(tmp_path, last=2)] == ["u2", "u1"]
    (tmp_path / "2026-09-25" / "u0.wav").unlink()  # a note without its WAV is not listed
    assert [m["utt"] for m in audio.kept(tmp_path, voice="pip")] == ["u2"]


# -- through the player ----------------------------------------------------------

def test_a_spoken_line_is_kept_and_said_names_it(box, tone):
    item = speak(box.d, "keep me", voice="pip")
    rec = said(box.logs, item["utt"])
    assert rec["reason"] == "done"
    wav = Path(rec["audio"])
    assert wav.parent.parent == box.audio and wav.name == f"{item['utt']}.wav"
    with wave.open(str(wav)) as w:
        assert w.getnframes() == 7200 and w.getframerate() == 24000
    note = json.loads(wav.with_suffix(".json").read_text())
    assert note["text"] == "keep me" and note["voice"] == "pip" and note["backend"] == "tone"


def test_the_audio_dir_env_moves_it(box, tone, tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_AUDIO_DIR", str(tmp_path / "elsewhere"))
    item = speak(box.d, "over there")
    assert Path(said(box.logs, item["utt"])["audio"]).is_relative_to(tmp_path / "elsewhere")


def test_silence_and_off_keep_nothing_and_said_has_no_audio(box, monkeypatch):
    a = speak(box.d, "quiet", backend="silence")  # the real resolve: the silence backend
    monkeypatch.setattr(backends, "resolve", lambda b, v: (Tone(), v))
    monkeypatch.setenv("VOICEMODE_MOUTH_KEEP_AUDIO", "0")
    b = speak(box.d, "off")
    for item in (a, b):
        assert "audio" not in said(box.logs, item["utt"])
    assert not list(box.d.rglob("*.wav"))


def test_mouth_audio_prints_json_lines(box, tone, capsys):
    item = speak(box.d, "list me", voice="pip")
    capsys.readouterr()
    assert main(["audio", "--voice", "pip", "--last", "5"]) == 0
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [m["utt"] for m in out] == [item["utt"]]
    assert main(["audio", "--voice", "nobody"]) == 0
    assert capsys.readouterr().out == ""
