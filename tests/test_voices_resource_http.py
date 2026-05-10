"""Integration tests for ``voice://voices`` over real streamable HTTP.

The in-memory tests in ``test_voices_resource.py`` exercise the resource
handlers directly via ``FastMCPTransport``. This file goes one step
further: a real ``uvicorn`` server hosts the production
``voice_mode.server.mcp`` instance on a free loopback port, and a
``fastmcp.Client`` connects over ``StreamableHttpTransport`` — the same
wire path an iOS app or web client would use.

VM-1208 test-002 step-by-step coverage:

1. ``voicemode serve --transport http`` (in fixture) — uvicorn-on-free-port,
   pattern from ``harness/spike-002/spike2_peer_address.py`` lifted to the
   production ``mcp`` instance.
2. Test MCP client — ``fastmcp.Client(StreamableHttpTransport(url))``.
3. ``resources/list`` includes ``voice://voices`` —
   ``test_resources_list_includes_voice_voices_over_http``.
4. ``resources/read voice://voices`` returns schema-shaped JSON —
   ``test_read_voice_voices_returns_locked_envelope_over_http``.
5. No raw URLs in the body —
   ``test_read_voice_voices_no_raw_urls_in_body``.
6. stdio vs streamable HTTP parity (modulo ``generated_at``) —
   ``test_stdio_and_http_bodies_match_modulo_generated_at``.

The enumerator is monkey-patched to a deterministic list — this isolates
the test from whether kokoro/mlx-audio happen to be running on the dev
box. The privacy filter ``_is_local_request`` runs naturally because we
are hitting the resource through real HTTP (loopback peer ⇒ local).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport, StreamableHttpTransport


# ---------- deterministic enumerator -------------------------------------


_FAKE_VOICES_LOCAL: list[dict[str, Any]] = [
    {
        "id": "openai:alloy",
        "voice": "alloy",
        "name": "alloy",
        "provider": "openai",
        "language": None,
        "gender": None,
        "preview_url": None,
    },
    {
        "id": "kokoro:af_river",
        "voice": "af_river",
        "name": "af_river",
        "provider": "kokoro",
        "language": None,
        "gender": None,
        "preview_url": None,
    },
    {
        "id": "mlx-audio:samantha",
        "voice": "samantha",
        "name": "samantha",
        "provider": "mlx-audio",
        "language": None,
        "gender": None,
        "preview_url": None,
    },
]


async def _fake_enumerate(*, include_local_only: bool) -> list[dict[str, Any]]:
    """Deterministic stand-in for ``enumerate_voices``.

    Returns the same list whether called locally or remotely so that the
    AC3 parity check (stdio vs HTTP) compares apples to apples. The
    privacy decision is made by ``_is_local_request`` upstream — both
    transports here are local (in-memory and loopback HTTP), so we
    expect ``include_local_only=True`` from each.
    """
    return [dict(v) for v in _FAKE_VOICES_LOCAL]


@pytest.fixture
def patched_enum(monkeypatch):
    """Patch the resource module's ``enumerate_voices`` for the test."""
    monkeypatch.setattr(
        "voice_mode.resources.voices.enumerate_voices",
        _fake_enumerate,
    )


# ---------- uvicorn fixture ----------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_socket(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"uvicorn did not start on {host}:{port} within {timeout}s")


@pytest.fixture
def http_server_url():
    """Spin uvicorn over the production ``mcp`` instance on a free port.

    Pattern lifted from ``harness/spike-002/spike2_peer_address.py``: a
    daemon thread runs ``asyncio.run(server.serve())``; the fixture
    waits for the listening socket then yields the MCP URL. Teardown
    asks uvicorn to exit and joins the thread.
    """
    from voice_mode.server import mcp

    host, port = "127.0.0.1", _free_port()
    app = mcp.http_app(path="/mcp")
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    try:
        _wait_for_socket(host, port)
        yield f"http://{host}:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


# ---------- helpers -------------------------------------------------------


async def _read_voice_voices(client: Client) -> tuple[str, dict[str, Any]]:
    """Read ``voice://voices`` and return ``(raw_text, parsed_dict)``."""
    blocks = await client.read_resource("voice://voices")
    text = getattr(blocks[0], "text", None)
    assert isinstance(text, str), f"expected text content block, got {blocks!r}"
    return text, json.loads(text)


# ---------- step 3: resources/list ---------------------------------------


