# MCP SDK Channel Notification Check — 2026-04-26

**Summary:** No channel/push notification support has landed yet. Two relevant draft PRs are in progress in the Python MCP SDK.

## Context

VoiceMode (tasks VM-970, VM-972) needs the ability for an MCP server to push arbitrary notifications to the client — specifically to deliver inbound voice messages through Claude Code's channel system. This requires server-initiated notifications beyond what the current MCP spec defines.

## Python MCP SDK (modelcontextprotocol/python-sdk)

### Existing capability

`ServerSession` already exposes several server-to-client notification methods:
- `send_log_message()` — log level messages
- `send_resource_updated()` — resource change events
- `send_progress_notification()` — progress updates
- `send_resource_list_changed()`, `send_tool_list_changed()`, `send_prompt_list_changed()` — list change events
- `send_elicit_complete()` — URL-mode elicitation completion

These are all protocol-defined, purpose-specific notifications — not a general-purpose channel.

### In-progress PRs (not merged)

**PR #2460 — `PeerMixin`, `BaseContext`, `Connection`, server `Context`** (opened 2026-04-16, draft)

The most relevant PR for VoiceMode. Adds a typed layer above the low-level dispatcher:
- `Connection` class: manages per-client state, provides a standalone-stream `Outbound` channel, includes best-effort `notify()` that never raises
- `PeerMixin`: typed server-to-client request methods (`sample`, `elicit_form`, `elicit_url`, `list_roots`, `ping`)
- Will be used by `ServerRunner` once that PR is ready

This is the closest thing to a general notification channel, but it's still bound to protocol-defined message types.

**PR #2491 — `ServerRunner` per-connection orchestrator** (opened 2026-04-22, draft)

Bridges the dispatcher layer with user handler logic. Handles initialize handshake, request gating, middleware chain. Stacked on #2460. No notification additions itself.

**PR #2502 — Drop responses/notifications when write stream is closed** (opened 2026-04-24, open)

Bug fix: catches `ClosedResourceError`/`BrokenResourceError` in `send_notification()` and `_send_response()` rather than crashing. Relevant for robustness but not new capability.

### Bottom line

No new notification types or channel primitives have been added. The SDK supports server-to-client notifications for defined protocol events only. The `Connection` class in PR #2460 is the most promising building block but is unmerged and still protocol-scoped.

## FastMCP (jlowin/fastmcp)

No relevant updates in recent releases (v3.0.1 through v3.2.4, February–April 2026). Recent work focuses on OAuth/auth providers, security hardening, and UI tools (`FastMCPApp`). FastMCP wraps the Python SDK, so any channel support would need to come from the SDK first.

## MCP Specification

No recent commits to the spec repository related to channels, push notifications, or new notification types. The spec defines server-to-client notifications for: logging, resource updates, list changes, and progress — all request-scoped or protocol-internal.

## What VoiceMode Needs

A mechanism for an MCP server to push an arbitrary message to the client without a client request — analogous to a WebSocket message or SSE event. This does not exist in the spec or SDK today. The closest path:

1. Wait for PR #2460 (`Connection`) to merge — it adds a typed `notify()` path
2. Propose a new notification type to the MCP spec (e.g., `notifications/message` or a channel primitive)
3. Or: use long-polling via a tool call (client polls `wait_for_message` tool) as a workaround

## Recommendation

Monitor PR #2460 for merge. Consider opening an issue on the MCP spec repo proposing a general-purpose `notifications/channel` message type to support use cases like VoiceMode inbound messages.
