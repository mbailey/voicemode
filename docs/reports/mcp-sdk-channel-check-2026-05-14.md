# MCP SDK Channel Notification Check — 2026-05-14

**Related tasks:** VM-970, VM-972  
**Question:** Have the Python MCP SDK or FastMCP added support for server-to-client channel notifications (server-initiated push)?

---

## TL;DR

No shipping support yet. Two active spec proposals (SEPs) are progressing that would enable server-to-client event streaming. The most relevant — SEP-2694 (Resumable Task Event Streams) — includes vendor-prefixed event types with arbitrary JSON payloads and could underpin VoiceMode inbound voice message delivery. Neither is implemented in the Python SDK yet.

---

## Python MCP SDK (modelcontextprotocol/python-sdk) — v1.27.1

### Already Shipped: Server-to-Client Notifications

The `ServerSession` class already implements these notification methods:

| Method | Purpose |
|--------|---------|
| `send_log_message()` | Send log message to client |
| `send_resource_updated()` | Notify resource changed |
| `send_progress_notification()` | Progress updates |
| `send_resource_list_changed()` | Resource list changed |
| `send_tool_list_changed()` | Tool list changed |
| `send_prompt_list_changed()` | Prompt list changed |
| `send_elicit_complete()` | URL-based elicitation finished |

These are all **protocol-defined** types only. No mechanism exists for arbitrary/custom notification payloads.

### Pending PRs

- **PR #1611** (open, last active Jan 2026): Adds client-side callback handlers for all protocol-defined server notification types (ResourceUpdated, LoggingLevel, Progress, ElicitComplete). Does **not** add new notification types — improves client handling of existing ones.
- **PR #2518/2514**: Send `notifications/cancelled` on request timeout.
- **PR #2584**: Transparent session migration on server restart.

No PRs add a new channel-style or arbitrary-payload notification mechanism.

---

## FastMCP (jlowin/fastmcp) — v3.2.4

VoiceMode requires `fastmcp>=3.2.0,<4`. Latest is v3.2.4.

The 3.x series added background task elicitation with Redis-backed distributed notification queues (`ctx.elicit()` relay), but this is scoped to the elicitation request/response pattern — the server **asking** the client/user for input — not pushing arbitrary data.

No new channel or push notification APIs were added in the 3.x series.

---

## MCP Specification — Active SEPs

Two SEPs are in active development that are directly relevant:

### SEP-2694: Resumable Task Event Streams (opened May 6, 2026)

**Most relevant for VoiceMode.**

Introduces:
- `tasks/stream` request: client subscribes to an event stream for a task
- `notifications/tasks/event`: server pushes events with sequence numbers (resumable after disconnect)
- **Vendor-prefixed event types with arbitrary JSON payloads**

This would enable something like `voicemode.inbound_audio` events pushed from server to client within the task framework. Still a spec proposal — not implemented in Python SDK.

### SEP-2679: Task Streaming Partial Results (opened May 4, 2026)

Introduces `notifications/tasks/partial` for streaming incremental text content during task execution. Narrowly focused on streaming LLM-generated text; not a general push mechanism.

---

## Assessment for VoiceMode

| Capability Needed | Status |
|-------------------|--------|
| Server sends protocol notifications (progress, tool list, etc.) | **Already works** |
| Client receives server notifications (all types) | **PR #1611 pending**, not shipped |
| Arbitrary/custom server-to-client push messages | **Not supported** |
| Task event streams with vendor-prefixed payloads | **SEP-2694, spec stage only** |

VoiceMode's inbound voice channel needs a way to push audio/text events to Claude Code unprompted. The closest path forward is SEP-2694 if it gets implemented. Alternative approaches in the interim:
- Use MCP resources as a polling target (client polls for new voice messages)
- Out-of-band transport (WebSocket/SSE alongside MCP)
- Abuse `send_log_message()` as a side channel (not recommended)

---

## Recommendation

Watch SEP-2694 (`modelcontextprotocol/specification#2694`) and PR #1611 (`modelcontextprotocol/python-sdk#1611`). No action needed in VoiceMode today. Re-check when either lands in a python-sdk release.
