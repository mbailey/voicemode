"""Tests for VM-2015's fastmcp LowLevelServer.run() cancellation patch.

fastmcp's LowLevelServer.run() (fastmcp/server/low_level.py) re-implements
the MCP SDK's dispatch loop but drops the SDK's
`finally: tg.cancel_scope.cancel()` (mcp/server/lowlevel/server.py:685-690)
around the task group that fans one task out per inbound message. Without
it, when the transport's incoming-message loop ends, the task group's
`__aexit__` just joins whatever handler tasks are still running instead of
cancelling them -- so shutdown can block indefinitely on a straggling
handler (e.g. VM-2015's orphaned recording thread).
"""

import asyncio

import anyio
import pytest

from voice_mode.mcp_shutdown_patch import (
    _CancelOnTransportCloseLowLevelServer,
    dispatch_until_closed,
    patch_cancel_on_transport_close,
)


class TestPatchCancelOnTransportClose:
    """Rebinding a FastMCP instance's low-level server class."""

    def test_rebinds_class(self):
        from fastmcp import FastMCP

        mcp = FastMCP("test-vm2015")
        assert not isinstance(mcp._mcp_server, _CancelOnTransportCloseLowLevelServer)

        patch_cancel_on_transport_close(mcp)

        assert isinstance(mcp._mcp_server, _CancelOnTransportCloseLowLevelServer)

    def test_idempotent(self):
        """Calling it twice on the same server must not error or double-wrap."""
        from fastmcp import FastMCP

        mcp = FastMCP("test-vm2015-idempotent")
        patch_cancel_on_transport_close(mcp)
        first_class = mcp._mcp_server.__class__
        patch_cancel_on_transport_close(mcp)

        assert mcp._mcp_server.__class__ is first_class

    def test_actual_server_is_patched(self):
        """The module-level `mcp` singleton voice_mode tools register
        against must already carry the patch (server.py wires it in at
        import time)."""
        from voice_mode.server import mcp

        assert isinstance(mcp._mcp_server, _CancelOnTransportCloseLowLevelServer)


class TestDispatchUntilClosed:
    """The extracted dispatch-loop-with-cancel-on-close behaviour, tested
    directly against a real anyio task group (no MCP session/transport
    needed) -- this is the actual bug fix."""

    @pytest.mark.asyncio
    async def test_cancels_in_flight_handler_when_stream_ends(self):
        """A handler still running when incoming_messages ends must be
        cancelled, not left to run to completion (which is exactly the
        VM-2015 orphaned-thread-blocks-teardown shape at the dispatch-loop
        level)."""
        handler_cancelled = asyncio.Event()

        async def hanging_dispatch(message, tag):
            try:
                # Simulate a handler coroutine that would otherwise run for
                # a long time (VM-2015's orphaned recording thread analog).
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        async def one_message_then_close():
            yield "only-message"
            # Async generator ends here -- simulates transport close.

        async with anyio.create_task_group() as tg:
            await dispatch_until_closed(tg, one_message_then_close(), hanging_dispatch, "tag")

        # dispatch_until_closed returned (and the `async with` block above
        # exited) promptly -- if the missing `finally: cancel()` bug were
        # present, this would hang for the full 3600s sleep instead.
        assert handler_cancelled.is_set(), (
            "handler task was not cancelled when the message stream ended -- "
            "the task group joined it instead (the VM-2015 fastmcp gap)"
        )

    @pytest.mark.asyncio
    async def test_cancels_on_iteration_error(self):
        """A raise from the incoming_messages loop itself must also cancel
        in-flight handlers, not just a clean end-of-stream."""
        handler_cancelled = asyncio.Event()

        async def hanging_dispatch(message, tag):
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        async def one_message_then_raise():
            yield "only-message"
            raise RuntimeError("transport blew up")

        # anyio's asyncio backend wraps the propagating error in an
        # ExceptionGroup once >=1 task is live in the group when it fails.
        with pytest.raises((RuntimeError, ExceptionGroup)) as excinfo:
            async with anyio.create_task_group() as tg:
                await dispatch_until_closed(tg, one_message_then_raise(), hanging_dispatch, "tag")

        if isinstance(excinfo.value, ExceptionGroup):
            assert any("transport blew up" in str(e) for e in excinfo.value.exceptions)
        else:
            assert "transport blew up" in str(excinfo.value)

        assert handler_cancelled.is_set()

    @pytest.mark.asyncio
    async def test_dispatches_every_message(self):
        """Sanity check: the loop still starts one task per message when
        nothing hangs -- the fix must not change normal dispatch."""
        seen = []

        async def quick_dispatch(message, tag):
            seen.append((message, tag))

        async def three_messages():
            for m in ("a", "b", "c"):
                yield m

        async with anyio.create_task_group() as tg:
            await dispatch_until_closed(tg, three_messages(), quick_dispatch, "tag")

        assert sorted(seen) == [("a", "tag"), ("b", "tag"), ("c", "tag")]
