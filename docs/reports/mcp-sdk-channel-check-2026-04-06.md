# MCP SDK Channel/Notification Check — 2026-04-06

Monitoring report for server-to-client notification support in Python MCP SDK and FastMCP.
Relevant to: VoiceMode tasks VM-970 and VM-972.

## Summary

No new arbitrary "channel" or free-form push notification primitive has been added to either
library. However, FastMCP v3.0.0 (Feb 2026) introduced a Redis-backed notification queue for
background task elicitation — the closest thing to new server-push infrastructure.

**Conclusion: Not yet unblocked for VoiceMode's inbound voice channel needs.**

---

## Python MCP SDK — v1.27.0 (Apr 2, 2026)

### Existing notification support
The MCP protocol has always included server-to-client notifications:
- **Progress**: `ctx.session.send_progress_notification(...)`
- **Resource updates**: `ctx.session.send_resource_updated(uri)`
- **List-change notifications**: tools/resources/prompts list changed
- **Log messages**

### Recent activity
| Issue/PR | Status | Notes |
|----------|--------|-------|
| [#953](https://github.com/modelcontextprotocol/python-sdk/issues/953) | Closed/fixed | `context.report_progress` not sending on streamable-HTTP (missing `request_id`) |
| [#2001](https://github.com/modelcontextprotocol/python-sdk/issues/2001) | Open (P2) | Progress notifications not delivered via SSE in stateless HTTP mode |
| [#1512](https://github.com/modelcontextprotocol/python-sdk/issues/1512) | Open | Feature request: client subscription and server event broadcasting |
| [#1141](https://github.com/modelcontextprotocol/python-sdk/issues/1141) | Open | Progress notifications cause server to hang on stdio transport |

**v1.23.0 (Dec 2025)** aligned with protocol spec 2025-11-25, improving SSE/StreamableHTTP
transport. No new notification types were added.

---

## FastMCP — v3.2.0 (Mar 30, 2026)

### New in v3.0.0 (Feb 18, 2026): Background task notification queue
FastMCP [PR #2906](https://github.com/jlowin/fastmcp/pull/2906) introduced a **Redis-backed
distributed notification queue** (LPUSH/BRPOP pattern). When a tool runs in a background Docket
worker, `ctx.elicit()` routes through this queue:
1. Task sets status to `input_required`
2. Server pushes notification to MCP session
3. Task waits for client response

This enables server-to-client push for elicitation during long-running background tasks —
but is scoped to the elicitation flow, not a general-purpose channel.

### Context notification API (v3.x)
```python
ctx.send_notification(ToolListChangedNotification())
ctx.send_notification(ResourceListChangedNotification())
ctx.report_progress(...)  # wraps progress token handling
```

Automatic list-change notifications fire when components are added/removed/toggled during
an active session.

### What is NOT present
No arbitrary "channel" API or general-purpose server-push primitive exists. Servers cannot
push custom messages outside the MCP spec's defined notification types.

---

## Gaps Relevant to VoiceMode

1. **No general push channel**: Neither library supports sending arbitrary free-form messages
   from server to client — only the protocol-defined types (progress, list changes, resource
   updates, log).
2. **Client-side support**: Claude Desktop and most MCP hosts do not implement
   `resource/subscribe`, so `notifications/resources/updated` may be ignored even if sent.
3. **Open bugs**: Notification delivery over stateless HTTP (issue #2001) and stdio hangs
   (issue #1141) remain unfixed.
4. **Feature request open**: Issue #1512 tracks general broadcasting support in the Python SDK.

---

## References

- [Python MCP SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases)
- [FastMCP releases](https://github.com/jlowin/fastmcp/releases)
- [FastMCP background task PR #2906](https://github.com/jlowin/fastmcp/pull/2906)
- [MCP notifications discussion #1192](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1192)
- [FastMCP notifications docs](https://gofastmcp.com/clients/notifications)
