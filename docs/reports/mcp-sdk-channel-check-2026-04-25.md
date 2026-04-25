# MCP SDK Channel Notification Check — 2026-04-25

**Tracking:** VM-970, VM-972  
**Question:** Have Python MCP SDK or FastMCP added support for channel/push notifications (server-to-client) needed for VoiceMode's inbound voice messages via Claude Code's channel system?

## Summary

**No new channel notification API has been added.** Existing server-to-client notification primitives (progress, resource updates, logs) remain unchanged. However, several relevant developments are worth tracking.

---

## Python MCP SDK (modelcontextprotocol/python-sdk)

### Existing capabilities (unchanged)
The SDK already supports server-initiated notifications via session methods:
- `ctx.session.send_resource_list_changed()`
- `ctx.session.send_resource_updated(uri)`
- `ctx.session.send_progress_notification(progress_token, progress, total)`
- Log notifications via `ctx.debug()`, `ctx.info()`, etc.

These are point-in-time notifications tied to existing MCP spec message types — not a general-purpose push channel.

### Notable open PRs (as of 2026-04-25)

| PR | Title | Status | Relevance |
|----|-------|--------|-----------|
| [#2281](https://github.com/modelcontextprotocol/python-sdk/pull/2281) | Add client callbacks for list_changed notifications | Open (awaiting review) | Medium — adds client-side handling of tool/resource/prompt change notifications; doesn't add new server push primitives |
| [#2491](https://github.com/modelcontextprotocol/python-sdk/pull/2491) | ServerRunner — per-connection orchestrator | Draft | Low — infrastructure refactor |
| [#2502](https://github.com/modelcontextprotocol/python-sdk/pull/2502) | Drop responses/notifications when write stream is closed | Open | Low — bug fix |
| [#2493](https://github.com/modelcontextprotocol/python-sdk/pull/2493) | Don't send response for cancelled requests | Open | Low — correctness fix |

### 2026 MCP Roadmap stance

The [2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) explicitly lists **"triggers and event-driven updates"** as **"On the Horizon"** (community-driven, not core-team-driven):

> "These aren't deprioritized in the sense of 'We don't want them.' They're areas where we'll happily support a community-formed WG and review SEPs as time permits."

The four core focus areas for 2026 are: transport scalability, agent communication, governance maturation, and enterprise readiness. Server-push/channel notifications are not among them.

---

## FastMCP (jlowin/fastmcp)

### PR #2906 — Distributed Notification Queue (merged Feb 10, 2026)

[feat: distributed notification queue + BLPOP elicitation for background tasks](https://github.com/jlowin/fastmcp/pull/2906)

This is the most significant notification-related change in FastMCP recently. It adds:
- Redis-backed notification queue using LPUSH/BRPOP
- Enables MCP servers running on distributed/remote workers to push task status updates to clients
- `report_progress()` now stores progress in Redis for remote workers to report metrics

**Important caveat:** This is an inter-process transport mechanism for FastMCP's own task system — it uses Redis to bridge worker processes to the MCP session, then delivers via the existing MCP notification protocol. It does **not** expose a new MCP protocol-level push channel.

### Issue #2904 — statusMessage not forwarded to client

A bug where `statusMessage` from task status updates wasn't reaching clients (via `tasks/get` polling responses). This is a polling-based issue, unrelated to push channels.

---

## Assessment for VoiceMode (VM-970, VM-972)

| Need | Status |
|------|--------|
| General server-to-client push channel (new MCP capability) | Not in any SDK; on MCP 2026 roadmap as community-driven only |
| Arbitrary message push from server to client | Not supported at protocol level |
| Notification when tools/resources change | Exists; client-side callback PR #2281 pending |
| Progress/log push during tool execution | Already supported |
| FastMCP distributed worker notifications | Available via Redis since Feb 2026 (internal mechanism) |

**Conclusion:** VoiceMode's need for inbound voice messages via Claude Code's channel system cannot yet be met by waiting for the Python MCP SDK or FastMCP to add this capability. The MCP 2026 roadmap explicitly deprioritizes general event-driven/push notification work. A custom solution (e.g., polling, webhooks, or a separate transport) will be needed in the near term.

---

*Checked by automated monitoring agent. Next check: 2026-05-02.*
