# MCP SDK Channel/Notification Check — 2026-05-05

Monitoring check for server-to-client notification support in the Python MCP SDK and FastMCP.
Relevant to VoiceMode tasks VM-970 and VM-972.

## Summary

**Python MCP SDK**: Found potentially relevant open PRs adding server-initiated notification infrastructure.
**FastMCP (PrefectHQ)**: No relevant changes found.
**MCP Specification**: No new channel/notification spec additions.

---

## Python MCP SDK (`modelcontextprotocol/python-sdk`)

### PR #2460 — `feat: PeerMixin, BaseContext, Connection, server Context` (OPEN, 2026-04-16)

**URL**: https://github.com/modelcontextprotocol/python-sdk/pull/2460

This is the most relevant finding. It introduces a `Connection` class and related abstractions that enhance server-initiated notification capabilities:

**New files:**
- `src/mcp/server/connection.py` — `Connection` class with best-effort server→client notification delivery
- `src/mcp/shared/context.py` — `BaseContext` wrapping `DispatchContext`
- `src/mcp/server/_typed_request.py` — Typed request handling

**Key notification methods on `Connection`:**
- `notify(method, params)` — Best-effort delivery; drops and debug-logs if no channel or stream is broken
- `log(level, data, logger)` — Sends `notifications/message` log entries
- `send_tool_list_changed()` — Server-initiated tool list change notification
- `send_prompt_list_changed()` — Server-initiated prompt list change notification
- `send_resource_list_changed()` — Server-initiated resource list change notification
- `send_resource_updated(uri)` — Server-initiated resource update notification

**`PeerMixin`** adds typed methods for server→client requests: `sample()`, `elicit_form()`, `list_roots()`, `ping()`.

**Status**: OPEN — not yet merged into main. This is foundational infrastructure, not a full "channel" system.

### PR #2452 — `feat: add Dispatcher Protocol and DirectDispatcher` (OPEN, 2026-04-16)

**URL**: https://github.com/modelcontextprotocol/python-sdk/pull/2452

Prerequisite to #2460. Introduces a `Dispatcher` protocol that decouples JSON-RPC framing from MCP semantics, enabling pluggable transports. `DirectDispatcher` is an in-memory implementation for testing.

Not directly a channel/push notification feature, but enables the transport-agnostic architecture needed for future channel support.

### PR #2518 — `fix: send notifications/cancelled on request timeout and cancellation` (OPEN, 2026-04-29)

**URL**: https://github.com/modelcontextprotocol/python-sdk/pull/2518

Ensures `BaseSession` sends `notifications/cancelled` when in-flight requests time out or are cancelled. Resource-management fix, not a new notification capability.

---

## FastMCP (`PrefectHQ/fastmcp`)

No issues, PRs, or commits related to channels, server-to-client push notifications, or subscription systems found in recent activity (April–May 2026). Recent work focuses on OAuth/auth, bug fixes, and OpenAPI integration.

FastMCP depends on the python-sdk for this functionality, so movement on PR #2460/#2452 upstream would be required first.

---

## MCP Specification (`modelcontextprotocol/specification`)

No new channel or notification capability changes in recent commits. New working group charters added (File Uploads, Interceptors) but no specification for server-push channels.

---

## Assessment for VoiceMode (VM-970, VM-972)

**What was found:** PR #2460 adds server→client notification delivery via a `Connection` class, which is closer to what VoiceMode needs than anything previously seen. However:

- It is **not yet merged**
- It provides standard MCP notification types (`notifications/message`, resource/tool/prompt list changes), not a general-purpose "channel" for arbitrary server push
- There is no "channel" API (as Claude Code's channel system would require) in either the spec or the SDKs

**What's still missing:** The ability for an MCP server to push arbitrary messages or voice data to a client (Claude Code) without the client polling. Neither the spec, the Python SDK, nor FastMCP has added this.

**Recommendation:** Watch PR #2460 for merge; once merged, FastMCP would likely expose equivalent methods quickly. The `Connection.notify()` method could potentially be used as a foundation, but a channel-specific notification type would need to be defined.

---

## Next Check

Re-run this check after PR #2460 merges into python-sdk main, or if a new MCP spec version is published addressing server push.
