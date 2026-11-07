"""VM-2072 — the decay criterion, as a permanent regression test.

THE CRITERION MIKE IS ACTUALLY PROTECTED BY
-------------------------------------------
*A test that NOBODY MARKED, added AFTER this work landed, in a NEW file, still
cannot reach the device.*

This file IS that test.  Nothing here is marked ``@pytest.mark.audio``, no
marker list mentions it, no fixture is requested, and it lives in a file that
did not exist when the guard was designed — and every audio call in it is still
blocked, because the guard arms at ``pytest_configure`` and covers the
sounddevice module object rather than a list of today's audio tests.

WHY IT IS A SEPARATE FILE AND NOT ANOTHER CLASS IN test_audio_guard.py
----------------------------------------------------------------------
Because the criterion is about a NEW FILE.  Measured in this repo: the ``manual``
and ``slow`` markers have ZERO users, while the exclusion that actually works
(keeping ``tests/manual`` out of a default run) is a PATH rule that requires
nobody to remember anything.  The marker layer decays; the layer that needs no
memory does not.  This file exists so that the day somebody breaks the
memory-free layer, a test says so.

The end-to-end proof — a genuinely naive test file in a directory that has never
heard of this repo — is in ``test_audio_guard.py::TestEndToEndInAChildRun``,
which spawns a child pytest and shows the run FAIL on the guard's hit record
while every test in it passes.
"""

from __future__ import annotations

import numpy as np
import pytest
import sounddevice as sd

from tests.audio_guard import AudioDeviceTouchedInTest, expect_blocked

SILENCE = np.zeros((1024, 1), dtype=np.float32)


def test_unmarked_playback_in_a_new_file_is_blocked():
    with expect_blocked("play", label="decay: unmarked playback"):
        with pytest.raises(AudioDeviceTouchedInTest):
            sd.play(SILENCE, samplerate=44100)


def test_unmarked_recording_in_a_new_file_is_blocked():
    with expect_blocked("rec", label="decay: unmarked recording"):
        with pytest.raises(AudioDeviceTouchedInTest):
            sd.rec(1024, samplerate=16000, channels=1)


def test_unmarked_stream_in_a_new_file_is_blocked():
    # Caught at InputStream.__init__ (the derived entry point names the
    # crossing precisely); a stream class nobody enumerated is caught one layer
    # further in, at _StreamBase.__init__ — see test_audio_guard.py.
    with expect_blocked("InputStream.__init__", label="decay: unmarked stream"):
        with pytest.raises(AudioDeviceTouchedInTest):
            sd.InputStream(samplerate=24000, channels=1)


def test_unmarked_module_level_style_call_is_blocked():
    """Nobody can put a marker on a module body.

    ``tests/test_ffmpeg_demo.py`` is a demo SCRIPT whose module body pytest
    executes at collection time — six subprocess spawns before any fixture
    exists.  Harmless there (``ffmpeg -version``), but had it been ``afplay`` a
    fixture-based guard would not have been in the room.  This is the same call
    shape, and it is blocked because the guard installs at plugin level.
    """
    import subprocess

    from tests.audio_guard import AudioSubprocessSpawnedInTest

    with expect_blocked("subprocess.run", label="decay: unmarked spawn"):
        with pytest.raises(AudioSubprocessSpawnedInTest):
            subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"])
