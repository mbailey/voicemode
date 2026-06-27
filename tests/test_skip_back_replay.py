"""Tests for skip-back replay -- the CD-style transport (VM-1685, impl-replay).

This wires the ``skip_back`` control command (impl-command) to the utterance
history buffer (impl-buffer): a press re-plays already-spoken audio with
CD-player semantics -- the first press restarts the most-recent *completed*
utterance, each further press steps one entry back through the buffer. Replay is
a **playback-layer** operation only: no STT, no model call, no new agent turn,
and it **composes with pause**.

Three seams are covered, mirroring tests/test_playback_interrupt.py (mocked
``sounddevice`` OutputStream, faked TTS byte source, control state driven
directly):

* ``streaming._poll_control_channel`` / the streaming write loops -- a pending
  transport request breaks playback (abort, not drain) and flags a *transport
  interrupt* distinct from a control stop, without capturing the aborted partial.
* ``streaming.play_cached_utterance`` -- replays a cached record's PCM through
  the normal playback path, honouring pause / stop / a further skip_back.
* ``converse._drain_skip_back`` and ``converse`` end-to-end -- the CD cursor and
  the replay-then-listen loop, proving no STT runs for a replay.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_mode import streaming
from voice_mode.streaming import (
    REPLAY_COMPLETED,
    REPLAY_STOPPED,
    REPLAY_TRANSPORT,
    _poll_control_channel,
    play_cached_utterance,
    stream_cartesia_pcm,
    stream_pcm_audio,
)
from voice_mode.control_channel import COMMAND_SKIP_BACK, get_control_state
from voice_mode.history_buffer import UtteranceRecord, get_history_buffer


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singletons():
    """Keep the process-wide control state + history buffer clean per test."""
    get_control_state().reset()
    get_history_buffer().clear()
    yield
    get_control_state().reset()
    get_history_buffer().clear()


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    """Shrink the pause poll interval so pause/resume tests are quick."""
    monkeypatch.setattr(streaming, "CONTROL_POLL_INTERVAL", 0.01)


def _pcm_chunks(n: int) -> list:
    """N small, even-length PCM byte chunks (np.frombuffer needs even length)."""
    return [bytes([i % 256, (i * 7) % 256]) * 8 for i in range(n)]


def _record(text: str, nbytes: int = 64, sample_rate: int = 24000) -> UtteranceRecord:
    """A cached utterance record with ``nbytes`` of arbitrary 16-bit PCM."""
    return UtteranceRecord(
        text=text,
        pcm_bytes=b"\x01\x00" * (nbytes // 2),
        sample_rate=sample_rate,
        channels=1,
        timestamp=0.0,
    )


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
            if self._on_chunk is not None:
                self._on_chunk(i)
            self.consumed.append(i)
            yield chunk
            await asyncio.sleep(0)


def _make_openai_client(chunks, on_chunk=None):
    resp = _FakeStreamingResponse(chunks, on_chunk)
    client = MagicMock()
    client.audio.speech.with_streaming_response.create.return_value = resp
    return client, resp


def _make_mock_stream():
    stream = MagicMock()
    stream.latency = 0.0
    return stream


# --------------------------------------------------------------------------
# _poll_control_channel -- a transport request breaks playback
# --------------------------------------------------------------------------

class TestPollTransport:
    async def test_pending_transport_returns_true(self):
        get_control_state().request_skip_back()
        # Breaks playback like a stop, but leaves the request pending for converse.
        assert await _poll_control_channel() is True
        assert get_control_state().pending_transport == COMMAND_SKIP_BACK

    async def test_transport_does_not_consume_the_request(self):
        get_control_state().request_skip_back()
        await _poll_control_channel()
        # _poll only peeks -- converse consumes via take_transport_request.
        assert get_control_state().take_transport_request() == COMMAND_SKIP_BACK

    async def test_transport_while_paused_breaks_the_hold(self):
        """'pause, then skip_back' -- a transport press wakes the pause hold."""
        state = get_control_state()
        state.request_pause()

        task = asyncio.create_task(_poll_control_channel())
        await asyncio.sleep(0.05)
        assert not task.done()  # held on the pause

        state.request_skip_back()
        # The transport press ends the hold (returns True to break and replay).
        assert await asyncio.wait_for(task, timeout=1.0) is True
        assert state.pending_transport == COMMAND_SKIP_BACK


# --------------------------------------------------------------------------
# play_cached_utterance -- the replay player
# --------------------------------------------------------------------------

class TestPlayCachedUtterance:
    async def test_empty_pcm_is_a_noop(self):
        record = UtteranceRecord(
            text="", pcm_bytes=b"", sample_rate=24000, channels=1, timestamp=0.0
        )
        with patch.object(streaming.sd, "OutputStream") as mk:
            assert await play_cached_utterance(record) == REPLAY_COMPLETED
            mk.assert_not_called()  # no device opened for empty audio

    async def test_natural_completion_drains_not_aborts(self):
        record = _record("hello", nbytes=streaming.STREAM_CHUNK_SIZE * 3)
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            reason = await play_cached_utterance(record)

        assert reason == REPLAY_COMPLETED
        assert mock_stream.write.call_count == 3   # three frame-aligned chunks
        mock_stream.stop.assert_called_once()      # drained
        mock_stream.abort.assert_not_called()

    async def test_does_not_capture_into_history_buffer(self):
        """A replay re-plays; it must never append a new history entry."""
        buf = get_history_buffer()
        record = _record("hello", nbytes=128)
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            await play_cached_utterance(record)
        assert len(buf) == 0

    async def test_stop_mid_replay_aborts(self):
        record = _record("hello", nbytes=streaming.STREAM_CHUNK_SIZE * 4)
        mock_stream = _make_mock_stream()

        writes = []

        def on_write(_arr):
            writes.append(1)
            if len(writes) == 1:
                get_control_state().request_stop()

        mock_stream.write.side_effect = on_write
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            reason = await play_cached_utterance(record)

        assert reason == REPLAY_STOPPED
        mock_stream.abort.assert_called_once()     # cut, not drained
        mock_stream.stop.assert_not_called()

    async def test_further_skip_back_mid_replay_steps_past(self):
        record = _record("hello", nbytes=streaming.STREAM_CHUNK_SIZE * 4)
        mock_stream = _make_mock_stream()

        writes = []

        def on_write(_arr):
            writes.append(1)
            if len(writes) == 1:
                get_control_state().request_skip_back()

        mock_stream.write.side_effect = on_write
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            reason = await play_cached_utterance(record)

        # A further press cuts this replay so the cursor can step back again.
        assert reason == REPLAY_TRANSPORT
        mock_stream.abort.assert_called_once()
        # Request left pending for the drain loop to consume.
        assert get_control_state().pending_transport == COMMAND_SKIP_BACK

    async def test_composes_with_pause(self):
        """A pause mid-replay holds; resume plays it out to the end."""
        record = _record("hello", nbytes=streaming.STREAM_CHUNK_SIZE * 3)
        mock_stream = _make_mock_stream()

        writes = []

        def on_write(_arr):
            writes.append(1)
            if len(writes) == 1:
                get_control_state().request_pause()

        mock_stream.write.side_effect = on_write
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            task = asyncio.create_task(play_cached_utterance(record))
            await asyncio.sleep(0.1)
            assert not task.done()                 # held on the pause
            assert len(writes) == 1

            get_control_state().request_resume()
            reason = await asyncio.wait_for(task, timeout=2.0)

        assert reason == REPLAY_COMPLETED
        assert len(writes) == 3                     # all chunks written after resume
        mock_stream.stop.assert_called_once()
        mock_stream.abort.assert_not_called()


# --------------------------------------------------------------------------
# streaming write loops -- a skip_back aborts the in-flight utterance
# --------------------------------------------------------------------------

class TestStreamTransportInterrupt:
    async def test_pcm_skip_back_flags_transport_not_stop(self):
        chunks = _pcm_chunks(6)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_skip_back()

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="hello", openai_client=client, request_params={}
            )

        assert success is True
        assert metrics.transport_interrupted is True
        assert metrics.control_stopped is False     # a transport press is NOT a stop
        assert mock_stream.write.call_count == 2     # broke within one chunk
        assert resp.consumed == [0, 1, 2]
        mock_stream.abort.assert_called_once()       # aborted, not drained

    async def test_pcm_skip_back_does_not_capture_partial(self):
        """The aborted in-flight utterance must NOT enter the history buffer."""
        buf = get_history_buffer()

        def on_chunk(i):
            if i == 1:
                get_control_state().request_skip_back()

        client, resp = _make_openai_client(_pcm_chunks(5), on_chunk)
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            await stream_pcm_audio(text="partial", openai_client=client, request_params={})

        assert len(buf) == 0       # nothing captured -- replay targets completed entries only

    async def test_pcm_pause_then_skip_back_breaks_and_aborts(self):
        """'pause, then skip_back' breaks the pause-hold inside the write loop."""
        chunks = _pcm_chunks(4)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_pause()

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            task = asyncio.create_task(
                stream_pcm_audio(text="hi", openai_client=client, request_params={})
            )
            await asyncio.sleep(0.1)
            assert not task.done()                  # held at the pause

            get_control_state().request_skip_back()
            success, metrics = await asyncio.wait_for(task, timeout=2.0)

        assert success is True
        assert metrics.transport_interrupted is True
        assert metrics.control_stopped is False
        mock_stream.abort.assert_called_once()

    async def test_stop_wins_over_pending_skip_back(self):
        """A stop latched alongside a stale skip_back is handled as a stop."""
        def on_chunk(i):
            if i == 1:
                # A transport press is queued, then a stop arrives -- stop wins.
                get_control_state().request_skip_back()
                get_control_state().request_stop(hint="switch-to-text")

        client, resp = _make_openai_client(_pcm_chunks(5), on_chunk)
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="x", openai_client=client, request_params={}
            )

        assert success is True
        assert metrics.control_stopped is True          # the stop wins
        assert metrics.transport_interrupted is False
        mock_stream.abort.assert_called_once()

    async def test_cartesia_skip_back_flags_transport(self):
        chunks = _pcm_chunks(6)
        consumed = []

        async def fake_stream(text, voice_id, sample_rate, speed):
            for i, chunk in enumerate(chunks):
                if i == 2:
                    get_control_state().request_skip_back()
                consumed.append(i)
                yield chunk
                await asyncio.sleep(0)

        mock_stream = _make_mock_stream()
        with patch("voice_mode.cartesia_tts.stream", new=fake_stream), \
             patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_cartesia_pcm(text="hi", voice_id="v")

        assert success is True
        assert metrics.transport_interrupted is True
        assert metrics.control_stopped is False
        assert mock_stream.write.call_count == 2
        mock_stream.abort.assert_called_once()

    async def test_natural_completion_still_captures(self):
        """Regression: a normal finish still records into the history buffer."""
        buf = get_history_buffer()
        client, resp = _make_openai_client(_pcm_chunks(3))
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="done", openai_client=client, request_params={}
            )

        assert success is True
        assert metrics.transport_interrupted is False
        assert len(buf) == 1 and buf.latest().text == "done"


# --------------------------------------------------------------------------
# converse._drain_skip_back -- the CD cursor over the history buffer
# --------------------------------------------------------------------------

def _populate_buffer(*texts):
    """Append records oldest-first; return the buffer."""
    buf = get_history_buffer()
    for t in texts:
        buf.append(text=t, pcm_bytes=b"\x01\x00", sample_rate=24000, channels=1)
    return buf


class TestDrainSkipBack:
    async def test_restart_then_step_back(self):
        from voice_mode.tools.converse import _drain_skip_back

        _populate_buffer("r0", "r1", "r2")   # r2 newest
        played = []

        async def fake_play(record, control_state=None):
            played.append(record.text)
            return REPLAY_COMPLETED

        cs = get_control_state()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, 0)
            assert played == ["r2"] and cursor == 1        # restart current

            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, cursor)
            assert played == ["r2", "r1"] and cursor == 2  # step back one

            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, cursor)
            assert played == ["r2", "r1", "r0"] and cursor == 3

    async def test_clamps_at_oldest_entry(self):
        from voice_mode.tools.converse import _drain_skip_back

        _populate_buffer("a", "b")           # depth 2
        played = []

        async def fake_play(record, control_state=None):
            played.append(record.text)
            return REPLAY_COMPLETED

        cs = get_control_state()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            cursor = 0
            for _ in range(4):               # press far past the front
                cs.request_skip_back()
                cursor = await _drain_skip_back(cs, cursor)

        # Steps b, a, then stays on a (oldest) -- never walks off the end.
        assert played == ["b", "a", "a", "a"]
        assert cursor == 2

    async def test_rapid_presses_step_back_within_one_drain(self):
        from voice_mode.tools.converse import _drain_skip_back

        _populate_buffer("r0", "r1", "r2")
        played = []

        async def fake_play(record, control_state=None):
            played.append(record.text)
            if len(played) < 2:
                control_state.request_skip_back()   # a press arrived during replay
                return REPLAY_TRANSPORT
            return REPLAY_COMPLETED

        cs = get_control_state()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, 0)

        assert played == ["r2", "r1"] and cursor == 2

    async def test_empty_buffer_replays_nothing(self):
        from voice_mode.tools.converse import _drain_skip_back

        spy = MagicMock()

        async def fake_play(record, control_state=None):
            spy(record)
            return REPLAY_COMPLETED

        cs = get_control_state()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, 0)

        assert cursor == 0
        spy.assert_not_called()

    async def test_skip_back_while_paused_lifts_the_hold(self):
        from voice_mode.tools.converse import _drain_skip_back

        _populate_buffer("only")

        async def fake_play(record, control_state=None):
            return REPLAY_COMPLETED

        cs = get_control_state()
        cs.request_pause()
        cs.request_skip_back()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            await _drain_skip_back(cs, 0)

        # The replay un-held the pause so it was audible; stop is never touched.
        snap = cs.snapshot()
        assert snap.is_running and not snap.is_paused

    async def test_stop_during_replay_returns(self):
        from voice_mode.tools.converse import _drain_skip_back

        _populate_buffer("a", "b")

        async def fake_play(record, control_state=None):
            return REPLAY_STOPPED

        cs = get_control_state()
        with patch("voice_mode.streaming.play_cached_utterance", new=fake_play):
            cs.request_skip_back()
            cursor = await _drain_skip_back(cs, 0)

        assert cursor == 1     # one replay attempted, then bailed on the stop


# --------------------------------------------------------------------------
# converse end-to-end -- replay-then-listen, no STT for a replay
# --------------------------------------------------------------------------

def _converse_fn():
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


class TestConverseSkipBack:
    async def test_skip_back_after_tts_replays_without_stt(self):
        """A skip_back after speaking replays cached audio and runs no STT."""
        _populate_buffer("older", "current")     # "current" is newest

        async def fake_tts(*_a, **_k):
            # The listener fires a skip_back right after the utterance is spoken.
            get_control_state().request_skip_back()
            metrics = {"ttfa": 0.1, "generation": 0.2, "playback": 0.3}
            return True, metrics, {"provider": "kokoro", "voice": "af_sky"}

        replayed = []

        async def fake_replay(record, control_state=None):
            replayed.append(record.text)
            return REPLAY_COMPLETED

        async def _noop_feedback(*_a, **_k):
            return None

        def _record_no_speech(*_a, **_k):
            # No spoken response -> converse ends the turn without STT.
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(side_effect=AssertionError("STT must not run for a replay"))

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=fake_tts), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.streaming.play_cached_utterance", new=fake_replay), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record_no_speech), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="The answer is 42.", wait_for_response=True
            )

        # Restart the most-recent completed utterance; STT never ran (replay-only).
        assert replayed == ["current"]
        assert isinstance(result, str)

    async def test_skip_back_during_listening_replays_then_relistens(self):
        """A skip_back pressed while listening replays, then we listen again."""
        _populate_buffer("prev", "latest")

        async def fake_tts(*_a, **_k):
            return True, {"ttfa": 0.1, "generation": 0.2, "playback": 0.3}, {
                "provider": "kokoro", "voice": "af_sky"
            }

        replayed = []

        async def fake_replay(record, control_state=None):
            replayed.append(record.text)
            return REPLAY_COMPLETED

        async def _noop_feedback(*_a, **_k):
            return None

        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                # First listen: user presses skip_back instead of speaking.
                get_control_state().request_skip_back()
                return (np.zeros(10, dtype=np.int16), False)
            # Second listen (after the replay): still no speech -> end the turn.
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(side_effect=AssertionError("STT must not run for a replay"))

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=fake_tts), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.streaming.play_cached_utterance", new=fake_replay), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Anything else?", wait_for_response=True
            )

        assert replayed == ["latest"]          # the press during listening replayed
        assert record_calls["n"] == 2          # ...and we listened again afterwards
        assert isinstance(result, str)
