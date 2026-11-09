"""scipy.signal import placement in the converse tool (VM-2254 / GH #545).

record_audio_with_silence_detection used to import scipy.signal inside its per-chunk
loop, so the first import ran after the sounddevice input stream had opened and blocked
the VAD loop for about 24 s on Windows. The import now sits at the top of the function:
once per call, before the stream opens. Importing the module itself stays free of scipy.signal
so non-audio entry points (`voicemode --help`) do not pay the BLAS load.
"""

import builtins
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from voice_mode.config import SAMPLE_RATE, VAD_CHUNK_DURATION_MS
from voice_mode.tools.converse import record_audio_with_silence_detection

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERSE_MODULE = "voice_mode.tools.converse"
CHUNK_SAMPLES = int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)
CHUNK_COUNT = 4

IMPORT_EVENT = "import scipy.signal"
STREAM_EVENT = "open input stream"


def _is_scipy_signal_import(name: str, fromlist: tuple | None) -> bool:
    """True for `import scipy.signal` and `from scipy import signal`."""
    return name == "scipy.signal" or (name == "scipy" and "signal" in (fromlist or ()))


def _record_calls(monkeypatch, events: list[str]) -> None:
    """Log every scipy.signal import executed by converse.py code into events."""
    real_import = builtins.__import__

    def recording_import(name, globals=None, locals=None, fromlist=(), level=0):
        in_converse = globals is not None and globals.get("__name__") == CONVERSE_MODULE
        if in_converse and _is_scipy_signal_import(name, fromlist):
            events.append(IMPORT_EVENT)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", recording_import)


def _fake_input_stream(events: list[str]):
    """InputStream stand-in that logs its construction and feeds CHUNK_COUNT chunks on enter."""

    class FakeInputStream:
        def __init__(self, *, callback, **_kwargs):
            events.append(STREAM_EVENT)
            self._callback = callback

        def __enter__(self):
            for _ in range(CHUNK_COUNT):
                self._callback(np.ones((CHUNK_SAMPLES, 1), dtype=np.int16), CHUNK_SAMPLES, None, None)
            return self

        def __exit__(self, *_exc):
            return False

    return FakeInputStream


def _record_chunks(monkeypatch) -> tuple[list[str], np.ndarray]:
    """Run the recorder over CHUNK_COUNT fake chunks; return the event log and the audio."""
    events: list[str] = []
    stop_event = threading.Event()
    vad_calls = []

    def is_speech(_chunk_bytes, _sample_rate):
        vad_calls.append(1)
        if len(vad_calls) == CHUNK_COUNT:
            stop_event.set()
        return True

    _record_calls(monkeypatch, events)
    with patch(f"{CONVERSE_MODULE}.VAD_AVAILABLE", True), \
         patch(f"{CONVERSE_MODULE}.webrtcvad") as mock_webrtcvad, \
         patch(f"{CONVERSE_MODULE}.sd") as mock_sd:
        mock_webrtcvad.Vad.return_value = MagicMock(is_speech=is_speech)
        mock_sd.InputStream = _fake_input_stream(events)
        audio, _speech_detected = record_audio_with_silence_detection(
            max_duration=30.0, stop_event=stop_event
        )

    assert len(audio) == CHUNK_COUNT * CHUNK_SAMPLES, "every fed chunk must be recorded"
    return events, audio


class TestScipyImportPlacement:
    """The scipy.signal import happens once per call, ahead of the input stream."""

    def test_scipy_signal_imported_before_input_stream_opens(self, monkeypatch):
        """Regression for #545: a first import after the stream opened stalled the VAD loop."""
        events, _audio = _record_chunks(monkeypatch)

        assert IMPORT_EVENT in events, "the function never imported scipy.signal"
        assert STREAM_EVENT in events, "the fake input stream was never opened"
        assert events.index(IMPORT_EVENT) < events.index(STREAM_EVENT), events

    def test_scipy_signal_imported_once_not_per_chunk(self, monkeypatch):
        """Regression for #545: the import ran inside the per-chunk loop."""
        events, _audio = _record_chunks(monkeypatch)

        assert events.count(IMPORT_EVENT) == 1, (
            f"expected one scipy.signal import across {CHUNK_COUNT} chunks, got {events}"
        )


class TestModuleImportIsLight:
    """Importing the converse module must not load scipy.signal (fresh interpreter)."""

    def test_importing_converse_does_not_import_scipy_signal(self):
        """Other tests may already have imported scipy.signal, so ask a clean process."""
        probe = (
            f"import sys; import {CONVERSE_MODULE}; "
            "print('scipy.signal' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == "False", (
            f"importing {CONVERSE_MODULE} loaded scipy.signal"
        )
