# MCP SDK Channel Notification Check — 2026-04-21

**Relevant to:** VM-970, VM-972  
**Question:** Have Python MCP SDK or FastMCP added support for server-to-client push notifications (channel notifications)?

## Summary

No new **released** support for server-initiated channel notifications was found today. However, an open PR in the Python MCP SDK is directly relevant and worth tracking.

---

## Python MCP SDK (`modelcontextprotocol/python-sdk`)

**Latest release:** v1.27.0 (April 2, 2026) — bug fixes and maintenance only; no new notification APIs.

### Notable open PR: #2460 — `feat: PeerMixin, BaseContext, Connection, server Context`

- **Status:** Open (not yet merged)
- **URL:** https://github.com/modelcontextprotocol/python-sdk/pull/2460
- **What it adds:**
  - `Connection` class with convenience notification methods: `log`, `send_*_list_changed`, `send_resource_updated`
  - Best-effort notify operations that "never raise"
  - `PeerMixin` with typed server→client methods: `sample`, `elicit_form`, `elicit_url`, `list_roots`, `ping`
  - `BaseContext` wrapper that forwards `send_raw_request` and `notify`
- **Relevance:** This is the most significant open work toward a clean server-to-client notification API. It builds on existing dispatcher infrastructure. It does **not** add new transport-level push mechanisms but provides a typed interface for the existing `notifications/*` spec messages.

### Open issue: #710 — `how to trigger a resources_changed or listChanged`

- Still open, labelled "needs decision", in the FastMCP milestone
- No resolution yet on how to cleanly trigger list-change notifications from user code

---

## FastMCP (`PrefectHQ/fastmcp`)

**Latest release:** v3.2.4 (April 14, 2026)

Recent focus areas: OAuth/auth providers, OpenAPI integration, interactive UIs (`FastMCPApp`), security hardening, and `CodeMode` for tool discovery via Python sandbox.

**No new server-to-client notification or channel APIs found.** FastMCP wraps the underlying Python MCP SDK, so it depends on the SDK adding support first.

---

## What This Means for VoiceMode

- No released library can be dropped in today to enable inbound voice via MCP channel notifications.
- PR #2460 is the signal to watch — if it merges, it unlocks a clean `context.notify(...)` API that VoiceMode could use to push voice-related server notifications to the client.
- Issue #710 tracks the list-changed notification gap; not directly relevant to inbound voice but same underlying need.

## Recommended Next Check

Re-check after v1.28.0 of the Python MCP SDK releases, or when PR #2460 merges.
