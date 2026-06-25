"""Tests for the control-channel playback interrupt (VM-1676, impl-playback-interrupt).

These verify that the TTS streaming write loops -- and the buffered fallback
player -- honour the process-wide control state: a ``stop`` breaks the loop
within one chunk and aborts the stream, a ``pause`` holds without busy-spinning
and resumes cleanly, and natural completion is unaffected. No real audio: the
``sounddevice`` OutputStream is mocked and the TTS byte source is faked.

Scope note: features wire the *activation* of the control channel (the socket
listener + converse reset) elsewhere; here we drive the shared
``get_control_state()`` singleton directly, which is exactly what those callers
will do at runtime.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from voice_mode import streaming
from voice_mode.streaming import (
    StreamMetrics,
    _abort_stream,
    _poll_control_channel,
    stream_cartesia_pcm,
    stream_pcm_audio,
    stream_with_buffering,
)
from voice_mode.control_channel import get_control_state


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_control_state():
    """Keep the process-wide control singleton clean around every test.

    It is a module-level singleton, so a stray ``stop`` could otherwise leak
    into an unrelated test (or the broader suite). Reset before and after.
    """
    get_control_state().reset()
    yield
    get_control_state().reset()


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    """Shrink the pause poll interval so pause/resume tests are quick."""
    monkeypatch.setattr(streaming, "CONTROL_POLL_INTERVAL", 0.01)


def _pcm_chunks(n: int) -> list:
    """N small, even-length PCM byte chunks (np.frombuffer needs even length)."""
    return [bytes([i % 256, (i * 7) % 256]) * 8 for i in range(n)]


class _FakeStreamingResponse:
    """Stand-in for openai's streaming-response async context manager."""

    def __init__(self, chunks, on_chunk=None):
        self._chunks = chunks
        self._on_chunk = on_chunk
        self.consumed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def iter_bytes(self, chunk_size=None):
        for i, chunk in enumerate(self._chunks):
            # Fire the hook *before* yielding so a test can flip the control
            # state at a precise chunk boundary, then let the caller observe it.
            if self._on_chunk is not None:
                self._on_chunk(i)
            self.consumed.append(i)
            yield chunk
            await asyncio.sleep(0)  # give the event loop / pause-hold a turn


def _make_openai_client(chunks, on_chunk=None):
    """A MagicMock openai client whose streaming create() yields ``chunks``."""
    resp = _FakeStreamingResponse(chunks, on_chunk)
    client = MagicMock()
    client.audio.speech.with_streaming_response.create.return_value = resp
    return client, resp


def _make_mock_stream():
    """A mock sd.OutputStream with the methods the loops call."""
    stream = MagicMock()
    stream.latency = 0.0
    return stream


# --------------------------------------------------------------------------
# _poll_control_channel (the per-chunk seam) -- unit
# --------------------------------------------------------------------------

class TestPollControlChannel:
    async def test_running_returns_false_immediately(self):
        # Default singleton state is running -> no stop, no hold.
        assert await _poll_control_channel() is False

    async def test_stopped_returns_true(self):
        get_control_state().request_stop()
        assert await _poll_control_channel() is True

    async def test_paused_then_resumed_returns_false(self):
        state = get_control_state()
        state.request_pause()

        task = asyncio.create_task(_poll_control_channel())
        await asyncio.sleep(0.05)
        # Still holding while paused.
        assert not task.done()

        state.request_resume()
        # Resumes promptly and signals "keep playing".
        assert await asyncio.wait_for(task, timeout=1.0) is False

    async def test_paused_then_stopped_returns_true(self):
        state = get_control_state()
        state.request_pause()

        task = asyncio.create_task(_poll_control_channel())
        await asyncio.sleep(0.05)
        assert not task.done()

        state.request_stop()
        assert await asyncio.wait_for(task, timeout=1.0) is True


# --------------------------------------------------------------------------
# _abort_stream -- unit
# --------------------------------------------------------------------------

class TestAbortStream:
    def test_prefers_abort(self):
        stream = MagicMock()
        _abort_stream(stream)
        stream.abort.assert_called_once()
        stream.stop.assert_not_called()

    def test_falls_back_to_stop_when_abort_raises(self):
        stream = MagicMock()
        stream.abort.side_effect = RuntimeError("no abort")
        _abort_stream(stream)
        stream.stop.assert_called_once()

    def test_swallows_all_errors(self):
        stream = MagicMock()
        stream.abort.side_effect = RuntimeError("boom")
        stream.stop.side_effect = RuntimeError("also boom")
        # Must not raise -- teardown can't mask the stop.
        _abort_stream(stream)


# --------------------------------------------------------------------------
# stream_pcm_audio -- integration over a mocked OutputStream
# --------------------------------------------------------------------------

