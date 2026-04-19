# MCP SDK Channel Notification Check — 2026-04-19

## Summary

**Python MCP SDK has active open PRs building server-to-client notification infrastructure (v2, unmerged).**
FastMCP has no relevant updates yet (depends on SDK merging first).

## Python MCP SDK (`modelcontextprotocol/python-sdk`)

### Latest Release
- **v1.27.0** (2026-04-02) — no notification/channel features

### Active PR Stack on `main` (v2 development)

A series of open, unmerged PRs specifically building the plumbing for server-to-client communication:

#### PR #2452 — `feat: add Dispatcher Protocol and DirectDispatcher`
- Decouples MCP request handling from JSON-RPC framing
- Introduces `Dispatcher` Protocol with `send_request(method, params)`, `notify(method, params)`, and `run(on_request, on_notify)`
- **Key**: adds `NoBackChannelError(MCPError)` — explicitly for "transports without a server-to-client request channel"
- `DirectDispatcher` provides in-memory peer wiring (test substrate)

#### PR #2458 — `feat: JSONRPCDispatcher` (stacked on #2452)
- Production JSON-RPC implementation of the Dispatcher Protocol
- Handles `notifications/cancelled` and `notifications/progress`
- Request-id correlation, per-request task isolation, cancellation wiring

#### PR #2460 — `feat: PeerMixin, BaseContext, Connection, server Context` (stacked on #2458)
- **`Connection`** (`server/connection.py`) — per-client state with:
  - `send_raw_request` gated on `has_standalone_channel`
  - Convenience notifications: `log`, `send_*_list_changed`, `send_resource_updated`
  - Best-effort `notify` (never raises)
- **`PeerMixin`** — typed methods: `sample`, `elicit_form`, `elicit_url`, `list_roots`, `ping`
- **`TypedServerRequestMixin`** — typed server→client requests with per-spec overloads (`CreateMessageRequest`, `ElicitRequest`, `ListRootsRequest`, `PingRequest`)
- **`Context`** — what `ServerRunner` (next PR) hands to user handlers

#### Next: `ServerRunner` PR (not yet submitted)
- Will wire everything into the usable surface

### Assessment

This is a **major v2 refactoring** specifically designed to enable server-to-client notifications and alternative transports. The `has_standalone_channel` gate and `NoBackChannelError` confirm this is targeting exactly the capability VoiceMode needs. The stack is in active review as of mid-April 2026.

**Status: Not yet merged. Target is v2 release (originally Q1 2026, now slipping).**

## FastMCP (`jlowin/fastmcp`)

- No recent commits related to channel/notification/server-to-client
- Recent work: OAuth hardening, bug fixes, OpenAPI integration
- FastMCP wraps the Python SDK — notification support will follow SDK merge

## Relevance to VoiceMode (VM-970, VM-972)

The Python MCP SDK v2 PR stack directly addresses the capability gap:
- `Connection.notify()` = server can push to client without client request
- `has_standalone_channel` = transport-level flag for whether bidirectional channel exists
- `NoBackChannelError` = explicit error when channel unavailable

**Recommended action**: Monitor PR #2452/#2458/#2460 for merge into `main`. Once `ServerRunner` PR lands and v2 is released, VoiceMode can use `Connection.notify()` / `Context.notify()` to push inbound voice messages to Claude Code.

## References

- PR #2452: https://github.com/modelcontextprotocol/python-sdk/pull/2452
- PR #2458: https://github.com/modelcontextprotocol/python-sdk/pull/2458
- PR #2460: https://github.com/modelcontextprotocol/python-sdk/pull/2460
- Latest release: https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.0
