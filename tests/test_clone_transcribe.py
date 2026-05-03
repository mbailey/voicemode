"""Regression tests for the STT_BASE_URLS failover walk in clone _transcribe_audio.

These tests guard the behaviour added in VM-1182: rather than POSTing to a
single hardcoded ``http://localhost:2022/v1/audio/transcriptions``, the
clone profile transcription helper now walks
``voice_mode.config.STT_BASE_URLS`` in order and returns the first
successful response.
"""

import json
import urllib.error
import wave
from unittest.mock import MagicMock, patch

import pytest

from voice_mode.tools.clone.profiles import (
    _normalise_transcription_url,
    _transcribe_audio,
)


@pytest.fixture
def sample_audio(tmp_path):
    """Create a minimal valid WAV file the helper can read."""
    audio_path = tmp_path / "clip.wav"
    with wave.open(str(audio_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    return audio_path


def _ok_response(text: str) -> MagicMock:
    """Build a mock urlopen context manager returning {'text': text}."""
    response = MagicMock()
    response.read.return_value = json.dumps({"text": text}).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_failover_success_uses_second_url(sample_audio, monkeypatch):
    """First URL raises URLError; second returns 200 -- result comes from the second."""
    monkeypatch.setattr(
        "voice_mode.config.STT_BASE_URLS",
        ["http://unreachable.invalid:1/v1", "http://good.example/v1"],
    )

    seen_urls: list[str] = []

    def fake_urlopen(req, timeout=60):
        url = req.full_url
        seen_urls.append(url)
        if url.startswith("http://unreachable.invalid"):
            raise urllib.error.URLError("Connection refused")
        return _ok_response("Hello world")

    with patch(
        "voice_mode.tools.clone.profiles.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = _transcribe_audio(sample_audio)

    assert result == "Hello world"
    # Walked both URLs, in order, and the success was the normalised second URL.
    assert seen_urls == [
        "http://unreachable.invalid:1/v1/audio/transcriptions",
        "http://good.example/v1/audio/transcriptions",
    ]


def test_all_urls_fail_lists_each_in_error(sample_audio, monkeypatch):
    """Every URL raises URLError --> ConnectionError naming both endpoints."""
    monkeypatch.setattr(
        "voice_mode.config.STT_BASE_URLS",
        ["http://first.invalid/v1", "http://second.invalid/v1"],
    )

    with patch(
        "voice_mode.tools.clone.profiles.urllib.request.urlopen",
        side_effect=urllib.error.URLError("nope"),
    ):
        with pytest.raises(ConnectionError) as exc_info:
            _transcribe_audio(sample_audio)

    message = str(exc_info.value)
    assert "http://first.invalid/v1/audio/transcriptions" in message
    assert "http://second.invalid/v1/audio/transcriptions" in message


@pytest.mark.parametrize(
    "base_url",
    [
        "http://host:8890/v1",
        "http://host:8890",
        "http://host:8890/v1/",
    ],
)
def test_url_normalisation(base_url):
    """Each accepted base form normalises to a single canonical endpoint."""
    assert (
        _normalise_transcription_url(base_url)
        == "http://host:8890/v1/audio/transcriptions"
    )