class TestStreamPcmAudio:
    async def test_natural_completion_unaffected(self):
        chunks = _pcm_chunks(5)
        client, resp = _make_openai_client(chunks)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="hello", openai_client=client, request_params={}
            )

        assert success is True
        assert metrics.control_stopped is False
        # Every chunk written; normal drain (stop), no abort.
        assert mock_stream.write.call_count == 5
        mock_stream.stop.assert_called_once()
        mock_stream.abort.assert_not_called()

    async def test_stop_breaks_within_one_chunk(self):
        chunks = _pcm_chunks(6)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_stop(hint="switch-to-text")

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="hello", openai_client=client, request_params={}
            )

        # Returns normally (True) but flags the control stop.
        assert success is True
        assert metrics.control_stopped is True
        # Only chunks 0 and 1 were written; the stop at chunk 2 broke before write.
        assert mock_stream.write.call_count == 2
        # Stopped within one chunk of the request: chunk 2 read, chunks 3+ never.
        assert resp.consumed == [0, 1, 2]
        # Aborted (discard buffered), not drained.
        mock_stream.abort.assert_called_once()

    async def test_pause_holds_then_resumes(self):
        chunks = _pcm_chunks(4)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_pause()

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            task = asyncio.create_task(
                stream_pcm_audio(text="hello", openai_client=client, request_params={})
            )
            await asyncio.sleep(0.1)
            # Held at the pause: chunks 0,1 written, not finished.
            assert not task.done()
            assert mock_stream.write.call_count == 2

            get_control_state().request_resume()
            success, metrics = await asyncio.wait_for(task, timeout=2.0)

        assert success is True
        assert metrics.control_stopped is False
        # All four chunks eventually written after resume.
        assert mock_stream.write.call_count == 4
        mock_stream.stop.assert_called_once()
        mock_stream.abort.assert_not_called()


# --------------------------------------------------------------------------
# stream_cartesia_pcm -- integration
# --------------------------------------------------------------------------

class TestStreamCartesiaPcm:
    async def test_stop_breaks_within_one_chunk(self):
        chunks = _pcm_chunks(6)
        consumed = []

        async def fake_stream(text, voice_id, sample_rate, speed):
            for i, chunk in enumerate(chunks):
                if i == 2:
                    get_control_state().request_stop()
                consumed.append(i)
                yield chunk
                await asyncio.sleep(0)

        mock_stream = _make_mock_stream()
        with patch("voice_mode.cartesia_tts.stream", new=fake_stream), \
             patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_cartesia_pcm(text="hi", voice_id="v")

        assert success is True
        assert metrics.control_stopped is True
        assert mock_stream.write.call_count == 2
        assert consumed == [0, 1, 2]
        mock_stream.abort.assert_called_once()

    async def test_natural_completion_unaffected(self):
        chunks = _pcm_chunks(3)

        async def fake_stream(text, voice_id, sample_rate, speed):
            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0)

        mock_stream = _make_mock_stream()
        with patch("voice_mode.cartesia_tts.stream", new=fake_stream), \
             patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_cartesia_pcm(text="hi", voice_id="v")

        assert success is True
        assert metrics.control_stopped is False
        assert mock_stream.write.call_count == 3
        mock_stream.stop.assert_called_once()
        mock_stream.abort.assert_not_called()


# --------------------------------------------------------------------------
# stream_with_buffering -- integration (opus path skips mid-loop decode)
# --------------------------------------------------------------------------

class TestStreamWithBuffering:
    async def test_stop_skips_remaining_decode(self):
        chunks = _pcm_chunks(6)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_stop(message="text mode please")

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_with_buffering(
                text="hello",
                openai_client=client,
                request_params={"response_format": "opus"},
            )

        assert success is True
        assert metrics.control_stopped is True
        # Broke within one chunk of the stop; never reached the final decode/write.
        assert resp.consumed == [0, 1, 2]
        mock_stream.write.assert_not_called()

    async def test_natural_completion_unaffected(self):
        # Tiny opus "stream": never crosses the 32KB mid-loop decode threshold,
        # so the final-buffer decode runs. Patch AudioSegment so no real codec
        # is needed -- we only care that the control path leaves it untouched.
        chunks = _pcm_chunks(3)
        client, resp = _make_openai_client(chunks)
        mock_stream = _make_mock_stream()

        fake_audio = MagicMock()
        fake_audio.frame_rate = 24000
        fake_audio.sample_width = 2
        fake_audio.get_array_of_samples.return_value = [0, 0, 0, 0]

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream), \
             patch.object(streaming, "AudioSegment") as mock_seg:
            mock_seg.from_file.return_value = fake_audio
            success, metrics = await stream_with_buffering(
                text="hello",
                openai_client=client,
                request_params={"response_format": "opus"},
            )

        assert success is True
        assert metrics.control_stopped is False
        # Final buffer decoded and written once; no abort.
        mock_stream.write.assert_called_once()
        mock_stream.abort.assert_not_called()


# --------------------------------------------------------------------------
# core._wait_for_player_with_control -- the buffered (callback player) path
# --------------------------------------------------------------------------

class _FakePlayer:
    def __init__(self):
        self.playback_complete = threading.Event()
        self.stop = MagicMock()
        self.wait = MagicMock()


class TestWaitForPlayerWithControl:
    async def test_natural_completion_calls_wait(self):
        from voice_mode.core import _wait_for_player_with_control

        player = _FakePlayer()
        player.playback_complete.set()  # already finished

        result = await _wait_for_player_with_control(player)

        assert result is False
        player.wait.assert_called_once()
        player.stop.assert_not_called()

    async def test_control_stop_calls_player_stop(self):
        from voice_mode.core import _wait_for_player_with_control

        player = _FakePlayer()  # never completes naturally
        get_control_state().request_stop()

        result = await _wait_for_player_with_control(player)

        assert result is True
        player.stop.assert_called_once()
        player.wait.assert_not_called()

    async def test_stop_mid_drain(self):
        from voice_mode.core import _wait_for_player_with_control

        player = _FakePlayer()

        async def stop_soon():
            await asyncio.sleep(0.03)
            get_control_state().request_stop()

        asyncio.create_task(stop_soon())
        result = await asyncio.wait_for(_wait_for_player_with_control(player), timeout=2.0)

        assert result is True
        player.stop.assert_called_once()
