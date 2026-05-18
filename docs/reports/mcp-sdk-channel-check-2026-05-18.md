# MCP SDK Channel Notification Check — 2026-05-18

**Context:** VoiceMode (VM-970, VM-972) needs to send `notifications/claude/channel` notifications from its FastMCP-based MCP server so Claude Code can receive inbound voice messages through its channel system.

---

## Summary

No new support for sending arbitrary/custom notification methods has been added to the Python MCP SDK or FastMCP. The core blocker remains: the Python MCP SDK's `ServerNotification` type is a strict union of predefined notification types — it does **not** allow servers to emit custom notification methods like `notifications/claude/channel`.

---

## Python MCP SDK (modelcontextprotocol/python-sdk)

**Latest version:** v1.27.1 (May 8, 2026)

### What exists

`ServerSession` exposes these predefined server-initiated notification methods:

- `send_log_message()`
- `send_resource_updated()`
- `send_progress_notification()`
- `send_resource_list_changed()`
- `send_tool_list_changed()`
- `send_prompt_list_changed()`
- `send_elicit_complete()`

The underlying `BaseSession.send_notification()` accepts a `SendNotificationT` generic, but `ServerNotification` is a **fixed union** of the types above — not an open type.

### What's missing

No mechanism to send a custom/arbitrary notification method name (e.g., `notifications/claude/channel`). The type system actively prevents it.

### Relevant open issues

- **#1512** (Oct 2025, open) — "Add client subscription and server event broadcasting" — touches on extensible notification capabilities, no resolution yet
- **#2507** (Apr 2026, open) — `ClientSession` never sends `notifications/cancelled`, causing server-side coroutine leaks
- **#2480** (Apr 2026, open) — `RequestResponder.cancel` sends JSON-RPC response instead of notification, violating cancellation spec

---

## FastMCP (jlowin/fastmcp)

**Latest version:** v3.3.1 (May 15, 2026)

### What exists

FastMCP surfaces the Python MCP SDK notification types through `Context` methods:
- `ctx.debug/info/warning/error()` → maps to `send_log_message()`
- `ctx.report_progress()` → maps to `send_progress_notification()`
- `ctx.session.send_resource_list_changed()`, etc.

### What's missing

No new notification or channel APIs. FastMCP inherits the Python MCP SDK's type restriction and adds no generic "send custom notification" capability of its own.

### Relevant open issues

- **#4161** (May 16, 2026, open) — "Should proxies forward upstream list/resource notifications downstream?" — confirms existing notification types (tools/resources/prompts list_changed, resources/updated, message) are not being forwarded through proxies
- **#3641** (Mar 2026, open) — "MCP conformance: resource subscriptions (subscribe/unsubscribe)" — resource subscriptions still marked as expected failures in conformance tests

---

## Claude Code Channel System (`notifications/claude/channel`)

The channel system VoiceMode wants to use is a **Claude Code-side MCP extension**, not a Python MCP SDK feature:

- MCP servers declare the capability: `experimental: { 'claude/channel': {} }`
- Servers send: `mcp.notification({ method: 'notifications/claude/channel', params: { content, meta } })`
- Expected message format in Claude Code: `<channel source="..." ...>message</channel>`
- Requires opt-in via `--channels` flag at Claude Code startup

**Current state in Claude Code:** Multiple open and closed issues show this is unreliable:

| Issue | Description | Status |
|-------|-------------|--------|
| #37026 | `--channels` ignored, Discord plugin notifications not working | Closed/duplicate |
| #36431 | Telegram plugin: inbound notifications not delivered | Closed/duplicate |
| #36503 | `--channels` shows "not currently available" | Closed/duplicate |
| #37301 | Telegram MCP channel notifications not received (v2.1.81) | Closed/duplicate |
| #43088 | `notifications/claude/channel` received by CLI but never displayed | Closed/not planned |
| #44283 | Discord plugin notifications not handled by Claude Code | Closed/duplicate |

The feature was announced March 20, 2026 as a research preview.

---

## Conclusion

**Blocker:** The Python MCP SDK's `ServerNotification` is a strict union type. No PR or commit in recent history has added support for sending arbitrary custom notification methods. FastMCP, which wraps the Python MCP SDK, inherits this constraint.

**Workaround to investigate:** It may be possible to send a raw JSON-RPC notification by reaching into the transport layer directly (bypassing SDK typing), but this would be fragile and unsupported. A cleaner path would require a PR to the Python MCP SDK to support extensible/custom notification types, or using the TypeScript SDK (which appears more permissive).

**Recommended next steps:**
1. Open or find an existing issue on `modelcontextprotocol/python-sdk` requesting support for sending custom notification method names
2. Monitor Claude Code issues — the channel system itself appears partially broken; may not be worth implementing against until Claude Code's handling stabilizes
3. Consider whether VoiceMode Connect (the existing remote voice bridge) covers the use case sufficiently while channel support matures

---

*Generated by automated MCP SDK channel monitoring check. References VoiceMode tasks VM-970, VM-972.*
