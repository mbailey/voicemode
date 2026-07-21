"""Tests for converse's behaviour when the MCP tool call is cancelled.

Context: VM-1026 / GH issue #337 -- pressing ESC during a `converse` call
used to disconnect the whole MCP server because `asyncio.CancelledError`
escaped the tool handler and tore down FastMCP's stdio transport. The fix
at the time was to catch `CancelledError` inside `converse()` and return a
normal string result instead of letting it propagate.

VM-2015 (successor bug, same root symptom -- ESC wedges the connection):
that "fix" was itself the bug. Catching a `CancelledError` inside a
coroutine does NOT clear the anyio `CancelScope` wrapping the in-flight MCP
request -- it stays cancelled, so the very next `await` anywhere further
down that same call (e.g. in a `finally` block doing cleanup) gets handed a
*fresh* `CancelledError` the code is no longer positioned to catch cleanly.
That is what actually escaped the request boundary and tore the server
down -- not the original one.

The correct fix is the opposite of VM-1026's: let `CancelledError` PROPAGATE
out of `converse()` uncaught. `mcp.server.lowlevel.server.Server._handle_request`
(unmodified by fastmcp) already has an `except
anyio.get_cancelled_exc_class(): if message.cancelled: ... return` that
absorbs a client-cancelled request's `CancelledError` exactly once, at the
correct boundary -- which is what actually keeps the stdio reader alive for
the next request. `converse()` just needs to get out of the way and still
run its cleanup (conch release, event logging) via `finally`.

These tests verify: cleanup still runs on cancellation, but the
`CancelledError` itself is allowed to propagate rather than being swallowed
into a normal string return.
"""

import asyncio

import pytest
from unittest.mock import patch


class TestConverseCancellation:
    """CancelledError must propagate so the MCP SDK's per-request cancel
    boundary absorbs it -- not be swallowed inside converse() itself."""

    @pytest.mark.asyncio
    async def test_cancelled_during_tts_reraises(self):
        """If TTS raises CancelledError, converse must let it propagate."""
        from voice_mode.tools.converse import converse

        with patch("voice_mode.core.text_to_speech") as mock_tts:
            mock_tts.side_effect = asyncio.CancelledError()

            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    with pytest.raises(asyncio.CancelledError):
                        await getattr(converse, 'fn', converse)(
                            message="Test message",
                            wait_for_response=False,
                        )

    @pytest.mark.asyncio
    async def test_cancellation_releases_conch(self):
        """Even though CancelledError propagates, the finally block must
        still run and release the conch so other agents can speak."""
        from voice_mode.tools.converse import converse
        from voice_mode.conch import Conch

        with patch("voice_mode.core.text_to_speech") as mock_tts:
            mock_tts.side_effect = asyncio.CancelledError()

            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    with pytest.raises(asyncio.CancelledError):
                        await getattr(converse, 'fn', converse)(
                            message="Test message",
                            wait_for_response=False,
                        )

        # No holder after cancellation — the finally block ran and released it.
        holder = Conch.get_holder()
        assert holder is None or holder.get("agent") != "converse", (
            f"Conch still held by converse after cancellation: {holder}"
        )

    @pytest.mark.asyncio
    async def test_outer_task_cancel_propagates(self):
        """Cancelling the converse task from the outside must still surface
        as CancelledError to the awaiter -- the tool must not convert it
        into a normal string result (that conversion is the VM-2015 bug)."""
        from voice_mode.tools.converse import converse

        # Make TTS hang so we can cancel it cleanly.
        hang_event = asyncio.Event()

        async def hang(*_args, **_kwargs):
            await hang_event.wait()
            return True, None, {}

        with patch("voice_mode.core.text_to_speech", new=hang):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    task = asyncio.create_task(
                        getattr(converse, 'fn', converse)(message="Hello", wait_for_response=False)
                    )
                    # Give it a moment to get into TTS
                    await asyncio.sleep(0.1)
                    task.cancel()

                    # Awaiting a cancelled task normally raises CancelledError.
                    # VM-2015: it must keep doing so -- that is what lets the
                    # MCP SDK's own per-request cancel handling absorb it at
                    # the correct boundary instead of converse() faking a
                    # normal return that leaves the anyio CancelScope
                    # cancelled underneath it.
                    with pytest.raises(asyncio.CancelledError):
                        await task
