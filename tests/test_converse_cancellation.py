"""Tests for converse's behaviour when the MCP tool call is cancelled.

Context: VM-1026 / GH issue #337 -- pressing ESC during a `converse` call
used to disconnect the whole MCP server because `asyncio.CancelledError`
escaped the tool handler and tore down FastMCP's stdio transport.

These tests verify that cancellation is caught inside the tool, cleanup
runs, and a well-formed string result is returned instead of the
exception escaping.
"""

import asyncio

import pytest
from unittest.mock import patch


class TestConverseCancellation:
    """CancelledError must be swallowed so the MCP server stays alive."""

    @pytest.mark.asyncio
    async def test_cancelled_during_tts_returns_cancellation_message(self):
        """If TTS raises CancelledError, converse must return cleanly."""
        from voice_mode.tools.converse import converse

        with patch("voice_mode.core.text_to_speech") as mock_tts:
            mock_tts.side_effect = asyncio.CancelledError()

            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    result = await converse.fn(
                        message="Test message",
                        wait_for_response=False,
                    )

        assert isinstance(result, str), (
            "converse must return a string on cancellation, not raise"
        )
        assert "cancel" in result.lower(), (
            f"Expected cancellation to be reflected in result, got: {result!r}"
        )

    @pytest.mark.asyncio
    async def test_cancellation_releases_conch(self):
        """After cancellation, the conch must be released so other agents can speak."""
        from voice_mode.tools.converse import converse
        from voice_mode.conch import Conch

        with patch("voice_mode.core.text_to_speech") as mock_tts:
            mock_tts.side_effect = asyncio.CancelledError()

            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    await converse.fn(
                        message="Test message",
                        wait_for_response=False,
                    )

        # No holder after cancellation — the finally block ran and released it.
        holder = Conch.get_holder()
        assert holder is None or holder.get("agent") != "converse", (
            f"Conch still held by converse after cancellation: {holder}"
        )

    @pytest.mark.asyncio
    async def test_outer_task_cancel_is_swallowed(self):
        """Cancelling the converse task from the outside must not raise past the await."""
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
                        converse.fn(message="Hello", wait_for_response=False)
                    )
                    # Give it a moment to get into TTS
                    await asyncio.sleep(0.1)
                    task.cancel()

                    # awaiting a cancelled task normally raises CancelledError.
                    # After our fix, converse catches it internally and returns,
                    # so the task completes with a string result rather than
                    # raising.
                    try:
                        result = await task
                    except asyncio.CancelledError:
                        pytest.fail(
                            "converse leaked CancelledError — would tear down FastMCP stdio"
                        )
                    assert isinstance(result, str)
                    assert "cancel" in result.lower()
