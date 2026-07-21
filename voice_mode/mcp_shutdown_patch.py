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
"""

from __future__ import annotations

from contextlib import AsyncExitStack

import anyio
from fastmcp.server.low_level import LowLevelServer, MiddlewareServerSession


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
    than once on the same server."""
    low_level_server = mcp._mcp_server
    if isinstance(low_level_server, LowLevelServer) and not isinstance(
        low_level_server, _CancelOnTransportCloseLowLevelServer
    ):
        low_level_server.__class__ = _CancelOnTransportCloseLowLevelServer
