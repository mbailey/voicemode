"""Tests for ``voice_mode/resources/voices.py``.

Covers the privacy filter (``_is_local_request`` — every branch of the
spike-002 hardened spec) and the two resource handlers
(``voice://voices`` and ``voice://voices/{provider}``).

``asyncio_mode = "auto"`` in pyproject means async test functions run
without an explicit decorator.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from voice_mode.resources.voices import (
    _is_local_request,
    list_voices,
    list_voices_for_provider,
)


# ---------- _is_local_request: every branch of the hardened spec -----------


@pytest.fixture
def clean_env(monkeypatch):
    """Drop the override env var so each test sets it deliberately."""
    monkeypatch.delenv("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", raising=False)
    return monkeypatch


def _patch_request(monkeypatch, request_obj):
    """Make ``get_http_request()`` return ``request_obj``."""
    monkeypatch.setattr(
        "voice_mode.resources.voices.get_http_request",
        lambda: request_obj,
    )


def _patch_no_request(monkeypatch):
    """Make ``get_http_request()`` raise — emulating stdio / in-memory."""
    def _raise():
        raise RuntimeError("No active HTTP request found.")
    monkeypatch.setattr("voice_mode.resources.voices.get_http_request", _raise)


def test_stdio_no_http_context_is_local(clean_env):
    _patch_no_request(clean_env)

    assert _is_local_request() is True


def test_http_loopback_ipv4_is_local(clean_env):
    req = MagicMock()
    req.client.host = "127.0.0.1"
    _patch_request(clean_env, req)

    assert _is_local_request() is True


def test_http_loopback_ipv6_is_local(clean_env):
    req = MagicMock()
    req.client.host = "::1"
    _patch_request(clean_env, req)

    assert _is_local_request() is True


def test_http_ipv4_mapped_ipv6_loopback_is_local(clean_env):
    """IPv4-mapped IPv6 loopback (``::ffff:127.0.0.1``) — verified in spike-002."""
    req = MagicMock()
    req.client.host = "::ffff:127.0.0.1"
    _patch_request(clean_env, req)

    assert _is_local_request() is True


def test_http_public_peer_is_remote(clean_env):
    req = MagicMock()
    req.client.host = "8.8.8.8"
    _patch_request(clean_env, req)

    assert _is_local_request() is False


def test_http_lan_peer_is_remote(clean_env):
    req = MagicMock()
    req.client.host = "192.168.1.42"
    _patch_request(clean_env, req)

    assert _is_local_request() is False


def test_env_override_forces_local_over_remote_peer(monkeypatch):
    """``VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE=true`` short-circuits to local."""
    req = MagicMock()
    req.client.host = "8.8.8.8"
    _patch_request(monkeypatch, req)
    monkeypatch.setenv("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", "true")

    assert _is_local_request() is True


@pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE", "  YES  "])
def test_env_override_accepts_truthy_variants(monkeypatch, value):
    _patch_no_request(monkeypatch)
    monkeypatch.setenv("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", value)

    assert _is_local_request() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
def test_env_override_falsy_does_not_force_local(monkeypatch, value):
    """Falsy values fall through to the normal detection path."""
    req = MagicMock()
    req.client.host = "8.8.8.8"
    _patch_request(monkeypatch, req)
    monkeypatch.setenv("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", value)

    assert _is_local_request() is False


def test_none_client_is_remote(clean_env):
    """spike-002 hardening: missing ``request.client`` → safe-default remote."""
    req = MagicMock()
    req.client = None
    _patch_request(clean_env, req)

    assert _is_local_request() is False


def test_empty_host_is_remote_not_crash(clean_env):
    """spike-002 hardening: empty host string must NOT raise (UDS / proxy)."""
    req = MagicMock()
    req.client.host = ""
    _patch_request(clean_env, req)

    assert _is_local_request() is False


def test_unparseable_host_is_remote_not_crash(clean_env):
    """spike-002 hardening: malformed peer host must NOT raise."""
    req = MagicMock()
    req.client.host = "not-an-ip"
    _patch_request(clean_env, req)

    assert _is_local_request() is False


# ---------- voice://voices envelope ---------------------------------------


def _make_voice(provider, voice):
    return {
        "id": f"{provider}:{voice}",
        "voice": voice,
        "name": voice,
        "provider": provider,
        "language": None,
        "gender": None,
        "preview_url": None,
    }


@pytest.fixture
def patched_enum(monkeypatch):
    """Replace ``enumerate_voices`` with a controllable async fake.

    Records the ``include_local_only`` value passed in so tests can
    assert on the privacy decision.
    """
    calls = []
    fake_voices = {
        True: [
            _make_voice("openai", "alloy"),
            _make_voice("kokoro", "af_alpha"),
            _make_voice("mlx-audio", "samantha"),  # impression
        ],
        False: [
            _make_voice("openai", "alloy"),
            _make_voice("kokoro", "af_alpha"),
        ],
    }

    async def fake_enum(*, include_local_only):
        calls.append(include_local_only)
        return list(fake_voices[include_local_only])

    monkeypatch.setattr("voice_mode.resources.voices.enumerate_voices", fake_enum)
    return calls


async def test_list_voices_returns_locked_envelope(patched_enum, clean_env):
    _patch_no_request(clean_env)   # stdio context → local

    body = await list_voices.fn()

    assert body["schema_version"] == 1
    assert isinstance(body["generated_at"], str)
    # generated_at parses as ISO 8601 (use the same Z→+00:00 swap).
    parsed = datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert isinstance(body["voices"], list)
    assert all({"id", "voice", "name", "provider", "language", "gender", "preview_url"} <= v.keys() for v in body["voices"])


async def test_list_voices_stdio_includes_impressions(patched_enum, clean_env):
    _patch_no_request(clean_env)

    body = await list_voices.fn()

    assert patched_enum == [True]   # stdio → include_local_only=True
    assert any(v["provider"] == "mlx-audio" for v in body["voices"])


async def test_list_voices_remote_omits_impressions(patched_enum, clean_env):
    """Non-loopback HTTP peer → enumerator called with include_local_only=False."""
    req = MagicMock()
    req.client.host = "203.0.113.7"
    _patch_request(clean_env, req)

    body = await list_voices.fn()

    assert patched_enum == [False]
    assert all(v["provider"] != "mlx-audio" for v in body["voices"])


async def test_list_voices_loopback_includes_impressions(patched_enum, clean_env):
    req = MagicMock()
    req.client.host = "127.0.0.1"
    _patch_request(clean_env, req)

    body = await list_voices.fn()

    assert patched_enum == [True]
    assert any(v["provider"] == "mlx-audio" for v in body["voices"])


async def test_list_voices_env_override_forces_impressions_over_remote(
    patched_enum, monkeypatch,
):
    req = MagicMock()
    req.client.host = "203.0.113.7"
    _patch_request(monkeypatch, req)
    monkeypatch.setenv("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", "true")

    body = await list_voices.fn()

    assert patched_enum == [True]
    assert any(v["provider"] == "mlx-audio" for v in body["voices"])


async def test_list_voices_response_carries_no_raw_urls(patched_enum, clean_env):
    """AC4: no ``http://`` / ``https://`` substrings anywhere in the body."""
    _patch_no_request(clean_env)

    body = await list_voices.fn()

    import json
    serialized = json.dumps(body)
    assert "http://" not in serialized
    assert "https://" not in serialized


