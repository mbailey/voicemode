"""Tests for the Cartesia TTS provider."""

import base64
import json
import os
from unittest.mock import patch

import httpx
import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("CARTESIA_API_KEY", "test-cartesia-key")
os.environ.setdefault("VOICEMODE_CARTESIA_VOICE_ID", "voice-abc")
os.environ.setdefault("VOICEMODE_CARTESIA_MODEL", "sonic-3")
os.environ.setdefault("VOICEMODE_CARTESIA_FALLBACK_MODEL", "sonic-2")

from voice_mode import cartesia_tts  # noqa: E402
from voice_mode import config  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(config, "CARTESIA_API_KEY", "test-cartesia-key")
    monkeypatch.setattr(config, "CARTESIA_VOICE_ID", "voice-abc")
    monkeypatch.setattr(config, "CARTESIA_MODEL", "sonic-3")
    monkeypatch.setattr(config, "CARTESIA_FALLBACK_MODEL", "sonic-2")


def _sse_lines(payloads):
    """Render a list of dicts as SSE ``data: ...`` lines."""
    for payload in payloads:
        yield f"data: {json.dumps(payload)}"


@pytest.mark.asyncio
async def test_synthesize_returns_bytes_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model_id"] == "sonic-3"
        assert body["voice"]["id"] == "voice-abc"
        assert body["output_format"]["container"] == "wav"
        return httpx.Response(200, content=b"FAKE_WAV")

    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch.object(cartesia_tts.httpx, "AsyncClient", FakeClient):
        result = await cartesia_tts.synthesize("hello")

    assert result == b"FAKE_WAV"


@pytest.mark.asyncio
async def test_synthesize_falls_back_on_model_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model_id"])
        if body["model_id"] == "sonic-3":
            return httpx.Response(404, text='{"error":"model not found"}')
        return httpx.Response(200, content=b"OK")

    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch.object(cartesia_tts.httpx, "AsyncClient", FakeClient):
        result = await cartesia_tts.synthesize("hello")

    assert result == b"OK"
    assert calls == ["sonic-3", "sonic-2"]


@pytest.mark.asyncio
async def test_synthesize_raises_on_non_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch.object(cartesia_tts.httpx, "AsyncClient", FakeClient):
        with pytest.raises(cartesia_tts.CartesiaError, match="401"):
            await cartesia_tts.synthesize("hello")


@pytest.mark.asyncio
async def test_synthesize_requires_api_key(monkeypatch):
    monkeypatch.setattr(config, "CARTESIA_API_KEY", "")
    with pytest.raises(cartesia_tts.CartesiaError, match="CARTESIA_API_KEY"):
        await cartesia_tts.synthesize("hello")


@pytest.mark.asyncio
async def test_synthesize_requires_voice_id(monkeypatch):
    monkeypatch.setattr(config, "CARTESIA_VOICE_ID", "")
    with pytest.raises(cartesia_tts.CartesiaError, match="VOICEMODE_CARTESIA_VOICE_ID"):
        await cartesia_tts.synthesize("hello")


@pytest.mark.asyncio
async def test_stream_yields_decoded_chunks():
    chunk_a = base64.b64encode(b"\x01\x02\x03\x04").decode()
    chunk_b = base64.b64encode(b"\x05\x06").decode()

    sse_body = "\n".join(
        list(
            _sse_lines(
                [
                    {"data": chunk_a, "done": False},
                    {"data": chunk_b, "done": False},
                    {"done": True},
                ]
            )
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["output_format"]["container"] == "raw"
        return httpx.Response(
            200,
            content=sse_body.encode(),
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch.object(cartesia_tts.httpx, "AsyncClient", FakeClient):
        chunks = [c async for c in cartesia_tts.stream("hello")]

    assert chunks == [b"\x01\x02\x03\x04", b"\x05\x06"]


@pytest.mark.asyncio
async def test_stream_falls_back_on_model_error():
    chunk = base64.b64encode(b"OK").decode()
    sse_ok = "\n".join(
        list(_sse_lines([{"data": chunk, "done": False}, {"done": True}]))
    )

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model_id"])
        if body["model_id"] == "sonic-3":
            return httpx.Response(400, text='{"error":"unknown model"}')
        return httpx.Response(
            200,
            content=sse_ok.encode(),
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch.object(cartesia_tts.httpx, "AsyncClient", FakeClient):
        chunks = [c async for c in cartesia_tts.stream("hello")]

    assert chunks == [b"OK"]
    assert calls == ["sonic-3", "sonic-2"]
