# MCP SDK Channel/Notification Check — 2026-04-01

## Summary

No new "channel" primitive has landed in either the Python MCP SDK or FastMCP in the past 30 days. However, there is **active open work** on resource subscriptions and notification callbacks that is directly relevant to VoiceMode's needs.

## Python MCP SDK (modelcontextprotocol/python-sdk)

### Already Supported (Server-to-Client)

`ServerSession` has these notification methods today:

- `send_log_message(level, data, ...)`
- `send_resource_updated(uri)`
- `send_resource_list_changed()`
- `send_tool_list_changed()`
- `send_prompt_list_changed()`
- `send_progress_notification(...)`
- `send_elicit_complete(elicitation_id, ...)` — added in v1.23.0

### Active PRs / Issues (past 30 days)

| # | Type | Title | Status |
|---|------|-------|--------|
| [#2281](https://github.com/modelcontextprotocol/python-sdk/pull/2281) | PR | Add client callbacks for list_changed notifications | Open, unreviewed |
| [#2322](https://github.com/modelcontextprotocol/python-sdk/pull/2322) | PR | Multi Round-Trip Requests (MRTR) — mid-execution client callbacks | Draft |
| [#1399](https://github.com/modelcontextprotocol/python-sdk/issues/1399) | Issue | Support more (custom) notification types | **Closed/fixed** — validation relaxed to allow non-standard methods like `codex/event` |

### Recent Releases

- **v1.26.0** (2026-01-24): Resource/ResourceTemplate metadata, HTTP 404 for unknown sessions
- **v1.23.0** (2025-12-02): SEP-1686 Tasks, SEP-1699 SSE polling, URL elicitation
- **v2.x**: Under active development on `main`, not yet released (Q1 2026 target, now overdue)

## FastMCP (PrefectHQ/fastmcp)

### Current API

`Context.send_notification()` is available for generic server-to-client push:

```python
await ctx.send_notification(mcp.types.ToolListChangedNotification())
```

No convenience wrappers (e.g., `notify_resource_updated()`) exist yet.

### Key Finding: Resource Subscriptions (Issue #3641)

**[Issue #3641](https://github.com/PrefectHQ/fastmcp/issues/3641)** (open, 2026-03-27):
FastMCP is failing MCP conformance tests for `resources/subscribe` and `resources/unsubscribe`. This is the core server-to-client push gap for resource updates.

**[PR #3645](https://github.com/PrefectHQ/fastmcp/pull/3645)** (rejected, 2026-03-27):
An implementation was submitted but rejected by @jlowin due to architectural issues (global registry vs. per-server registry). A design proposal was requested. No replacement PR has appeared yet.

### Recent Releases

- **v3.2.0** (2026-03-30): `FastMCPApp` interactive UI providers (FileUpload, Approval, Choice, FormInput). No notification changes.
- **v3.1.0** (2026-03-03): CodeMode transform, MultiAuth. v3.0.0 introduced background task notification queues.
- **v3.0.0** (2026-02-18): Major rewrite with OpenTelemetry, session state, `on_disconnect` middleware.

## Implications for VoiceMode

1. **No new channel primitive** has landed — VoiceMode's channel/notification work cannot rely on new SDK support yet.

2. **FastMCP resource subscriptions are the critical gap** — Issue #3641 is the blocker for clean server-push semantics. Track this issue.

3. **Custom notification types now allowed** in the Python SDK (Issue #1399 closed) — VoiceMode could send custom notifications (e.g., `voicemode/inbound`) using `ServerSession` directly.

4. **Python SDK v2** has not released yet — watch for its release as it may change notification APIs.

5. **Workaround available today**: Using the low-level Python SDK `ServerSession.send_*` methods directly (bypassing FastMCP's `Context`) is possible but fragile until FastMCP wraps them properly.

## Tasks to Watch

- VM-970, VM-972 — VoiceMode channel/notification work
- FastMCP Issue #3641 — resource subscriptions
- Python SDK PR #2281 — client list_changed callbacks
