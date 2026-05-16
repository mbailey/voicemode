# MCP SDK Channel Notification Check — 2026-05-16

**Status: No channel/push notification support added. Spec moved in opposite direction.**

## Summary

Neither the Python MCP SDK nor FastMCP added support for server-initiated channel notifications this week. More significantly, the MCP specification just clarified (and effectively restricted) how server-to-client notifications work.

## Key Finding: Spec Restriction (PR #2728)

**[modelcontextprotocol/specification#2728](https://github.com/modelcontextprotocol/specification/pull/2728)** — merged May 15, 2026

This merged PR clarifies that `notifications/message` (logging notifications) is **request-scoped**:

- The server **MUST NOT** deliver it on a `subscriptions/listen` stream or any other stream
- It may only be emitted on the response stream of the specific request that triggered it
- The `subscriptions/listen` stream carries only opted-in change notifications: `tools/listChanged`, `prompts/listChanged`, `resources/listChanged`, and resource subscriptions

This is documentation-only (no wire format change), but it formally closes off the possibility of using `notifications/message` as a general push channel.

## Python MCP SDK (v1.27.1, May 8, 2026)

**No new push/channel capabilities added.** The existing `ServerSession` has these server-to-client methods:
- `send_log_message()` — request-scoped (now explicitly restricted per above)
- `send_resource_updated()` / `send_resource_list_changed()`
- `send_tool_list_changed()` / `send_prompt_list_changed()`
- `send_progress_notification()` — request-scoped

**Draft PR [#2460](https://github.com/modelcontextprotocol/python-sdk/pull/2460)** — "PeerMixin, BaseContext, Connection" (open, Apr 16)
- A refactor introducing typed `Connection` objects for per-client state management
- Provides `send_*_list_changed()` and `log()` convenience methods
- Still request-response + standard MCP notifications only — not arbitrary push

Recent activity focused on: SSE transport error isolation, session migration, OpenTelemetry tracing, OAuth improvements.

## FastMCP (v3.3.1, May 15, 2026)

No notification/channel features added. Recent releases focused on:
- `fastmcp-slim` for lightweight client-only installs
- OAuth hardening (Azure B2C, Clerk)
- OTEL compliance, bug fixes

FastMCP wraps the Python SDK, so it inherits the same constraints.

## Relevant Ongoing Proposals

These SEPs in the specification repo could eventually provide task-level streaming, which may indirectly enable what VoiceMode needs:

- **[SEP-2694](https://github.com/modelcontextprotocol/specification/issues/2694)**: Resumable Task Event Streams (open)
- **[SEP-2679](https://github.com/modelcontextprotocol/specification/issues/2679)**: Task streaming partial results (open)

Neither is implemented in the Python SDK yet.

## Implications for VoiceMode (VM-970, VM-972)

The MCP protocol does not support general server-to-client push outside the standard notification types. The spec clarification this week explicitly forbids using the `subscriptions/listen` stream for non-list-change notifications.

VoiceMode's inbound voice message channel likely needs to work through a different mechanism than MCP server notifications — for example:
- Polling via a tool call from the client
- Using the `elicitation` mechanism (out-of-band interaction)
- A separate WebSocket/HTTP channel outside MCP
- Waiting for Task streaming SEPs to mature

## Checked

- `modelcontextprotocol/python-sdk` commits, PRs, issues (past 7 days)
- `jlowin/fastmcp` commits and releases
- `modelcontextprotocol/specification` issues/PRs (channel, notification, server-to-client)
- Python SDK `ServerSession` notification API surface
