"""MCP resources for voice discovery.

Exposes two resources:

* ``voice://voices`` — full list of TTS voices the server can produce.
* ``voice://voices/{provider}`` — same envelope, filtered to entries
  whose ``provider`` matches the path segment.

Both return ``application/json``. The body is
``{schema_version, generated_at, voices[]}`` per the locked v1 schema in
the task README. Impressions/clones are local-only and only appear when
the caller is local — see ``_is_local_request``.

Design references: ``design.md`` §11 (privacy), §12 (AC cross-check);
``harness/progress.json`` ``decisions.spike-001`` (mime_type) and
``decisions.spike-002`` (peer-address introspection + hardened predicate).
"""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone
from typing import Any

from fastmcp.server.dependencies import get_http_request

from ..server import mcp
from ..voices import enumerate_voices

_SCHEMA_VERSION = 1
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _is_local_request() -> bool:
    """Should this caller see local-only voices (impressions/clones)?

    Resolution order, hardened per spike-002 review:

    1. ``VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE`` truthy → True.
    2. No active HTTP request (stdio / in-memory transport) → True.
    3. HTTP request with a loopback peer (127/8, ::1, IPv4-mapped
       loopback) → True.
    4. Anything else — None client, empty host, unparseable IP, or a
       public peer — → False (safe default: treat as remote).
    """
    override = os.environ.get("VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE", "")
    if override.strip().lower() in _TRUE_VALUES:
        return True

    try:
        req = get_http_request()
    except RuntimeError:
        return True

    client = req.client
    if client is None or not client.host:
        return False
    try:
        ip = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    # Python < 3.12's IPv6Address.is_loopback does not unwrap IPv4-mapped
    # addresses, so ::ffff:127.0.0.1 reads as non-loopback. Check the mapped
    # IPv4 explicitly for cross-version parity.
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped is not None and mapped.is_loopback


def _now_iso() -> str:
    """ISO 8601 UTC timestamp with the ``Z`` suffix."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


async def _build_response() -> dict[str, Any]:
    voices = await enumerate_voices(include_local_only=_is_local_request())
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "voices": voices,
    }


@mcp.resource("voice://voices", mime_type="application/json")
async def list_voices() -> dict[str, Any]:
    """JSON list of TTS voices the server can produce.

    Envelope: ``{schema_version, generated_at, voices[]}``. Each entry
    has ``id`` (``{provider}:{voice}``), ``voice``, ``name``, ``provider``,
    ``language``, ``gender``, ``preview_url``. Impressions/clones are
    included only when the caller is local.
    """
    return await _build_response()


@mcp.resource("voice://voices/{provider}", mime_type="application/json")
async def list_voices_for_provider(provider: str) -> dict[str, Any]:
    """Same envelope as ``voice://voices``, filtered to one provider.

    Filters ``voices[]`` to entries with ``provider == {provider}``. An
    unknown provider yields an empty ``voices`` list — the envelope is
    well-formed either way.
    """
    body = await _build_response()
    body["voices"] = [v for v in body["voices"] if v.get("provider") == provider]
    return body
