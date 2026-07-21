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
    TESTED_FASTMCP_VERSION,
    _CancelOnTransportCloseLowLevelServer,
    dispatch_until_closed,
    patch_cancel_on_transport_close,
    upstream_run_drift,
)


class TestUpstreamDriftGuard:
    """VM-2015 fix-001 review: subclassing fastmcp's private ``run()`` is
    version-fragile and would otherwise fail SILENTLY on a fastmcp bump
    (pyproject pins only ``fastmcp>=3.2.0,<4``). These two tests are the
    loud failure -- they break in CI the moment upstream moves."""

    def test_upstream_run_body_has_not_drifted(self):
        drift = upstream_run_drift()
        assert drift is None, drift

    def test_upstream_still_lacks_the_cancel(self):
        """If fastmcp restores the SDK's ``finally: tg.cancel_scope.cancel()``
        itself, voice_mode/mcp_shutdown_patch.py is dead code and should be
        deleted (along with these tests)."""
        import inspect

        from fastmcp.server.low_level import LowLevelServer

        source = inspect.getsource(LowLevelServer.run)
        assert "cancel_scope.cancel()" not in source, (
            "fastmcp's LowLevelServer.run() now cancels in-flight handlers on "
            "transport close by itself -- delete voice_mode/mcp_shutdown_patch.py "
            f"and its wiring in server.py (patch was written against fastmcp "
            f"{TESTED_FASTMCP_VERSION})."
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


async def _drive_until_transport_close(apply_patch: bool, settle: float = 3.0):
    """Run a REAL fastmcp server over in-memory MCP streams, get a tool call
    in flight, then close the client->server stream (the transport dying under
    an in-flight handler) and report what happened.

    Returns ``(server_run_returned, handler_was_cancelled)`` sampled *before*
    any outer cancellation, so the two arms differ only by the patch.
    """
    from fastmcp import FastMCP
    from mcp.shared.memory import create_client_server_memory_streams
    from mcp.shared.message import SessionMessage
    import mcp.types as types

    handler_started = anyio.Event()
    handler_cancelled = anyio.Event()
    server_returned = anyio.Event()

    mcp = FastMCP("vm2015-transport-close")

    @mcp.tool
    async def slow_tool() -> str:
        """Stand-in for converse()'s long recording: in flight, not done."""
        handler_started.set()
        try:
            await anyio.sleep(60)
        except anyio.get_cancelled_exc_class():
            handler_cancelled.set()
            raise
        return "never reached"  # pragma: no cover

    if apply_patch:
        patch_cancel_on_transport_close(mcp)

    def _request(rid, method, params):
        return SessionMessage(
            types.JSONRPCMessage(
                types.JSONRPCRequest(jsonrpc="2.0", id=rid, method=method, params=params)
            )
        )

    def _notification(method):
        return SessionMessage(
            types.JSONRPCMessage(
                types.JSONRPCNotification(jsonrpc="2.0", method=method, params={})
            )
        )

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        async def _serve():
            await mcp._mcp_server.run(
                server_read,
                server_write,
                mcp._mcp_server.create_initialization_options(),
            )
            server_returned.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_serve)

            await client_write.send(_request(1, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "vm2015-test", "version": "0"},
            }))
            with anyio.fail_after(10):
                await client_read.receive()  # initialize result
            await client_write.send(_notification("notifications/initialized"))
            await client_write.send(_request(2, "tools/call", {
                "name": "slow_tool", "arguments": {},
            }))

            with anyio.fail_after(10):
                await handler_started.wait()

            # THE EVENT UNDER TEST: the client vanishes mid-call. The server's
            # incoming-message loop hits EOF with a handler still running.
            await client_write.aclose()

            with anyio.move_on_after(settle):
                await server_returned.wait()

            result = (server_returned.is_set(), handler_cancelled.is_set())
            tg.cancel_scope.cancel()

    return result


class TestTransportCloseCancelsInFlightHandler:
    """VM-2015 fix-001 round 2, question D -- what this module actually
    defends, end to end through a real fastmcp server.

    The per-request fix in converse.py closes VM-2015 itself (measured: the
    repro passes with this module disabled). What it does NOT cover is the
    client vanishing *without* cancelling first -- the agent is killed, the
    terminal closes, the pipe breaks. Then nothing ever cancels the in-flight
    handler, so the recording thread's stop flag is never set and the orphaned
    server keeps the microphone for the rest of ``listen_duration_max``,
    then spends an STT call transcribing audio nobody asked for.

    Measured at process level with scripts/probe-transport-close.py (task dir,
    listen_duration_max=20s): unpatched the process lived 17.5s past the close
    and logged RECORDING_END -> STT_START -> STT_COMPLETE; patched it exited in
    0.4s having logged TOOL_CANCELLED. These two tests pin that difference at
    the dispatch-loop seam so it stays fixed.
    """

    @pytest.mark.asyncio
    async def test_patched_server_cancels_handler_and_returns(self):
        returned, cancelled = await _drive_until_transport_close(apply_patch=True)

        assert cancelled, (
            "in-flight handler was not cancelled when the transport closed -- "
            "a real recording thread would keep the mic for listen_duration_max"
        )
        assert returned, "LowLevelServer.run() did not return after transport close"

    @pytest.mark.asyncio
    async def test_unpatched_fastmcp_leaves_the_handler_running(self):
        """The other half of the proof: stock fastmcp does NOT do this, so the
        module is load-bearing rather than decorative. If this test starts
        failing, upstream has fixed it -- delete this module (see
        ``test_upstream_still_lacks_the_cancel``)."""
        returned, cancelled = await _drive_until_transport_close(apply_patch=False)

        assert not cancelled and not returned, (
            "stock fastmcp cancelled the in-flight handler on transport close "
            "-- voice_mode/mcp_shutdown_patch.py is now redundant and should "
            "be deleted"
        )


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
