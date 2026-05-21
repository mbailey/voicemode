# MCP SDK Channel Notification Check — 2026-05-21

**Tasks:** VM-970, VM-972  
**Question:** Have the Python MCP SDK or FastMCP added support for channel notifications (server-to-client notifications)?

## Summary

Claude Code Channels is a live, documented feature (research preview since March 20, 2026) that is **exactly** what VM-970/VM-972 needs. The notification mechanism `notifications/claude/channel` is already defined and working in the TypeScript SDK. The Python MCP SDK can send arbitrary notifications via its low-level API — but no Python-specific channel documentation or convenience APIs exist yet. FastMCP has not added anything channel-specific. There is also an active, unresolved bug where channel notifications fail to reach the Claude Code conversation in the Telegram and Discord plugins.

---

## Claude Code Channels (the feature VoiceMode needs)

**What it is:** Channels allow an MCP server (running as a stdio subprocess spawned by Claude Code) to push events into the active session. Events arrive in Claude's context as `<channel source="...">content</channel>` tags. Claude can read them and optionally reply via a registered tool.

**Announced:** March 20, 2026 — research preview, requires Claude Code ≥ v2.1.80.

**Reference:** https://code.claude.com/docs/en/channels-reference

### Protocol contract

To be a channel, an MCP server must:

1. **Declare capability:** `capabilities.experimental['claude/channel'] = {}`
2. **Send notifications via:** `mcp.notification({ method: 'notifications/claude/channel', params: { content, meta? } })`
3. **Connect over stdio** (Claude Code spawns the server as a subprocess)

Notification payload:
```json
{
  "method": "notifications/claude/channel",
  "params": {
    "content": "the message body",
    "meta": { "key": "value" }
  }
}
```

The event Claude sees:
```
<channel source="server-name" key="value">the message body</channel>
```

Optional extensions:
- `capabilities.experimental['claude/channel/permission']` — relay permission prompts to the remote channel
- A standard MCP `reply` tool — for two-way (chat bridge) use cases

### Launch flag

Channels must be named explicitly at startup:
```bash
claude --channels server:myserver
# or during research preview with custom channels:
claude --dangerously-load-development-channels server:myserver
```

---

## Python MCP SDK status

**Latest release:** v1.27.1 (May 8, 2026)  
**Repo:** https://github.com/modelcontextprotocol/python-sdk

### Notification support (existing)

The Python SDK already supports server-initiated notifications:
- `ctx.session.send_progress_notification()` — progress during tool calls
- `ctx.session.send_resource_updated(uri)` — resource change notification
- `ctx.session.send_resource_list_changed()` — resource list change

### `notifications/claude/channel` — no native Python support yet

The channels reference only shows TypeScript/Bun examples. There is no Python SDK convenience method for `notifications/claude/channel`. However, the Python SDK's low-level session API can send arbitrary notifications. A VoiceMode channel server would need to call something like:

```python
await session.send_notification("notifications/claude/channel", {
    "content": "voice message text",
    "meta": {"source": "voice"}
})
```

The exact Python API surface for this needs verification against the SDK source.

### Relevant recent PR

**PR #2654** (open, May 21, 2026): "fix: buffer stdio server writes during progress notifications"  
Fixes a deadlock where a handler can't queue its response while stdout is flushing an earlier notification. This is directly relevant since VoiceMode would use stdio transport and send notifications during tool execution.  
https://github.com/modelcontextprotocol/python-sdk/pull/2654

---

## FastMCP status

**Latest release:** v3.3.1 (May 15, 2026)  
**Repo:** https://github.com/jlowin/fastmcp

No channel-specific features added. Recent releases focus on:
- `fastmcp-slim` lightweight client-only package
- OTEL instrumentation improvements
- OAuth security hardening
- Thread affinity control for sync tools

FastMCP does not yet expose a `notifications/claude/channel` API or a `channel` capability helper. VoiceMode would need to either:
1. Use the underlying Python MCP SDK session directly, or
2. Wait for FastMCP to add a channel convenience API

---

## Active bugs — channel notifications not delivered

Two open issues confirm that `notifications/claude/channel` events are not reaching the Claude Code conversation, even when the MCP server is correctly connected and sending them:

- **Issue #36431** (open): Telegram plugin — inbound `notifications/claude/channel` never appear in conversation. Outbound (reply tool) works. https://github.com/anthropics/claude-code/issues/36431
- **Issue #40729** (open): Same failure for Discord. Both confirmed across multiple restarts.

**Root cause hypothesis:** Claude Code's MCP notification handler does not properly route `notifications/claude/channel` events into the active conversation despite the server being connected. No fix or workaround has been posted.

This bug affects any channel implementation, including a VoiceMode voice channel.

---

## Implications for VM-970 / VM-972

| Question | Answer |
|---|---|
| Does the channel protocol exist? | Yes — `notifications/claude/channel` is documented and in research preview |
| Does the TypeScript SDK support it? | Yes — examples in the official reference |
| Does the Python MCP SDK support it? | Indirectly — low-level notification API can send it, no convenience method |
| Does FastMCP support it? | No — no channel APIs added |
| Does it work end-to-end right now? | Blocked by bug #36431 / #40729 — notifications not delivered to conversation |
| Is the stdio notification deadlock fixed? | PR #2654 is open but not yet merged |

### Recommended next steps

1. **Watch issue #36431** for a fix — this is the critical blocker for any channel implementation
2. **Test the Python low-level notification API** to confirm `notifications/claude/channel` can be sent from a FastMCP server via the underlying session
3. **Open a FastMCP issue** requesting a `channel` capability helper and `send_channel_notification()` convenience method
4. **Prototype with `--dangerously-load-development-channels`** once #36431 is resolved, using the Python SDK directly before FastMCP adds support

---

## Sources

- Claude Code Channels docs: https://code.claude.com/docs/en/channels
- Channels reference: https://code.claude.com/docs/en/channels-reference
- Python MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- FastMCP: https://github.com/jlowin/fastmcp
- PR #2654 (stdio notification deadlock): https://github.com/modelcontextprotocol/python-sdk/pull/2654
- Bug #36431 (notifications not delivered): https://github.com/anthropics/claude-code/issues/36431
- Bug #40729 (Discord same issue): https://github.com/anthropics/claude-code/issues/40729
- MCP server notifications discussion: https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1192
