"""VM-2072 — the ``-m audio`` opt-in path, and its canary.

WHY A CANARY EXISTS AT ALL
--------------------------
Measured on this repo (VM-2072 rca-001): every audio-touching test in the suite
was a MISSING MOCK, not a test that genuinely needs a device.  All of them were
fixed by mocking the seam they were not asserting about.  So the ``audio``
marker ships with **zero natural occupants**, and an opt-in path with no tests
on it is an untested code path.

The first person to genuinely need ``-m audio`` would then be the person who
discovers it stopped working, at the moment they least want a detour — a dead
guard arriving through the ESCAPE HATCH rather than through the guard.

So this file occupies the path deliberately.  It proves three things at once:
the marker registers under ``--strict-markers``, the default exclusion genuinely
excludes it, and the opt-in path still runs — muted, never on a real device.

⚠️ THE CANARY'S OWN ASSERTION IS THAT IT RAN.  A canary that quietly gets
excluded is the exact failure it exists to catch, so it writes a receipt and the
companion test below checks the wiring from inside a default run.

    pytest -m audio tests/test_audio_optin_canary.py       # the opt-in run
    VOICEMODE_AUDIO_CANARY_RECEIPT=/tmp/canary.json pytest -m audio ...
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import pytest
import sounddevice as sd

from tests import audio_guard

#: Silent samples: even a total guard failure would be inaudible.
SILENCE = np.zeros((1024, 1), dtype=np.float32)

RECEIPT_ENV = "VOICEMODE_AUDIO_CANARY_RECEIPT"


def _write_receipt(payload: dict) -> None:
    path = os.environ.get(RECEIPT_ENV)
    if not path:
        return
    Path(path).write_text(json.dumps(payload, indent=2, default=str) + "\n")


@pytest.mark.audio
def test_optin_audio_path_runs_and_is_device_safe():
    """The one test that actually opts in — and it never reaches a device.

    ``-m audio`` puts the guard in MUTE mode: the calls below are made for
    real, at the real entry points, and the guard hands back inert stand-ins
    without PortAudio ever being called.  Device-safe by construction, not by a
    null sink somebody has to configure correctly.
    """
    mode = audio_guard.current_mode()

    if mode == audio_guard.MODE_OFF:
        # The loud escape hatch is in use: a real device IS reachable, so the
        # canary refuses to make a sound. Skipping is the safe answer here, and
        # the skip is itself the report.
        pytest.skip(
            f"{audio_guard.MODE_ENV}=off — the guard is disarmed and this test "
            "will not play audio through a live human's speakers to prove a point"
        )

    ran_at = dt.datetime.now(dt.timezone.utc).isoformat()
    before = len(audio_guard.HITS)

    if mode == audio_guard.MODE_MUTE:
        # Playback, enumeration and a live output stream — all made for real,
        # all handed inert stand-ins.
        assert sd.play(SILENCE, samplerate=44100) is None
        assert sd.query_devices() == []
        stream = sd.OutputStream(samplerate=44100, channels=1)
        assert stream.start() is None
        assert stream.close() is None
    else:  # a deliberate block-mode run of the opt-in selection
        with pytest.raises(audio_guard.AudioDeviceTouchedInTest):
            sd.play(SILENCE, samplerate=44100)

    crossings = audio_guard.HITS[before:]
    assert crossings, "the opt-in path made no audio call at all — it is not exercising anything"
    expected = "muted" if mode == audio_guard.MODE_MUTE else "blocked"
    assert all(hit["disposition"] == expected for hit in crossings), crossings
    assert all(hit["layer"] == "sounddevice" for hit in crossings)

    _write_receipt({
        "canary": "tests/test_audio_optin_canary.py::test_optin_audio_path_runs_and_is_device_safe",
        "ran_at": ran_at,
        "guard_mode": mode,
        "crossings": crossings,
        "assertion": "I RAN. The opt-in path is alive and device-safe.",
    })


def test_the_canary_is_marked_registered_and_excluded_by_default(request):
    """Runs in a DEFAULT run, and checks the wiring the canary depends on.

    Without this, the canary could quietly stop being collected — unmarked,
    unregistered or un-excluded — and nothing would say so, which is precisely
    the failure the canary exists to catch.
    """
    markers = request.config.getini("markers")
    assert any(marker.startswith("audio:") for marker in markers), (
        "the `audio` marker is not registered in pyproject.toml, and "
        "--strict-markers is on"
    )

    markexpr = request.config.getoption("-m")
    assert "not audio" in markexpr, (
        "a default run is no longer excluding audio-marked tests "
        f"(-m {markexpr!r}). The guard still holds, but the opt-in path has "
        "stopped being opt-in."
    )

    own_marks = {
        mark.name
        for mark in getattr(test_optin_audio_path_runs_and_is_device_safe,
                            "pytestmark", [])
    }
    assert "audio" in own_marks, "the canary has lost its own audio marker"
