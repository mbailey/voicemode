"""whisper.cpp backend temp WAV handling (VM-2484, CodeQL py/insecure-temporary-file).

``tempfile.mktemp`` only chose a name, leaving a window for another process to
create that path first. The backend now uses ``tempfile.mkstemp``, which creates
the file itself, and must still remove it on every exit path.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from voice_mode.tools.transcription import backends


class _Response:
    status_code = 200
    text = ""

    def json(self):
        return {"text": "hello", "language": "en", "segments": []}


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _Response()


@pytest.fixture
def mp3(tmp_path):
    path = tmp_path / "clip.mp3"
    path.write_bytes(b"not really mp3")
    return path


@pytest.fixture
def isolated_tmp(tmp_path, monkeypatch):
    """Point tempfile at a private dir so leaks are countable."""
    tdir = tmp_path / "tmp"
    tdir.mkdir()
    monkeypatch.setattr(backends.tempfile, "tempdir", str(tdir))
    return tdir


def _fake_ffmpeg(seen):
    def run(cmd, check, capture_output):
        out = Path(cmd[-1])
        # mkstemp made the file before ffmpeg ran, private to this user.
        seen["existed"] = out.exists()
        seen["mode"] = stat.S_IMODE(os.stat(out).st_mode)
        seen["cmd"] = cmd
        out.write_bytes(b"RIFF....WAVE")
        return subprocess.CompletedProcess(cmd, 0)

    return run


async def test_temp_wav_is_created_securely_and_removed(mp3, isolated_tmp, monkeypatch):
    seen = {}
    monkeypatch.setattr(backends.subprocess, "run", _fake_ffmpeg(seen))
    monkeypatch.setattr(backends.httpx, "AsyncClient", _Client)

    result = await backends.transcribe_with_whisper_cpp(mp3)

    assert result["success"] is True
    assert seen["existed"] is True
    assert seen["mode"] == 0o600
    assert "-y" in seen["cmd"], "ffmpeg must overwrite the pre-created temp file"
    assert Path(seen["cmd"][-1]).parent == isolated_tmp
    assert list(isolated_tmp.iterdir()) == []


async def test_temp_wav_removed_when_ffmpeg_fails(mp3, isolated_tmp, monkeypatch):
    def run(cmd, check, capture_output):
        raise subprocess.CalledProcessError(1, cmd, stderr=b"bad input")

    monkeypatch.setattr(backends.subprocess, "run", run)

    result = await backends.transcribe_with_whisper_cpp(mp3)

    assert result["success"] is False
    assert "bad input" in result["error"]
    assert list(isolated_tmp.iterdir()) == []


async def test_temp_wav_removed_when_ffmpeg_missing(mp3, isolated_tmp, monkeypatch):
    def run(cmd, check, capture_output):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(backends.subprocess, "run", run)

    with pytest.raises(FileNotFoundError):
        await backends.transcribe_with_whisper_cpp(mp3)
    assert list(isolated_tmp.iterdir()) == []


async def test_wav_input_is_not_copied_or_deleted(tmp_path, isolated_tmp, monkeypatch):
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF....WAVE")

    def run(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("ffmpeg should not run for .wav input")

    monkeypatch.setattr(backends.subprocess, "run", run)
    monkeypatch.setattr(backends.httpx, "AsyncClient", _Client)

    result = await backends.transcribe_with_whisper_cpp(wav)

    assert result["success"] is True
    assert wav.exists()
    assert list(isolated_tmp.iterdir()) == []
