"""Tests for the optional Smart Turn end-of-turn detector."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Mock webrtcvad before importing voice_mode modules (same pattern as the
# other VAD test modules in this suite).
sys.modules.setdefault('webrtcvad', MagicMock())

from voice_mode import smart_turn
from voice_mode.config import SAMPLE_RATE, VAD_CHUNK_DURATION_MS
from voice_mode.smart_turn import TurnGate, to_model_audio
from voice_mode.tools.converse import record_audio_with_silence_detection

CHUNK_SAMPLES = int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)


def _chunk():
    return np.random.randint(-1000, 1000, size=CHUNK_SAMPLES, dtype=np.int16)


class _Scorer:
    def __init__(self, ended=True, error=None):
        self.ended = ended
        self.error = error
        self.calls = []

    def __call__(self, pcm):
        self.calls.append(pcm)
        if self.error:
            raise self.error
        return (0.9 if self.ended else 0.1), self.ended


class TestTurnGate:
    def test_waits_for_the_pause(self):
        scorer = _Scorer()
        gate = TurnGate(scorer, pause_ms=200)
        assert gate.turn_ended(150, [_chunk()]) is False
        assert scorer.calls == []
        assert gate.turn_ended(210, [_chunk()]) is True
        assert len(scorer.calls) == 1

    def test_scores_once_per_pause(self):
        scorer = _Scorer(ended=False)
        gate = TurnGate(scorer, pause_ms=200)
        for silence_ms in (210, 240, 900):
            assert gate.turn_ended(silence_ms, [_chunk()]) is False
        assert len(scorer.calls) == 1

    def test_speech_starts_a_new_pause(self):
        scorer = _Scorer(ended=False)
        gate = TurnGate(scorer, pause_ms=200)
        gate.turn_ended(210, [_chunk()])
        gate.on_speech()
        gate.turn_ended(210, [_chunk()])
        assert len(scorer.calls) == 2

    def test_scorer_error_turns_the_gate_off(self):
        scorer = _Scorer(error=RuntimeError("boom"))
        gate = TurnGate(scorer, pause_ms=200)
        assert gate.turn_ended(210, [_chunk()]) is False
        gate.on_speech()
        assert gate.turn_ended(210, [_chunk()]) is False
        assert len(scorer.calls) == 1

    def test_scores_16k_float_audio(self):
        scorer = _Scorer()
        gate = TurnGate(scorer, pause_ms=0)
        gate.turn_ended(0, [np.full(SAMPLE_RATE, 16384, dtype=np.int16)])
        pcm = scorer.calls[0]
        assert pcm.dtype == np.float32
        assert len(pcm) == 16000
        assert np.allclose(pcm[100:-100], 0.5, atol=0.01)


def test_to_model_audio_joins_chunks():
    pcm = to_model_audio([_chunk(), _chunk(), _chunk()])
    assert len(pcm) == 3 * CHUNK_SAMPLES * 16000 // SAMPLE_RATE


def test_off_by_default():
    with patch.object(smart_turn, 'TURN_DETECTOR', 'silence'), \
         patch.object(smart_turn, 'SmartTurnModel') as model:
        assert smart_turn.get_scorer() is None
        assert smart_turn.make_gate() is None
    model.assert_not_called()


def test_load_failure_falls_back_to_silence():
    with patch.object(smart_turn, 'TURN_DETECTOR', 'smart-turn'), \
         patch.object(smart_turn, '_model', None), \
         patch.object(smart_turn, '_load_failed', False), \
         patch.object(smart_turn, 'resolve_model_path', return_value='/x.gguf'), \
         patch.object(smart_turn, 'SmartTurnModel', side_effect=ImportError('no transcribe_cpp')):
        assert smart_turn.make_gate() is None
        assert smart_turn._load_failed is True


class _ScriptedQueue:
    """Serves chunks forever; counts them so a test can see when recording stopped."""

    def __init__(self):
        self.served = 0

    def get(self, timeout=None):
        self.served += 1
        return _chunk().reshape(-1, 1)


SPEECH_CHUNKS = 40  # 1.2 s of speech, then silence


def _record(gate):
    """Run the real recording loop: speech, then silence, with ``gate``."""
    q = _ScriptedQueue()
    with patch('voice_mode.tools.converse.VAD_AVAILABLE', True), \
         patch('voice_mode.tools.converse.SILENCE_THRESHOLD_MS', 3000), \
         patch('voice_mode.tools.converse.MIN_RECORDING_DURATION', 0.0), \
         patch('voice_mode.tools.converse.make_turn_gate', return_value=gate), \
         patch('voice_mode.tools.converse.webrtcvad') as mock_webrtcvad, \
         patch('voice_mode.tools.converse.sd') as mock_sd, \
         patch('queue.Queue', return_value=q):
        mock_webrtcvad.Vad.return_value.is_speech.side_effect = (
            [True] * SPEECH_CHUNKS + [False] * 10_000
        )
        mock_sd.InputStream.return_value.__enter__.return_value = MagicMock()
        audio, speech_detected = record_audio_with_silence_detection(max_duration=60.0)
    assert speech_detected is True
    return len(audio) // CHUNK_SAMPLES


class TestRecordingLoop:
    def test_smart_turn_ends_the_turn_at_the_first_pause(self):
        scorer = _Scorer(ended=True)
        chunks = _record(TurnGate(scorer, pause_ms=210))
        # 7 silent chunks (210 ms) after speech, far before the 3 s threshold.
        assert chunks == SPEECH_CHUNKS + 7
        assert len(scorer.calls) == 1
        # The scored audio is the turn: from the first speech chunk.
        assert len(scorer.calls[0]) == chunks * CHUNK_SAMPLES * 16000 // SAMPLE_RATE

    def test_open_turn_falls_back_to_the_silence_threshold(self):
        scorer = _Scorer(ended=False)
        chunks = _record(TurnGate(scorer, pause_ms=210))
        assert chunks == SPEECH_CHUNKS + 100  # 3000 ms / 30 ms
        assert len(scorer.calls) == 1

    def test_no_gate_keeps_the_silence_threshold(self):
        assert _record(None) == SPEECH_CHUNKS + 100
