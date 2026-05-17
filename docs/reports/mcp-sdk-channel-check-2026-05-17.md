# MCP SDK Channel/Notification Check — 2026-05-17

**Relevance to VoiceMode:** VM-970, VM-972 — server-initiated voice channel notifications

## Summary

Significant WIP refactor underway in the Python MCP SDK to properly support server-to-client channels. **Not yet merged or released**, but the architecture is explicitly designed for this use case. FastMCP has no related changes.

---

## Python MCP SDK (modelcontextprotocol/python-sdk)

### Active Draft PR Stack — "V2 Server-Side Refactor"

A stack of 5 draft PRs by @maxisbey implements `Transport → Dispatcher → ServerRunner → Server` architecture specifically to decouple MCP request handling from JSON-RPC framing and enable flexible server-to-client communication:

| PR | Title | Status |
|----|-------|--------|
| [#2452](https://github.com/modelcontextprotocol/python-sdk/pull/2452) | feat: add Dispatcher Protocol and DirectDispatcher | Draft |
| [#2458](https://github.com/modelcontextprotocol/python-sdk/pull/2458) | feat: JSONRPCDispatcher | Draft |
| [#2460](https://github.com/modelcontextprotocol/python-sdk/pull/2460) | feat: PeerMixin, BaseContext, Connection, server Context | Draft |
| [#2491](https://github.com/modelcontextprotocol/python-sdk/pull/2491) | feat: ServerRunner — per-connection orchestrator | Draft |
| [#2562](https://github.com/modelcontextprotocol/python-sdk/pull/2562) | [v2] Server registry + per-connection state | Draft (WIP) |

### Key Features Relevant to VoiceMode

From PR #2452 (`Dispatcher Protocol`):
- `Outbound` protocol: `send_request(method, params) -> dict` + `notify(method, params)` — the minimal interface for both sending requests and fire-and-forget notifications
- `NoBackChannelError(MCPError)` — explicit error for transports that don't support server-to-client requests (stateless HTTP, etc.)
- `DirectDispatcher` — in-memory implementation enabling in-process server-to-client communication without a transport

From PR #2460 (`Connection`):
- `Connection.has_standalone_channel` — boolean property indicating whether the current transport supports server-initiated requests
- `Connection.notify()` — best-effort notification send (never raises); wraps the underlying dispatcher
- Convenience notification methods: `send_resource_updated()`, `send_tools_list_changed()`, `send_resources_list_changed()`, `send_prompts_list_changed()`
- `Context` object now exposes `connection` so handlers can send back-channel notifications

### Design Doc

Full architecture: https://gist.github.com/maxisbey/1e14e741d774acf52b80e69db292c5d7

### What This Means for VoiceMode

Once merged and released, this refactor would enable VoiceMode to:
1. Check `connection.has_standalone_channel` to know if a notification channel is available
2. Call `connection.notify(method, params)` to push voice messages/events to the client without a client request
3. Use `NoBackChannelError` to gracefully handle transports that don't support it (e.g. stateless HTTP)

### Other Notable Issues

- [#2207](https://github.com/modelcontextprotocol/python-sdk/issues/2207) — `fix: pass related_request_id in Context.report_progress()` (open) — progress notification routing fix
- [#2570](https://github.com/modelcontextprotocol/python-sdk/issues/2570) — Distributed `EventStore` (Redis/Postgres) for SSE stream resumability (feature request, not merged)
- [#1827](https://github.com/modelcontextprotocol/python-sdk/pull/1827) — Previously merged: `fix: raise clear error for server-to-client requests in stateless mode` — confirms stateless HTTP still cannot do server-to-client

### Latest Release: v1.27.1 (May 8, 2026)

No notification/channel features in recent releases (v1.27.0, v1.27.1). The v2 refactor has not landed yet.

---

## FastMCP (jlowin/fastmcp)

### Latest Release: v3.3.1 (May 15, 2026)

No relevant changes. Recent releases focused on:
- `fastmcp-slim` lightweight client-only package
- OAuth improvements (AzureB2C, consent guards)
- OTEL instrumentation
- Bug fixes

FastMCP depends on the Python MCP SDK, so server-to-client channel support here will follow SDK adoption.

---

## Conclusion

| Library | Status |
|---------|--------|
| Python MCP SDK | Active WIP — 5 draft PRs, not merged |
| FastMCP | No changes — will follow SDK |

**Action:** Monitor the v2 draft PR stack. The critical merge to watch for is PR #2452 (Dispatcher Protocol) as the foundation — once it merges, the rest of the stack can follow quickly. No released SDK version yet supports server-initiated notifications beyond progress reporting.

**Check again:** In 1–2 weeks, or when any of the 5 draft PRs changes state.
