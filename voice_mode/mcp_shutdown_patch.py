"""VM-2015 -- restore the MCP SDK's transport-close cancellation semantics
that fastmcp's ``LowLevelServer.run()`` drops.

The upstream MCP SDK's dispatch loop
(``mcp.server.lowlevel.server.Server.run``, mcp/server/lowlevel/server.py)
fans one task per inbound message out onto a task group, then does::

    async with anyio.create_task_group() as tg:
        try:
            async for message in session.incoming_messages:
                tg.start_soon(self._handle_message, ...)
        finally:
            # Transport closed: cancel in-flight handlers. Without this the
            # TG join waits for them, and when they eventually try to
            # respond they hit a closed write stream.
            tg.cancel_scope.cancel()

fastmcp's ``LowLevelServer.run()`` (fastmcp/server/low_level.py) overrides
``run()`` -- to swap in its own ``MiddlewareServerSession`` -- and in doing
so re-implements this loop *without* that ``finally``. So when the
transport's ``incoming_messages`` loop ends (or raises), the task group's
``__aexit__`` just joins whatever handler tasks are still running instead of
cancelling them outright.

That is a real, if secondary, contributor to the VM-2015 wedge: pair it with
converse.py's "let CancelledError propagate instead of swallowing it" fix
(the primary fix -- see converse.py's ``_converse_core``/``_ask_turns_pipeline``
cancellation handling) and the recording-thread stop-flag (also converse.py)
so that IF a handler is still in flight when the transport loop exits, the
task group tears it down instead of blocking indefinitely.

There's no supported fastmcp extension point for this, so we restore it via
a local subclass and rebind an already-constructed ``LowLevelServer``
instance onto it (safe: the subclass adds no new instance attributes, so the
object's layout is unchanged) rather than editing fastmcp itself -- see the
task README's "Fix 1" for the sanctioned approach ("upstream fix, or a local
subclass").

FAILING LOUDLY (VM-2015 fix-001 review)
---------------------------------------
Subclassing a private, undocumented ``run()`` is version-fragile: our copy of
fastmcp's body can silently go stale on a ``fastmcp`` bump (pyproject pins
only ``>=3.2.0,<4``), either dropping whatever upstream added to ``run()`` or
re-shipping a patch upstream no longer needs. Two guards make that loud
instead of silent:

* ``upstream_run_drift()`` fingerprints ``LowLevelServer.run``'s source and
  reports any divergence from the version this subclass was copied from.
  ``patch_cancel_on_transport_close()`` logs it at ERROR, and
  ``tests/test_mcp_shutdown_patch.py`` asserts it is clean -- so a fastmcp
  bump fails CI with an explicit "re-sync this copy" message rather than
  quietly reintroducing VM-2015.
* the same test asserts upstream still *lacks* ``tg.cancel_scope.cancel()``.
  When fastmcp fixes this itself, the test fails and this whole module should
  be deleted.

Note the empirical scope of this patch, measured during review with
``scripts/repro-vm2015.sh 30``: with the patch disabled the repro still
PASSES (second converse after ESC reaches the server). The per-request fix in
``converse.py`` is what closes VM-2015; this module is defence in depth for
the *transport-close* path only.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from contextlib import AsyncExitStack

import anyio
from fastmcp.server.low_level import LowLevelServer, MiddlewareServerSession

logger = logging.getLogger("voicemode")

#: fastmcp version whose ``LowLevelServer.run()`` body this module's subclass
#: reproduces (plus the missing ``finally: tg.cancel_scope.cancel()``).
TESTED_FASTMCP_VERSION = "3.4.3"

#: sha256 of ``inspect.getsource(LowLevelServer.run)`` at that version.
UPSTREAM_RUN_SHA256 = "73334ad4b34ad6cb59e3f2c0d60adb96e09582b04534107bcce7134773e854a0"


def upstream_run_drift() -> str | None:
    """Return a human-readable reason if fastmcp's ``LowLevelServer.run()``
    no longer matches the implementation this module was copied from, else
    ``None``.

    Any drift means the subclass below may be re-implementing a stale body --
    re-copy it (and update :data:`UPSTREAM_RUN_SHA256` /
    :data:`TESTED_FASTMCP_VERSION`), or delete this module if upstream has
    restored the cancel-on-transport-close ``finally`` itself.
    """
    try:
        source = inspect.getsource(LowLevelServer.run)
    except (OSError, TypeError) as exc:  # pragma: no cover - source-less install
        return f"could not read fastmcp LowLevelServer.run source: {exc!r}"

    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest == UPSTREAM_RUN_SHA256:
        return None

    try:
        import fastmcp

        installed = getattr(fastmcp, "__version__", "unknown")
    except Exception:  # pragma: no cover - defensive
        installed = "unknown"

    return (
        f"fastmcp LowLevelServer.run() has changed (installed fastmcp="
        f"{installed}, this patch was copied from {TESTED_FASTMCP_VERSION}; "
        f"sha256 {digest} != {UPSTREAM_RUN_SHA256}). Re-sync "
        "voice_mode/mcp_shutdown_patch.py against the new upstream body, or "
        "delete it if upstream now cancels in-flight handlers on transport "
        "close (VM-2015)."
    )


async def dispatch_until_closed(tg, incoming_messages, dispatch, *dispatch_args) -> None:
    """Fan ``incoming_messages`` out onto ``tg`` via ``dispatch``, one task
    per message, then cancel ``tg``'s scope once the message stream ends
    (transport closed, or the loop raised) instead of leaving the task
    group's ``__aexit__`` to join whatever handler tasks are still running.

    Factored out of ``_CancelOnTransportCloseLowLevelServer.run()`` so it can
    be exercised directly in tests with a fake iterable and a fake dispatch
    coroutine, without needing a real MCP session/transport.
    """
    try:
        async for message in incoming_messages:
            tg.start_soon(dispatch, message, *dispatch_args)
    finally:
        tg.cancel_scope.cancel()


class _CancelOnTransportCloseLowLevelServer(LowLevelServer):
    """``LowLevelServer`` whose ``run()`` cancels in-flight handler tasks
    when the transport's incoming-message loop ends, matching the upstream
    MCP SDK's ``Server.run()`` (see module docstring)."""

    async def run(
        self,
        read_stream,
        write_stream,
        initialization_options,
        raise_exceptions: bool = False,
        stateless: bool = False,
    ):
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))
            session = await stack.enter_async_context(
                MiddlewareServerSession(
                    self.fastmcp,
                    read_stream,
                    write_stream,
                    initialization_options,
                    stateless=stateless,
                )
            )

            async with anyio.create_task_group() as tg:
                # Store task group on session for subscription tasks (SEP-1686)
                session._subscription_task_group = tg

                await dispatch_until_closed(
                    tg,
                    session.incoming_messages,
                    self._handle_message,
                    session,
                    lifespan_context,
                    raise_exceptions,
                )


