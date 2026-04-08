# MCP SDK Channel/Notification Check — 2026-04-08

**Related tasks:** VM-970, VM-972  
**Purpose:** Monitor Python MCP SDK and FastMCP for server-to-client notification / channel support needed for VoiceMode inbound voice messages via Claude Code's channel system.

---

## Summary

Both repos have relevant notification infrastructure. The most significant recent additions are in **FastMCP v3.0.0** (released Feb 18, 2025, with key commits in Feb 2026): a Redis-backed distributed notification queue and `ctx.elicit()` relay for background tasks via standard MCP protocol.

**Bottom line:** FastMCP now has the building blocks for server-initiated async notifications via background tasks. However, this is not yet a generic "push channel" — it is tied to the task/elicitation workflow and requires Redis for distributed deployments. The Python SDK's experimental task context (`TaskStatusNotification`) is the underlying spec primitive.

---

## Python MCP SDK (`modelcontextprotocol/python-sdk`)

### Existing notification support (long-standing)

`ServerSession` in `src/mcp/server/session.py` has always supported one-way JSON-RPC server-initiated notifications:

- `send_log_message()` — log events to client
- `send_resource_updated(uri)` — resource changed
- `send_resource_list_changed()` — resource catalog changed
- `send_tool_list_changed()` — tool catalog changed
- `send_prompt_list_changed()` — prompt catalog changed
- `send_progress_notification()` — progress updates

All delegate to `BaseSession.send_notification()` which pushes directly over `_write_stream`. No queuing or channel abstraction.

### Experimental task infrastructure (v1.23.0, Dec 2024)

`src/mcp/server/experimental/` adds:

- `ServerTaskContext` — wraps tasks with `update_status()`, `complete()`, `fail()`, `elicit_as_task()`, `create_message_as_task()`, sending `TaskStatusNotification` back to client
- `TaskSupport` — wires a task store, `TaskMessageQueue`, and result handler; configures sessions with "response routing"
- `TaskResultHandler` — routes responses from queued requests back to waiting resolvers

This enables **long-running background tasks that push async status notifications** to the client and relay elicitation/sampling requests without blocking.

### Recent activity (Jan–Apr 2026)

- **Mar 31, 2026** — OpenTelemetry tracing added (#2381) — not notification-related
- **Mar 9, 2026** — `fix: don't send log notification on transport error` (#2257) — bug fix preventing spurious log notifications on transport errors
- **Jan–Feb 2026** — context propagation and misc refactors

No new notification/channel features in the past 90 days in the Python SDK itself.

**Relevant files:**
- `src/mcp/server/session.py` — `ServerSession` with all `send_*` methods
- `src/mcp/shared/session.py` — `BaseSession.send_notification`
- `src/mcp/server/experimental/` — task context / `TaskSupport` / `TaskResultHandler`

---

## FastMCP (`jlowin/fastmcp` → `PrefectHQ/fastmcp`)

### v3.0.0 — Feb 18, 2025 — Major notification additions

Key features added:
- **Background tasks with Redis notification queue** — distributed queue replacing polling
- **`ctx.elicit()` relay** — background tasks can request user input relayed through standard MCP elicitation protocol
- `ctx.set_state()` / `ctx.get_state()` — session state persistence

### Key commits (recent, within 90 days)

| Date | Commit | Summary |
|------|--------|---------|
| Feb 8, 2026 | `ecbce07` | `feat: distributed notification queue for background task elicitation` — Redis-backed queue with subscriber management, retry logic, TTL expiration |
| Feb 10, 2026 | `361eb08` | `Relay task elicitation through standard MCP protocol` — background tasks request user input via standard MCP without direct Redis interaction |
| Jan 18, 2026 | — | `Remove sync notification infrastructure` — removed `send_notification_sync()` and background flusher task |
| Dec 24, 2025 | — | `Consolidate notification system with unified API` |

### Current state (Apr 2026)

The notification system is now consolidated. Background tasks in FastMCP can:
1. Push `TaskStatusNotification` events to clients asynchronously
2. Relay `elicit()` calls back through standard MCP protocol
3. Use a Redis-backed queue for distributed deployments

Recent v3.1.0 (Mar 3, 2025) and v3.2.0 (Mar 30, 2025) focused on auth/OAuth and FastMCPApp UI — no new notification features. Current Apr 2026 activity continues on auth/OAuth fixes.

---

## Assessment for VoiceMode

### What exists now

The infrastructure for server-to-client async notifications **exists** but is:
1. Tied to the **task/elicitation workflow** — not a generic push channel
2. Requires **Redis** for distributed deployments (FastMCP v3.0.0+)
3. Based on **MCP spec's Tasks capability** (SEP-1686) which is experimental

### Gap for VoiceMode's needs

VoiceMode needs to push **inbound voice messages** to Claude Code's channel system as server-initiated events. The current notification primitives:
- Can push task status updates ✓
- Can relay elicitation requests (e.g., asking Claude to do something) ✓
- Cannot push arbitrary "new voice message arrived" events in a generic channel pattern ✗

### Recommended next steps

1. **Evaluate the Tasks capability** (SEP-1686) in the Python SDK experimental module — a background task that listens for voice input and sends `TaskStatusNotification` with the audio/transcript may be the closest fit
2. **Test FastMCP's `ctx.elicit()` relay** — could work as a channel for voice input if VoiceMode runs a background task that long-polls for audio and relays it as an elicitation
3. **Watch for MCP spec "channels" proposal** — none found yet, but the community is moving toward this

---

## References

- https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/session.py
- https://github.com/modelcontextprotocol/python-sdk/tree/main/src/mcp/server/experimental
- https://github.com/modelcontextprotocol/python-sdk/commit/62eb08e (log notification bug fix, Mar 9 2026)
- https://github.com/jlowin/fastmcp/releases/tag/v3.0.0 (background task notifications)
- https://github.com/jlowin/fastmcp/commit/ecbce07 (distributed notification queue, Feb 8 2026)
- https://github.com/jlowin/fastmcp/commit/361eb08 (elicitation relay, Feb 10 2026)