# ---------- voice://voices/{provider} filter ------------------------------


async def test_per_provider_filter_returns_only_matching(patched_enum, clean_env):
    _patch_no_request(clean_env)

    body = await list_voices_for_provider.fn(provider="openai")

    assert body["schema_version"] == 1
    assert all(v["provider"] == "openai" for v in body["voices"])
    assert len(body["voices"]) == 1


async def test_per_provider_filter_empty_for_unknown_provider(patched_enum, clean_env):
    _patch_no_request(clean_env)

    body = await list_voices_for_provider.fn(provider="never-heard-of-it")

    assert body["voices"] == []
    assert body["schema_version"] == 1


async def test_per_provider_filter_respects_privacy(patched_enum, clean_env):
    """Asking ``/mlx-audio`` from a remote peer returns no impressions."""
    req = MagicMock()
    req.client.host = "203.0.113.7"
    _patch_request(clean_env, req)

    body = await list_voices_for_provider.fn(provider="mlx-audio")

    # patched_enum returns no mlx-audio voices when include_local_only=False,
    # so the per-provider filter yields nothing.
    assert patched_enum == [False]
    assert body["voices"] == []


async def test_per_provider_envelope_matches_unfiltered(patched_enum, clean_env):
    """Per-provider response carries the same envelope keys as the unfiltered one."""
    _patch_no_request(clean_env)

    full = await list_voices.fn()
    one = await list_voices_for_provider.fn(provider="kokoro")

    assert set(full.keys()) == set(one.keys())
    assert full["schema_version"] == one["schema_version"]


# ---------- registration sanity check -------------------------------------


def test_resources_register_with_expected_uris():
    """Both resources are loaded into the FastMCP instance with mime_type=json."""
    # The resource objects expose .uri / .mime_type attributes once registered.
    assert str(list_voices.uri) == "voice://voices"
    assert list_voices.mime_type == "application/json"
    assert "voice://voices/{provider}" in str(list_voices_for_provider.uri_template)
    assert list_voices_for_provider.mime_type == "application/json"