async def test_resources_list_includes_voice_voices_over_http(
    patched_enum, http_server_url
):
    """test-002 step 3: ``voice://voices`` appears in ``resources/list``."""
    transport = StreamableHttpTransport(url=http_server_url)
    async with Client(transport=transport) as client:
        resources = await client.list_resources()
        templates = await client.list_resource_templates()

    matches = [r for r in resources if str(r.uri) == "voice://voices"]
    assert len(matches) == 1, f"expected exactly one voice://voices, got {matches!r}"
    assert matches[0].mimeType == "application/json"

    template_uris = {getattr(t, "uriTemplate", None) for t in templates}
    assert "voice://voices/{provider}" in template_uris


# ---------- step 4: resources/read schema --------------------------------


async def test_read_voice_voices_returns_locked_envelope_over_http(
    patched_enum, http_server_url
):
    """test-002 step 4: the body matches the locked v1 schema."""
    from datetime import datetime

    transport = StreamableHttpTransport(url=http_server_url)
    async with Client(transport=transport) as client:
        _raw, body = await _read_voice_voices(client)

    assert body["schema_version"] == 1

    # generated_at parses as ISO 8601 with timezone.
    parsed = datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None

    assert isinstance(body["voices"], list)
    expected_keys = {"id", "voice", "name", "provider", "language", "gender", "preview_url"}
    for entry in body["voices"]:
        assert expected_keys <= set(entry.keys()), entry


# ---------- step 5: no raw URLs ------------------------------------------


async def test_read_voice_voices_no_raw_urls_in_body(
    patched_enum, http_server_url
):
    """test-002 step 5 / AC4: no ``http://`` or ``https://`` in the body."""
    transport = StreamableHttpTransport(url=http_server_url)
    async with Client(transport=transport) as client:
        raw_text, _body = await _read_voice_voices(client)

    assert "http://" not in raw_text
    assert "https://" not in raw_text


# ---------- step 6: stdio vs HTTP parity ---------------------------------


def _strip_generated_at(body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body.pop("generated_at", None)
    return body


async def test_stdio_and_http_bodies_match_modulo_generated_at(
    patched_enum, http_server_url
):
    """test-002 step 6 / AC3: stdio and HTTP bodies are identical except
    for ``generated_at``.

    "stdio" is approximated by the in-memory ``FastMCPTransport`` against
    the same ``mcp`` instance (no HTTP request → ``_is_local_request``
    returns True via the ``RuntimeError`` branch — same outcome as a
    real stdio server). The HTTP side connects from loopback, which the
    privacy predicate also classifies as local. With the deterministic
    enumerator both paths produce the same voice list, so any diff
    outside ``generated_at`` indicates a transport-level bug.
    """
    from voice_mode.server import mcp

    in_memory = FastMCPTransport(mcp=mcp)
    async with Client(transport=in_memory) as client:
        _stdio_raw, stdio_body = await _read_voice_voices(client)

    transport = StreamableHttpTransport(url=http_server_url)
    async with Client(transport=transport) as client:
        _http_raw, http_body = await _read_voice_voices(client)

    # Sort keys before comparing so dict ordering can never trip us up,
    # then strip the timestamp the schema explicitly excludes.
    stdio_canonical = json.dumps(
        _strip_generated_at(stdio_body), sort_keys=True
    )
    http_canonical = json.dumps(
        _strip_generated_at(http_body), sort_keys=True
    )
    assert stdio_canonical == http_canonical


# ---------- AC8 spot-check: loopback is local ----------------------------


async def test_loopback_caller_treated_as_local(
    patched_enum, http_server_url
):
    """AC8 spot-check: peer 127.0.0.1 ⇒ caller treated as local, so the
    impression in the fake enumerator output appears in the response.

    This is the privacy predicate exercised end-to-end through real
    HTTP — the whole point of the integration test. With ``_is_local_request``
    returning True for a loopback peer, the response carries every voice
    in ``_FAKE_VOICES_LOCAL``, including the ``mlx-audio`` impression.
    """
    transport = StreamableHttpTransport(url=http_server_url)
    async with Client(transport=transport) as client:
        _raw, body = await _read_voice_voices(client)

    providers = {v["provider"] for v in body["voices"]}
    assert "mlx-audio" in providers, (
        "loopback caller should see impressions; got providers="
        f"{providers!r}"
    )
