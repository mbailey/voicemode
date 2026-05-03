# MCP SDK Channel/Notification Check — 2026-05-03

**Relevant to**: VM-970, VM-972 (VoiceMode inbound voice via Claude Code channel system)

## Summary

Active work-in-progress in the Python MCP SDK introduces server-to-client push notification infrastructure. **None is merged yet**, but a 4-part refactoring series (all draft PRs by contributor `maxisbey`) is ~67% complete and directly implements what VoiceMode needs.

## Python MCP SDK (modelcontextprotocol/python-sdk)

### Key PRs — All DRAFT, Not Yet Merged

**[PR #2452](https://github.com/modelcontextprotocol/python-sdk/pull/2452) — Add Dispatcher Protocol and DirectDispatcher** (Apr 16)
- Part 1 of 4. Introduces `Outbound` protocol with `notify(method, params)` and `send_raw_request(method, params)`.
- Also adds `NoBackChannelError` for transports (e.g. stateless HTTP) that can't handle server-initiated requests.
- Introduces `DirectDispatcher` for in-memory peer wiring (useful for testing).

**[PR #2458](https://github.com/modelcontextprotocol/python-sdk/pull/2458) — JSONRPCDispatcher** (Apr 16)
- Part 2 of 4. Wraps the wire protocol, sitting above transport and below MCP semantics.

**[PR #2460](https://github.com/modelcontextprotocol/python-sdk/pull/2460) — PeerMixin, BaseContext, Connection, server Context** (Apr 16)
- Part 3 of 4. **Most directly relevant.**
- `PeerMixin`: typed kwarg-style methods — `sample()`, `elicit_form()`, `elicit_url()`, `list_roots()`, `ping()` — enabling servers to send requests/notifications to clients proactively.
- `Connection`: per-client state with **best-effort notification methods** (`log()`, `send_resource_updated()`), gated on channel availability.
- `Context[LifespanT, TT]`: what handlers receive — combines `BaseContext`, `PeerMixin`, and typed request capabilities.
- Explicitly described as "enabling servers to send requests and notifications to connected clients proactively."

**[PR #2491](https://github.com/modelcontextprotocol/python-sdk/pull/2491) — ServerRunner — per-connection orchestrator** (Apr 22)
- Part 4 of 4. Bridges dispatcher layer and user handler layer; handles connection lifecycle.

### Status
- All 4 PRs are **draft** with 6/9 checklist tasks complete.
- No releases since v1.27.0 (Apr 2, 2025) include these features.
- The existing `notifications/cancelled` PRs (#2514, #2518) are separate — those are about cancellation protocol fixes, not server-push capabilities.

## FastMCP (jlowin/fastmcp)

No relevant work found. Latest releases (v3.2.x) focus on OAuth/auth hardening, interactive UI providers (`FastMCPApp`), and CodeMode. FastMCP wraps the Python MCP SDK, so it must wait for the SDK to ship these features before building on them.

## What This Means for VoiceMode

The Python MCP SDK is building exactly the infrastructure VoiceMode needs:
- A `notify()` API that servers can call to push messages to connected clients
- `Connection` objects with convenience notification methods
- Guard rails (`NoBackChannelError`) for transport types that don't support back-channels

**Action**: Monitor this PR series. When PR #2452 merges (it's Part 1 and unblocks everything else), the foundation is in. Watch for a release that includes these PRs — likely a v1.28.0 or similar.

No equivalent work exists in FastMCP yet; VoiceMode may need to call the underlying SDK APIs directly once merged, or wait for FastMCP to wrap them.

## Next Check

Re-run this check when any of PRs #2452, #2460, or #2491 are merged, or on 2026-05-10 (weekly cadence).
