# MCP SDK Channel Notification Check — 2026-04-24

**Status: SIGNIFICANT FINDINGS — Claude Code Channels is live, Python SDK support is partial**

## Summary

Claude Code Channels (research preview) launched on **March 20, 2026** with Claude Code v2.1.80. This is exactly the mechanism VoiceMode needs for inbound voice messages. However, the **Python MCP SDK does not yet support sending the required custom notification type** (`notifications/claude/channel`). The official examples and pre-built plugins all use TypeScript/Node.js.

A workaround exists using the Python SDK's lower-level transport APIs.

---

## 1. Claude Code Channels — The Feature VoiceMode Needs

**Documentation:** https://code.claude.com/docs/en/channels-reference

Channels allow MCP servers to **push events into a running Claude Code session** — no client request required. This is the "server-to-client notification" capability tracked in VM-970 and VM-972.

### How it works

An MCP server declares a special experimental capability and emits a notification method that Claude Code listens for:

```typescript
// TypeScript (official SDK — works today)
const mcp = new Server(
  { name: 'voicemode', version: '1.0.0' },
  {
    capabilities: {
      experimental: { 'claude/channel': {} },  // registers the listener
    },
    instructions: 'Inbound voice messages arrive as <channel source="voicemode" ...>.',
  },
)

await mcp.notification({
  method: 'notifications/claude/channel',
  params: {
    content: 'User said: "run the tests"',
    meta: { speaker: 'mike', audio_id: 'abc123' },
  },
})
```

Claude Code receives:
```
<channel source="voicemode" speaker="mike" audio_id="abc123">
User said: "run the tests"
</channel>
```

### Key protocol details

| Item | Value |
|---|---|
| Capability declaration | `experimental: { 'claude/channel': {} }` |
| Notification method | `notifications/claude/channel` |
| Params | `content: string`, `meta: Record<string, string>` (optional) |
| Permission relay capability | `experimental: { 'claude/channel/permission': {} }` |
| Permission request notification | `notifications/claude/channel/permission_request` |
| Permission verdict notification | `notifications/claude/channel/permission` |
| Min Claude Code version | v2.1.80 (channels), v2.1.81 (permission relay) |
| Auth requirement | claude.ai login (Console/API key NOT supported) |
| Dev testing flag | `--dangerously-load-development-channels server:<name>` |

### Feature status

- Research preview since March 20, 2026
- Built-in channels: Telegram, Discord, iMessage, fakechat
- Custom channels require `--dangerously-load-development-channels` until on the official allowlist
- Team/Enterprise: admin must explicitly enable (`channelsEnabled` policy)
- Known bug (issue #44283, closed as duplicate): Discord plugin notifications were silently dropped in Claude Code 2.1.92 for Team/Enterprise users

---

## 2. Python MCP SDK (v1.27.0) — Partial Support

**Current version:** 1.27.0 (released April 2, 2026)  
**Latest protocol version in SDK:** 2025-06-18

### What works ✅

`ServerCapabilities` supports `experimental` as `dict[str, dict[str, Any]]`:

```python
# mcp/types.py line ~298
class ServerCapabilities(BaseModel):
    experimental: dict[str, dict[str, Any]] | None = None
    # ...
```

So declaring the `claude/channel` capability IS possible in Python via `InitializationOptions`.

### What doesn't work ❌

`ServerNotification` is a **closed union** of predefined types only:

```python
# mcp/types.py line ~1292
class ServerNotification(
    RootModel[
        CancelledNotification
        | ProgressNotification
        | LoggingMessageNotification
        | ResourceUpdatedNotification
        | ResourceListChangedNotification
        | ToolListChangedNotification
        | PromptListChangedNotification
    ]
):
    pass
```

The `send_notification()` method in `BaseSession` requires a `ServerNotification` object. There is **no `notifications/claude/channel` type** in this union, and no equivalent of the TypeScript SDK's `server.notification({ method: '...', params: {...} })` that accepts arbitrary method names.

### Python SDK workaround (hack)

It IS possible to bypass the typed API by writing directly to the transport write stream:

```python
from mcp.types import JSONRPCNotification, JSONRPCMessage
from mcp.shared.message import SessionMessage

async def send_channel_notification(session, content: str, meta: dict = None):
    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={"content": content, "meta": meta or {}},
    )
    session_msg = SessionMessage(message=JSONRPCMessage(notification))
    await session._write_stream.send(session_msg)
```

This bypasses the type system. It's a workaround, not an official API. A proper solution requires the Python MCP SDK to add an `send_raw_notification(method, params)` or similar method.

### Recent Python SDK activity (past 7 days)

No notification system changes. Recent PRs focus on:
- Request cancellation handling (#2479, #2481, #2493, #2502)
- ServerRunner orchestrator refactor (#2491, draft)
- Auth improvements (#2492, #2495, #2498)

No open PRs or issues for adding arbitrary/custom notification sending.

---

## 3. FastMCP (VoiceMode currently uses 2.x pinned to `>=2.3.2,<3`)

**FastMCP 2.x** (the version VoiceMode uses): Has `experimental_capabilities` parameter in `LowLevelServer.create_initialization_options()` — so capability declaration works. No channel-specific notification sending support.

**FastMCP 3.x** (PrefectHQ, v3.2.4 as of April 14, 2026): No Claude Code channel protocol support. Recent releases focus on auth (Azure B2C, Cognito, Keycloak), OpenTelemetry, OAuth, and plugin architecture. No Python channel support added.

---

## 4. Recommended Paths for VoiceMode

### Option A: TypeScript companion channel server (fastest to working)

Build a small Node.js/Bun channel server alongside VoiceMode. The TypeScript MCP SDK fully supports the protocol. This server would:
1. Receive audio/transcription from VoiceMode's Python server (via local HTTP or socket)
2. Forward as `notifications/claude/channel` to Claude Code

Pros: Works today, follows official examples  
Cons: Adds a Node.js dependency, two-process architecture

### Option B: Python SDK raw notification workaround

Use the `_write_stream` hack above inside VoiceMode's FastMCP server. Also need to declare the capability via `experimental_capabilities`.

Pros: Pure Python, single process  
Cons: Uses private API (`_write_stream`), may break on SDK updates

### Option C: Contribute to Python MCP SDK

Open a PR to add `send_raw_notification(method: str, params: dict)` to `ServerSession` or `BaseSession`. This is the clean long-term solution.

The TypeScript SDK's `server.notification()` pattern should be mirrored in Python.

### Option D: Wait and monitor

Continue checking weekly. If PrefectHQ's FastMCP 3.x adds support, VoiceMode would need to drop the `<3` pin (VM-742 tracks this migration). No sign of this happening imminently.

---

## 5. Related Links

- [Claude Code Channels reference docs](https://code.claude.com/docs/en/channels-reference)
- [Official channel plugin examples (TypeScript)](https://github.com/anthropics/claude-plugins-official/tree/main/external_plugins)
- [Issue #36665 — MCP server push notifications request](https://github.com/anthropics/claude-code/issues/36665) (open, stale)
- [Issue #44283 — Discord channel notifications silently dropped](https://github.com/anthropics/claude-code/issues/44283) (closed duplicate)
- [Python MCP SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases)
- [FastMCP 3.x releases](https://github.com/PrefectHQ/fastmcp/releases)
- VoiceMode tasks: VM-970, VM-972
