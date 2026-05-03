"""Tests for the 3-15s reference-clip length gate in clone_add."""

import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.tools.clone.profiles import (
    TRIM_HINT,
    _probe_duration_seconds,
    _validate_clip_length,
    clone_add,
)


def _write_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


@pytest.fixture
def tmp_voicemode(tmp_path, monkeypatch):
    voices_json = tmp_path / "voices.json"
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    monkeypatch.setattr("voice_mode.tools.clone.profiles.VOICES_JSON", voices_json)
    monkeypatch.setattr("voice_mode.tools.clone.profiles.VOICES_DIR", voices_dir)
    return {"voices_json": voices_json, "voices_dir": voices_dir}


def test_validate_rejects_short_clip(tmp_path):
    short = _write_wav(tmp_path / "short.wav", 1.0)
    with pytest.raises(ValueError) as exc:
        _validate_clip_length(short)
    msg = str(exc.value)
    assert "1.0s" in msg
    assert "3-15s" in msg
    assert "ffmpeg -i" in msg


def test_validate_rejects_long_clip(tmp_path):
    long = _write_wav(tmp_path / "long.wav", 60.0)
    with pytest.raises(ValueError) as exc:
        _validate_clip_length(long)
    msg = str(exc.value)
    assert "60.0s" in msg
    assert "3-15s" in msg


def test_validate_accepts_in_window(tmp_path):
    ok = _write_wav(tmp_path / "ok.wav", 7.0)
    duration = _validate_clip_length(ok)
    assert 6.9 <= duration <= 7.1


def test_validate_accepts_boundary_3s(tmp_path):
    boundary = _write_wav(tmp_path / "three.wav", 3.0)
    assert _validate_clip_length(boundary) == pytest.approx(3.0, abs=0.05)


def test_validate_accepts_boundary_15s(tmp_path):
    boundary = _write_wav(tmp_path / "fifteen.wav", 15.0)
    assert _validate_clip_length(boundary) == pytest.approx(15.0, abs=0.05)


def test_probe_falls_back_to_wave_when_ffprobe_missing(tmp_path):
    wav = _write_wav(tmp_path / "wave.wav", 5.0)
    with patch(
        "voice_mode.tools.clone.profiles.subprocess.run",
        side_effect=FileNotFoundError("ffprobe not found"),
    ):
        duration = _probe_duration_seconds(wav)
    assert duration == pytest.approx(5.0, abs=0.05)


def test_probe_non_wav_without_ffprobe_raises(tmp_path):
    mp3 = tmp_path / "x.mp3"
    mp3.write_bytes(b"\x00" * 100)
    with patch(
        "voice_mode.tools.clone.profiles.subprocess.run",
        side_effect=FileNotFoundError("ffprobe not found"),
    ):
        with pytest.raises(RuntimeError) as exc:
            _probe_duration_seconds(mp3)
    assert "ffmpeg/ffprobe required" in str(exc.value)


@pytest.mark.asyncio
async def test_clone_add_rejects_short_clip(tmp_voicemode, tmp_path):
    short = _write_wav(tmp_path / "short.wav", 1.0)
    result = await clone_add("testfoo", str(short))
    assert result["success"] is False
    assert "1.0s" in result["error"]
    assert "3-15s" in result["error"]
    assert TRIM_HINT in result["error"]


@pytest.mark.asyncio
async def test_clone_add_rejects_long_clip(tmp_voicemode, tmp_path):
    long = _write_wav(tmp_path / "long.wav", 60.0)
    result = await clone_add("testfoo", str(long))
    assert result["success"] is False
    assert "60.0s" in result["error"]
    assert "3-15s" in result["error"]


@pytest.mark.asyncio
async def test_clone_add_passes_gate_for_7s_clip(tmp_voicemode, tmp_path):
    ok = _write_wav(tmp_path / "ok.wav", 7.0)
    with patch(
        "voice_mode.tools.clone.profiles._transcribe_audio",
        return_value="hello world",
    ):
        result = await clone_add("testfoo", str(ok))
    assert result["success"] is True
    assert result["name"] == "testfoo"