def patch_cancel_on_transport_close(mcp) -> None:
    """Rebind ``mcp._mcp_server``'s class in place so its ``run()`` cancels
    in-flight handlers on transport close. Idempotent -- safe to call more
    than once on the same server.

    Never raises: a stdio MCP server that refuses to start is worse than one
    missing this defence-in-depth patch. Both failure modes (upstream body
    drifted, or the server is no longer a ``LowLevelServer``) are logged at
    ERROR and are asserted against in ``tests/test_mcp_shutdown_patch.py``,
    so they surface at CI time rather than silently at runtime.
    """
    drift = upstream_run_drift()
    if drift:
        logger.error("VM-2015 shutdown patch: %s", drift)

    low_level_server = getattr(mcp, "_mcp_server", None)
    if isinstance(low_level_server, _CancelOnTransportCloseLowLevelServer):
        return
    if not isinstance(low_level_server, LowLevelServer):
        logger.error(
            "VM-2015 shutdown patch NOT applied: %s._mcp_server is %r, not a "
            "fastmcp LowLevelServer -- in-flight handlers will not be "
            "cancelled on transport close.",
            type(mcp).__name__,
            type(low_level_server).__name__,
        )
        return

    low_level_server.__class__ = _CancelOnTransportCloseLowLevelServer
