"""Tests for the utterance history buffer (VM-1685, impl-buffer).

Two halves:

* The buffer module itself (``voice_mode.history_buffer``) -- append, bound /
  evict at maxlen, record fields, ordering / cursor reads, clear, and the
  process-wide singleton. Pure data structure, no audio.

* The capture hook in the TTS playback loops (``voice_mode.streaming``) -- that a
  rendered utterance lands in the buffer **regardless of SAVE_AUDIO**, that a
  control-channel stop does NOT capture a partial, and that the cheap context
  (voice / conversation_id / sample_rate) is recorded. The ``sounddevice``
  OutputStream is mocked and the TTS byte source faked, mirroring
  ``tests/test_playback_interrupt.py``.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from voice_mode import history_buffer, streaming
from voice_mode.config import SAMPLE_RATE
from voice_mode.control_channel import get_control_state
from voice_mode.history_buffer import (
    DEFAULT_HISTORY_SIZE,
    HistoryBuffer,
    UtteranceRecord,
    get_history_buffer,
)
from voice_mode.streaming import (
    stream_cartesia_pcm,
    stream_pcm_audio,
    stream_with_buffering,
)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """Keep the process-wide singletons clean around every test.

    Both the history buffer and the control state are module-level singletons;
    a stray record or a latched ``stop`` could otherwise leak across tests.
    """
    monkeypatch.setattr(history_buffer, "_default_buffer", None)
    get_control_state().reset()
    yield
    monkeypatch.setattr(history_buffer, "_default_buffer", None)
    get_control_state().reset()


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    """Shrink the pause poll interval so any pause/stop timing is quick."""
    monkeypatch.setattr(streaming, "CONTROL_POLL_INTERVAL", 0.01)


def _record(text="hi", pcm=b"\x00\x01", sample_rate=24000, channels=1, **kw):
    """A minimal UtteranceRecord for buffer-level tests."""
    return UtteranceRecord(
        text=text,
        pcm_bytes=pcm,
        sample_rate=sample_rate,
        channels=channels,
        timestamp=kw.pop("timestamp", 123.0),
        **kw,
    )


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
# UtteranceRecord -- unit
# --------------------------------------------------------------------------

class TestUtteranceRecord:
    def test_fields_populated(self):
        rec = _record(
            text="hello", pcm=b"\x01\x02\x03\x04", sample_rate=24000, channels=1,
            voice="af_sky", conversation_id="conv-1", timestamp=42.0,
        )
        assert rec.text == "hello"
        assert rec.pcm_bytes == b"\x01\x02\x03\x04"
        assert rec.sample_rate == 24000
        assert rec.channels == 1
        assert rec.voice == "af_sky"
        assert rec.conversation_id == "conv-1"
        assert rec.timestamp == 42.0

    def test_optional_context_defaults_to_none(self):
        rec = _record()
        assert rec.voice is None
        assert rec.conversation_id is None

    def test_nbytes(self):
        assert _record(pcm=b"\x00" * 10).nbytes == 10

    def test_duration_from_pcm_length(self):
        # 24000 mono 16-bit samples = 48000 bytes = exactly 1.0s.
        rec = _record(pcm=b"\x00\x00" * 24000, sample_rate=24000, channels=1)
        assert rec.duration == pytest.approx(1.0)

    def test_duration_zero_when_rate_unusable(self):
        assert _record(pcm=b"\x00\x00", sample_rate=0).duration == 0.0

    def test_is_frozen(self):
        rec = _record()
        with pytest.raises(Exception):
            rec.text = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------
# HistoryBuffer -- unit
# --------------------------------------------------------------------------

class TestHistoryBuffer:
    def test_append_returns_record_and_grows_length(self):
        buf = HistoryBuffer(maxlen=4)
        assert len(buf) == 0
        rec = buf.append(text="a", pcm_bytes=b"\x00\x01", sample_rate=24000)
        assert isinstance(rec, UtteranceRecord)
        assert rec.text == "a"
        assert len(buf) == 1

    def test_append_record_fields_populated(self):
        buf = HistoryBuffer(maxlen=4)
        buf.append(
            text="hello", pcm_bytes=b"\x01\x02", sample_rate=16000, channels=2,
            voice="v", conversation_id="c",
        )
        rec = buf.latest()
        assert rec.text == "hello"
        assert rec.pcm_bytes == b"\x01\x02"
        assert rec.sample_rate == 16000
        assert rec.channels == 2
        assert rec.voice == "v"
        assert rec.conversation_id == "c"

    def test_append_stamps_timestamp_by_default(self):
        buf = HistoryBuffer(maxlen=2)
        buf.append(text="a", pcm_bytes=b"\x00\x01", sample_rate=24000)
        assert buf.latest().timestamp > 0

    def test_append_honours_explicit_timestamp(self):
        buf = HistoryBuffer(maxlen=2)
        buf.append(text="a", pcm_bytes=b"\x00\x01", sample_rate=24000, timestamp=7.0)
        assert buf.latest().timestamp == 7.0

    def test_bounded_evicts_oldest_past_maxlen(self):
        buf = HistoryBuffer(maxlen=3)
        for i in range(5):
            buf.append(text=str(i), pcm_bytes=b"\x00\x01", sample_rate=24000)
        # Only the last 3 survive; oldest (0, 1) evicted.
        assert len(buf) == 3
        assert [r.text for r in buf.snapshot()] == ["2", "3", "4"]

    def test_maxlen_property(self):
        assert HistoryBuffer(maxlen=5).maxlen == 5

    def test_snapshot_is_oldest_first_and_a_copy(self):
        buf = HistoryBuffer(maxlen=4)
        for i in range(3):
            buf.append(text=str(i), pcm_bytes=b"\x00\x01", sample_rate=24000)
        snap = buf.snapshot()
        assert [r.text for r in snap] == ["0", "1", "2"]
        # Mutating the snapshot must not affect the buffer.
        snap.clear()
        assert len(buf) == 3

    def test_latest_returns_newest(self):
        buf = HistoryBuffer(maxlen=4)
        buf.append(text="old", pcm_bytes=b"\x00\x01", sample_rate=24000)
        buf.append(text="new", pcm_bytes=b"\x00\x01", sample_rate=24000)
        assert buf.latest().text == "new"

    def test_latest_none_when_empty(self):
        assert HistoryBuffer(maxlen=4).latest() is None

    def test_get_negative_index_walks_back(self):
        # The skip-back cursor access pattern: -1 latest, -2 the one before.
        buf = HistoryBuffer(maxlen=4)
        for t in ("a", "b", "c"):
            buf.append(text=t, pcm_bytes=b"\x00\x01", sample_rate=24000)
        assert buf.get(-1).text == "c"
        assert buf.get(-2).text == "b"
        assert buf.get(0).text == "a"

    def test_get_out_of_range_returns_none(self):
        buf = HistoryBuffer(maxlen=4)
        buf.append(text="a", pcm_bytes=b"\x00\x01", sample_rate=24000)
        assert buf.get(5) is None
        assert buf.get(-5) is None

    def test_clear_empties(self):
        buf = HistoryBuffer(maxlen=4)
        buf.append(text="a", pcm_bytes=b"\x00\x01", sample_rate=24000)
        buf.clear()
        assert len(buf) == 0
        assert buf.latest() is None

    def test_invalid_maxlen_rejected(self):
        with pytest.raises(ValueError):
            HistoryBuffer(maxlen=0)


# --------------------------------------------------------------------------
# get_history_buffer() singleton -- unit
# --------------------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        assert get_history_buffer() is get_history_buffer()

    def test_size_from_config(self, monkeypatch):
        monkeypatch.setattr(history_buffer, "_default_buffer", None)
        monkeypatch.setattr("voice_mode.config.HISTORY_BUFFER_SIZE", 3, raising=False)
        assert get_history_buffer().maxlen == 3

    def test_default_size_when_config_missing(self, monkeypatch):
        monkeypatch.setattr(history_buffer, "_default_buffer", None)
        monkeypatch.delattr("voice_mode.config.HISTORY_BUFFER_SIZE", raising=False)
        assert get_history_buffer().maxlen == DEFAULT_HISTORY_SIZE


# --------------------------------------------------------------------------
# Capture hook in the playback loops -- integration over a mocked stream
# --------------------------------------------------------------------------

class TestPcmCaptureHook:
    async def test_captures_utterance_when_save_audio_off(self):
        chunks = _pcm_chunks(5)
        client, resp = _make_openai_client(chunks)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="hello world",
                openai_client=client,
                request_params={"voice": "af_sky"},
                save_audio=False,
                conversation_id="conv-42",
            )

        assert success is True
        buf = get_history_buffer()
        assert len(buf) == 1
        rec = buf.latest()
        # Full rendered PCM captured (every chunk), not just when saving.
        assert rec.pcm_bytes == b"".join(chunks)
        assert rec.text == "hello world"
        assert rec.sample_rate == SAMPLE_RATE
        assert rec.channels == 1
        assert rec.voice == "af_sky"
        assert rec.conversation_id == "conv-42"

    async def test_control_stop_does_not_capture_partial(self):
        chunks = _pcm_chunks(6)

        def on_chunk(i):
            if i == 2:
                get_control_state().request_stop()

        client, resp = _make_openai_client(chunks, on_chunk)
        mock_stream = _make_mock_stream()

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_pcm_audio(
                text="cut short", openai_client=client, request_params={},
            )

        assert metrics.control_stopped is True
        # A stopped (partial) utterance is not stored -- only complete renders.
        assert len(get_history_buffer()) == 0

    async def test_cartesia_captures_with_voice_id(self):
        chunks = _pcm_chunks(3)

        async def fake_stream(text, voice_id, sample_rate, speed):
            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0)

        mock_stream = _make_mock_stream()
        with patch("voice_mode.cartesia_tts.stream", new=fake_stream), \
             patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            success, metrics = await stream_cartesia_pcm(
                text="cartesia hi", voice_id="sonic-v", conversation_id="c9",
            )

        assert success is True
        rec = get_history_buffer().latest()
        assert rec is not None
        assert rec.text == "cartesia hi"
        assert rec.pcm_bytes == b"".join(chunks)
        assert rec.voice == "sonic-v"
        assert rec.conversation_id == "c9"
        assert rec.sample_rate == SAMPLE_RATE

    async def test_buffered_path_captures_decoded_pcm(self):
        # Tiny opus "stream": stays under the mid-loop decode threshold, so the
        # final-buffer decode runs. AudioSegment is mocked (no real codec).
        chunks = _pcm_chunks(3)
        client, resp = _make_openai_client(chunks)
        mock_stream = _make_mock_stream()

        fake_audio = MagicMock()
        fake_audio.frame_rate = SAMPLE_RATE
        fake_audio.sample_width = 2
        fake_audio.get_array_of_samples.return_value = [0, 0, 0, 0]

        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream), \
             patch.object(streaming, "AudioSegment") as mock_seg:
            mock_seg.from_file.return_value = fake_audio
            success, metrics = await stream_with_buffering(
                text="buffered hi",
                openai_client=client,
                request_params={"response_format": "opus", "voice": "af_nova"},
            )

        assert success is True
        rec = get_history_buffer().latest()
        assert rec is not None
        assert rec.text == "buffered hi"
        assert rec.voice == "af_nova"
        # Decoded PCM captured: the 4 zero samples (plus any trailing silence
        # pad) -> all-zero int16 bytes, non-empty.
        assert len(rec.pcm_bytes) > 0
        assert set(rec.pcm_bytes) == {0}

    async def test_two_utterances_accumulate_in_order(self):
        mock_stream = _make_mock_stream()
        with patch.object(streaming.sd, "OutputStream", return_value=mock_stream):
            client1, _ = _make_openai_client(_pcm_chunks(2))
            await stream_pcm_audio(text="first", openai_client=client1, request_params={})
            client2, _ = _make_openai_client(_pcm_chunks(2))
            await stream_pcm_audio(text="second", openai_client=client2, request_params={})

        buf = get_history_buffer()
        assert [r.text for r in buf.snapshot()] == ["first", "second"]
        assert buf.get(-1).text == "second"
        assert buf.get(-2).text == "first"
