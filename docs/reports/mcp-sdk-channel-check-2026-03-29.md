# MCP SDK Channel/Notification Check — 2026-03-29

**Purpose:** Monitor Python MCP SDK and FastMCP for server-to-client notification support
**Context:** VoiceMode tasks VM-970, VM-972 — needed for inbound voice messages via Claude Code channel system
**Window checked:** 2026-03-15 to 2026-03-29

---

## Summary

**Verdict: FOUND_UPDATES** — Active development on server-to-client notification primitives, but nothing has shipped in a release yet.

---

## Python MCP SDK (`modelcontextprotocol/python-sdk`)

### PR #2281 — "Add client callbacks for list_changed notifications"
- **URL:** https://github.com/modelcontextprotocol/python-sdk/pull/2281
- **State:** Open (not yet merged)
- **Created:** 2026-03-12
- **Author:** omar-y-abdi
- **Description:** Adds optional callback parameters to `ClientSession` for handling server-initiated list-change notifications that were previously silently dropped. Introduces:
  - `tools_list_changed_callback`
  - `resources_list_changed_callback`
  - `prompts_list_changed_callback`
- **Relevance:** Foundational client-side plumbing — clients must be able to receive/handle server push before servers can usefully send. Addresses issue #2107.

### Recent releases
- Latest: **v1.26.0** (2026-01-24) — no notification-related changes
- No new releases in the last 14 days

---

## FastMCP (`PrefectHQ/fastmcp`)

### Issue #3641 — MCP conformance: resource subscriptions (subscribe/unsubscribe)
- **URL:** https://github.com/PrefectHQ/fastmcp/issues/3641
- **State:** Open
- **Created:** 2026-03-27
- **Description:** The MCP conformance suite now explicitly tracks `resources/subscribe` and `resources/unsubscribe` as expected failures in FastMCP. Formal acknowledgment that resource subscription (the primary server-to-client notification mechanism) is a known gap.

### PR #3645 — "feat: implement resource subscriptions"
- **URL:** https://github.com/PrefectHQ/fastmcp/pull/3645
- **State:** Closed without merge (2026-03-27)
- **Author:** syhstanley
- **Description:** Community contribution proposing full resource subscription support:
  - `ResourceSubscriptionRegistry` for tracking active subscriptions
  - `ctx.notify_resource_updated(uri)` — a context method enabling servers to **push change notifications to subscribed clients**
- **Relevance:** Most direct implementation attempt to date. Closed without merge (likely needs revision), but the issue remains open indicating active intent.

### Recent releases
- Latest: **v3.1.1** (2026-03-14) — pydantic pinning fix only, no notification changes

---

## Assessment

| Item | Status |
|------|--------|
| python-sdk client callbacks for server notifications | PR open, under review |
| FastMCP resource subscription tracking | Issue open, PR closed/needs rework |
| Any of this shipped in a release | No |

The activity level on server-to-client notifications increased noticeably in the last 7 days, particularly in FastMCP. The key building block (`ctx.notify_resource_updated()`) has been prototyped in PR #3645. Once that work matures and the python-sdk PR #2281 merges, the path to VoiceMode channel support becomes much clearer.

---

## Recommendation

Watch:
- python-sdk PR #2281 for merge
- FastMCP issue #3641 for a replacement PR (the closed #3645 shows the team knows what's needed)

When `resources/subscribe` lands in FastMCP + a release is tagged, VoiceMode can implement inbound channel notifications (VM-970/VM-972).
