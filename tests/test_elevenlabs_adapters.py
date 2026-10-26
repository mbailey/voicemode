"""Tests for the ElevenLabs TTS and STT adapter modules.

Covers elevenlabs_tts.synthesize / stream and elevenlabs_stt.transcribe
using httpx.MockTransport — no live API calls, mirrors test_cartesia_tts.py.
"""

import json
import os
from unittest.mock import patch

import httpx
import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ELEVENLABS_API_KEY", "test-el-key")
os.environ.setdefault("VOICEMODE_ELEVENLABS_VOICE_ID", "IKne3meq5aSn9XLyUdCD")
os.environ.setdefault("VOICEMODE_ELEVENLABS_MODEL", "eleven_flash_v2_5")
os.environ.setdefault("VOICEMODE_ELEVENLABS_FALLBACK_MODEL", "eleven_multilingual_v2")
os.environ.setdefault("VOICEMODE_ELEVENLABS_STT_MODEL", "scribe_v1")

from voice_mode import elevenlabs_tts, elevenlabs_stt, config  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-el-key")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "IKne3meq5aSn9XLyUdCD")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_flash_v2_5")
    monkeypatch.setattr(config, "ELEVENLABS_FALLBACK_MODEL", "eleven_multilingual_v2")
    monkeypatch.setattr(config, "ELEVENLABS_STT_MODEL", "scribe_v1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_client(handler):
    """Return an httpx.AsyncClient subclass whose transport uses *handler*."""
    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    return FakeClient


# ===========================================================================
# elevenlabs_tts — internal helpers
# ===========================================================================


class TestResolveRequest:
    """_resolve_request validates credentials and voice ID shape."""

    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="ELEVENLABS_API_KEY"):
            elevenlabs_tts._resolve_request(None, None)

    def test_raises_without_voice_id(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="voice ID"):
            elevenlabs_tts._resolve_request(None, None)

    def test_raises_on_non_elevenlabs_voice(self, monkeypatch):
        """Kokoro/OpenAI voice names are rejected with a clear message."""
        monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "af_sky")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="not a valid ElevenLabs voice ID"):
            elevenlabs_tts._resolve_request(None, None)

    def test_returns_both_models_when_different(self):
        api_key, voice, primary, models = elevenlabs_tts._resolve_request(
            "IKne3meq5aSn9XLyUdCD", None
        )
        assert api_key == "test-el-key"
        assert voice == "IKne3meq5aSn9XLyUdCD"
        assert primary == "eleven_flash_v2_5"
        assert models == ["eleven_flash_v2_5", "eleven_multilingual_v2"]

    def test_returns_single_model_when_same(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_FALLBACK_MODEL", "eleven_flash_v2_5")
        _, _, _, models = elevenlabs_tts._resolve_request("IKne3meq5aSn9XLyUdCD", None)
        assert models == ["eleven_flash_v2_5"]

    def test_explicit_voice_overrides_config(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
        _, voice, _, _ = elevenlabs_tts._resolve_request("21m00Tcm4TlvDq8ikWAM", None)
        assert voice == "21m00Tcm4TlvDq8ikWAM"


class TestClampSpeed:
    def test_none_returns_none(self):
        assert elevenlabs_tts._clamp_speed(None) is None

    def test_within_range_unchanged(self):
        assert elevenlabs_tts._clamp_speed(1.0) == 1.0

    def test_below_minimum_clamped(self):
        assert elevenlabs_tts._clamp_speed(0.5) == 0.7

    def test_above_maximum_clamped(self):
        assert elevenlabs_tts._clamp_speed(2.0) == 1.2

    def test_boundary_values_unchanged(self):
        assert elevenlabs_tts._clamp_speed(0.7) == 0.7
        assert elevenlabs_tts._clamp_speed(1.2) == 1.2


class TestMapOutputFormat:
    def test_mp3_maps_to_mp3_44100_128(self):
        assert elevenlabs_tts._map_output_format("mp3") == "mp3_44100_128"

    def test_opus_maps_to_opus_48000_32(self):
        assert elevenlabs_tts._map_output_format("opus") == "opus_48000_32"

    def test_pcm_maps_to_pcm_24000(self):
        assert elevenlabs_tts._map_output_format("pcm") == "pcm_24000"

    def test_none_returns_default(self):
        assert elevenlabs_tts._map_output_format(None) == "mp3_44100_128"

    def test_unknown_format_returns_default(self):
        assert elevenlabs_tts._map_output_format("flac") == "mp3_44100_128"

    def test_case_insensitive(self):
        assert elevenlabs_tts._map_output_format("MP3") == "mp3_44100_128"


# ===========================================================================
# elevenlabs_tts.synthesize
# ===========================================================================


class TestSynthesize:
    """elevenlabs_tts.synthesize — buffered POST to /v1/text-to-speech/{voice}."""

    @pytest.mark.asyncio
    async def test_returns_audio_bytes_on_200(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "IKne3meq5aSn9XLyUdCD" in str(request.url)
            body = json.loads(request.content)
            assert body["model_id"] == "eleven_flash_v2_5"
            assert body["text"] == "hello"
            assert request.headers["xi-api-key"] == "test-el-key"
            return httpx.Response(200, content=b"FAKE_MP3")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_tts.synthesize("hello")

        assert result == b"FAKE_MP3"

    @pytest.mark.asyncio
    async def test_output_format_sent_as_query_param(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["output_format"] == "mp3_44100_128"
            return httpx.Response(200, content=b"OK")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            await elevenlabs_tts.synthesize("hello", output_format="mp3")

    @pytest.mark.asyncio
    async def test_speed_sent_in_voice_settings(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["voice_settings"]["speed"] == 1.0
            return httpx.Response(200, content=b"OK")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            await elevenlabs_tts.synthesize("hello", speed=1.0)

    @pytest.mark.asyncio
    async def test_speed_clamped_before_sending(self):
        seen_speed = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen_speed.append(body["voice_settings"]["speed"])
            return httpx.Response(200, content=b"OK")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            await elevenlabs_tts.synthesize("hello", speed=5.0)

        assert seen_speed == [1.2]

    @pytest.mark.asyncio
    async def test_falls_back_to_fallback_model_on_model_error(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(body["model_id"])
            if body["model_id"] == "eleven_flash_v2_5":
                return httpx.Response(404, text='{"detail":"model not found"}')
            return httpx.Response(200, content=b"FALLBACK")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_tts.synthesize("hello")

        assert result == b"FALLBACK"
        assert calls == ["eleven_flash_v2_5", "eleven_multilingual_v2"]

    @pytest.mark.asyncio
    async def test_no_fallback_on_non_model_error(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(body["model_id"])
            return httpx.Response(401, text="unauthorized")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            with pytest.raises(elevenlabs_tts.ElevenLabsError, match="401"):
                await elevenlabs_tts.synthesize("hello")

        # Should not have retried with fallback model
        assert calls == ["eleven_flash_v2_5"]

    @pytest.mark.asyncio
    async def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="ELEVENLABS_API_KEY"):
            await elevenlabs_tts.synthesize("hello")

    @pytest.mark.asyncio
    async def test_raises_on_invalid_voice_id(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "af_sky")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="not a valid ElevenLabs voice ID"):
            await elevenlabs_tts.synthesize("hello")


# ===========================================================================
# elevenlabs_tts.stream
# ===========================================================================


class TestStream:
    """elevenlabs_tts.stream — chunked HTTP streaming from /v1/text-to-speech/{voice}/stream."""

    @pytest.mark.asyncio
    async def test_yields_chunks_from_streaming_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/stream" in str(request.url)
            assert "IKne3meq5aSn9XLyUdCD" in str(request.url)
            body = json.loads(request.content)
            assert body["model_id"] == "eleven_flash_v2_5"
            assert request.headers["xi-api-key"] == "test-el-key"
            return httpx.Response(200, content=b"\x01\x02\x03\x04\x05\x06")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            chunks = [c async for c in elevenlabs_tts.stream("hello")]

        assert b"".join(chunks) == b"\x01\x02\x03\x04\x05\x06"

    @pytest.mark.asyncio
    async def test_output_format_sent_as_query_param(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["output_format"] == "opus_48000_32"
            return httpx.Response(200, content=b"OK")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            _ = [c async for c in elevenlabs_tts.stream("hello", output_format="opus")]

    @pytest.mark.asyncio
    async def test_falls_back_on_model_error(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(body["model_id"])
            if body["model_id"] == "eleven_flash_v2_5":
                return httpx.Response(400, text='{"detail":"unknown model"}')
            return httpx.Response(200, content=b"FALLBACK_AUDIO")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            chunks = [c async for c in elevenlabs_tts.stream("hello")]

        assert b"".join(chunks) == b"FALLBACK_AUDIO"
        assert calls == ["eleven_flash_v2_5", "eleven_multilingual_v2"]

    @pytest.mark.asyncio
    async def test_raises_on_non_model_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized")

        with patch.object(elevenlabs_tts.httpx, "AsyncClient", _fake_client(handler)):
            with pytest.raises(elevenlabs_tts.ElevenLabsError, match="401"):
                _ = [c async for c in elevenlabs_tts.stream("hello")]

    @pytest.mark.asyncio
    async def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        with pytest.raises(elevenlabs_tts.ElevenLabsError, match="ELEVENLABS_API_KEY"):
            _ = [c async for c in elevenlabs_tts.stream("hello")]


# ===========================================================================
# elevenlabs_stt.transcribe
# ===========================================================================


class TestTranscribe:
    """elevenlabs_stt.transcribe — multipart POST to /v1/speech-to-text."""

    @pytest.mark.asyncio
    async def test_returns_transcript_on_200(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["xi-api-key"] == "test-el-key"
            assert b"scribe_v1" in request.content
            assert b"audio.mp3" in request.content
            return httpx.Response(200, json={"text": "hello world"})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_stt.transcribe(b"FAKE_AUDIO")

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_custom_model_sent_in_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert b"scribe_v2" in request.content
            return httpx.Response(200, json={"text": "hi"})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_stt.transcribe(b"FAKE_AUDIO", model="scribe_v2")

        assert result == "hi"

    @pytest.mark.asyncio
    async def test_language_sent_when_provided(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert b"es" in request.content
            return httpx.Response(200, json={"text": "hola"})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_stt.transcribe(b"FAKE_AUDIO", language="es")

        assert result == "hola"

    @pytest.mark.asyncio
    async def test_auto_language_not_sent(self):
        """language='auto' should not be included in the request body."""
        body_bytes = []

        def handler(request: httpx.Request) -> httpx.Response:
            body_bytes.append(request.content)
            return httpx.Response(200, json={"text": "hello"})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            await elevenlabs_stt.transcribe(b"FAKE_AUDIO", language="auto")

        assert b"language_code" not in body_bytes[0]

    @pytest.mark.asyncio
    async def test_filename_hint_sent_in_multipart(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert b"recording.wav" in request.content
            return httpx.Response(200, json={"text": "ok"})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            await elevenlabs_stt.transcribe(b"FAKE_AUDIO", filename="recording.wav")

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="bad request")

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            with pytest.raises(elevenlabs_stt.ElevenLabsSTTError, match="400"):
                await elevenlabs_stt.transcribe(b"FAKE_AUDIO")

    @pytest.mark.asyncio
    async def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        with pytest.raises(elevenlabs_stt.ElevenLabsSTTError, match="ELEVENLABS_API_KEY"):
            await elevenlabs_stt.transcribe(b"FAKE_AUDIO")

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_empty_text_field(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"text": ""})

        with patch.object(elevenlabs_stt.httpx, "AsyncClient", _fake_client(handler)):
            result = await elevenlabs_stt.transcribe(b"FAKE_AUDIO")

        assert result == ""
