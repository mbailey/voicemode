"""Native stdio <-> Streamable-HTTP MCP bridge (VM-1314).

The VM-1314 prototype bridged the plugin's stdio entry to a remote
``voicemode serve`` with ``npx -y mcp-remote``. That pulls in a Node/npx
runtime dependency and fetches the bridge over the network at launch -- not
acceptable for production (see VM-1314 README, "Hard requirements" #1).

This module replaces that with a first-party bridge built on ``fastmcp``,
which is already a hard dependency of voicemode.  ``FastMCP.as_proxy()``
constructs a proxy server whose backend is an MCP *client* to the remote
Streamable-HTTP endpoint.  Running that proxy over stdio yields exactly the
stdio<->HTTP bridge we need, with no Node, no ``npx``, and no launch-time
network fetch of a bridge.

Used by :mod:`voice_mode.mcp_launcher` when ``VOICEMODE_MCP_URL`` is set, and
exposed as the hidden ``voicemode mcp-bridge URL`` CLI subcommand for testing.
"""
from __future__ import annotations


def build_proxy(url: str, token: str | None = None):
    """Build (but do not run) the stdio<->HTTP proxy server.

    Split out from :func:`run_bridge` so tests can assert wiring (transport
    URL, Bearer auth) without standing up a real server / event loop.

    Args:
        url: Full Streamable-HTTP endpoint URL of the remote ``voicemode
            serve`` (includes the ``/mcp`` path, and ``/mcp/<secret>`` when a
            URL secret is configured server-side).
        token: Optional Bearer token. When set, it is sent as
            ``Authorization: Bearer <token>`` on every request to the remote
            (mirrors ``VOICEMODE_SERVE_TOKEN`` on the serve side). fastmcp's
            ``StreamableHttpTransport`` treats a plain ``str`` auth value as a
            Bearer credential.
    """
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.server import create_proxy

    transport = StreamableHttpTransport(url, auth=token if token else None)
    client = Client(transport)
    # One proxied server, surfaced to Claude Code as the single stdio
    # "voicemode" entry -> one mcp__voicemode__* namespace, unchanged from the
    # local path's point of view.
    return create_proxy(client, name="voicemode")


def run_bridge(url: str, token: str | None = None) -> None:
    """Run the native stdio<->Streamable-HTTP bridge (blocks until stdin EOF).

    The proxy owns connection lifecycle: it lazily connects the backend
    client on first use and tears it down with the session, so a clean
    stdin EOF / SIGINT / SIGTERM from Claude Code unwinds the HTTP client
    without leaving orphaned children (there are none -- this is in-process,
    unlike the npx prototype).
    """
    proxy = build_proxy(url, token)
    proxy.run(transport="stdio", show_banner=False)
