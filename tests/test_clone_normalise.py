"""Tests for the ffmpeg loudnorm normalisation helper in clone_add."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from voice_mode.tools.clone.profiles import _normalise_audio


EXPECTED_FFMPEG_ARGS = [
    "ffmpeg",
    "-y",
    "-i",
    "/tmp/in.wav",
    "-ac",
    "1",
    "-ar",
    "24000",
    "-sample_fmt",
    "s16",
    "-af",
    "loudnorm=I=-16:TP=-1.5:LRA=11",
    "/tmp/out.wav",
]


def test_normalise_invokes_ffmpeg_with_expected_arg_vector():
    src = Path("/tmp/in.wav")
    dest = Path("/tmp/out.wav")
    fake_result = SimpleNamespace(returncode=0, stderr="", stdout="")
    with patch(
        "voice_mode.tools.clone.profiles.subprocess.run",
        return_value=fake_result,
    ) as mock_run:
        _normalise_audio(src, dest)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == EXPECTED_FFMPEG_ARGS
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True


def test_normalise_raises_runtimeerror_on_nonzero_exit_with_stderr():
    src = Path("/tmp/in.wav")
    dest = Path("/tmp/out.wav")
    stderr_payload = "\n".join(f"line {i}" for i in range(30))
    fake_result = SimpleNamespace(returncode=1, stderr=stderr_payload, stdout="")
    with patch(
        "voice_mode.tools.clone.profiles.subprocess.run",
        return_value=fake_result,
    ):
        with pytest.raises(RuntimeError) as exc:
            _normalise_audio(src, dest)
    msg = str(exc.value)
    assert "ffmpeg failed" in msg
    assert "exit 1" in msg
    # Last 20 lines should be present, the first 10 should not.
    assert "line 29" in msg
    assert "line 10" in msg
    assert "line 9" not in msg


def test_normalise_raises_filenotfound_when_ffmpeg_missing():
    src = Path("/tmp/in.wav")
    dest = Path("/tmp/out.wav")
    with patch(
        "voice_mode.tools.clone.profiles.subprocess.run",
        side_effect=FileNotFoundError("No such file: ffmpeg"),
    ):
        with pytest.raises(FileNotFoundError) as exc:
            _normalise_audio(src, dest)
    assert "brew install ffmpeg" in str(exc.value)
    assert "ffmpeg required" in str(exc.value)
