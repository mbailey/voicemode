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

from voice_mode.tools.impressions.profiles import (
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
        "voice_mode.tools.impressions.profiles.urllib.request.urlopen",
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
        "voice_mode.tools.impressions.profiles.urllib.request.urlopen",
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


def _form_fields(req) -> dict:
    """Parse the simple (non-file) fields out of a multipart request body.

    Returns ``{name: value}`` for every part that carries no filename. The
    file part is skipped; its bytes are binary audio.
    """
    content_type = req.get_header("Content-type")
    boundary = content_type.split("boundary=", 1)[1]
    fields = {}
    for part in req.data.split(f"--{boundary}".encode()):
        head, sep, value = part.partition(b"\r\n\r\n")
        if not sep or b"filename=" in head:
            continue
        disposition = head.strip().decode()
        name = disposition.split('name="', 1)[1].split('"', 1)[0]
        fields[name] = value.removesuffix(b"\r\n").decode()
    return fields


def test_request_asks_for_json_on_every_failover_url(sample_audio, monkeypatch):
    """Every POST carries response_format=json beside model (VM-2346).

    mlx-audio >=0.4.4 defaults an omitted response_format to ndjson, which
    json.loads cannot parse; the request must ask for json explicitly, on
    each URL the failover walk attempts.
    """
    monkeypatch.setattr(
        "voice_mode.config.STT_BASE_URLS",
        ["http://unreachable.invalid:1/v1", "http://localhost:8890/v1"],
    )

    seen: list = []

    def fake_urlopen(req, timeout=60):
        seen.append((req.full_url, _form_fields(req)))
        if req.full_url.startswith("http://unreachable.invalid"):
            raise urllib.error.URLError("Connection refused")
        return _ok_response("Hello world")

    with patch(
        "voice_mode.tools.impressions.profiles.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        assert _transcribe_audio(sample_audio) == "Hello world"

    assert [url for url, _ in seen] == [
        "http://unreachable.invalid:1/v1/audio/transcriptions",
        "http://localhost:8890/v1/audio/transcriptions",
    ]
    for url, fields in seen:
        assert fields == {"model": "whisper-1", "response_format": "json"}, url


def test_whisper_cpp_plain_json_reply_still_transcribes(sample_audio, monkeypatch):
    """whisper.cpp behaviour is unchanged: its plain {"text": ...} reply,
    returned for response_format=json as it is by default, transcribes."""
    monkeypatch.setattr(
        "voice_mode.config.STT_BASE_URLS", ["http://127.0.0.1:2022/v1"]
    )

    response = MagicMock()
    response.read.return_value = b'{"text":" And so my fellow Americans.\\n"}\n'
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)

    with patch(
        "voice_mode.tools.impressions.profiles.urllib.request.urlopen",
        return_value=response,
    ) as urlopen:
        result = _transcribe_audio(sample_audio)

    assert result == "And so my fellow Americans."
    (req,), _ = urlopen.call_args
    assert req.full_url == "http://127.0.0.1:2022/v1/audio/transcriptions"
    assert _form_fields(req)["response_format"] == "json"
