"""VM-2099 regression-check-001 — behaviour proofs: config owns the listening cap.

The rest of VM-2099 is documentation surgery plus a pattern-scan check
(``tests/test_no_cap_teaching.py``) that stops the *advice* coming back. Neither
of those measures the thing Mike actually named: **he must never be cut off
mid-answer**. That is what this module measures, and it measures it at the
*call path* — the number that reaches the recorder — not at the signature
default and not in the docs. A signature default can be right while the
resolved value is wrong; only the recorder's argument decides when Mike gets
cut off.

Two proofs:

1. ``TestEffectiveCapFollowsConfig`` — with **no** ``listen_duration_max``
   passed, the ceiling handed to ``record_audio_with_silence_detection`` is the
   one ``VOICEMODE_DEFAULT_LISTEN_DURATION`` names. Parametrised over two
   unusual values (137.5, 42.25) so a hard-coded constant *cannot* pass: break
   the config→call-path binding and these go red (demonstrated red output is
   pasted in the task README's Testing section). Covered on the scalar-message
   path *and* the per-turn ``turns=[{"ask": ...}]`` path — the path whose
   parameter documentation carried the taught numbers (VM-1775).

2. ``TestRecursiveProof`` — the case that produced this task: an answer of
   ≥ 84.3 seconds (Mike's dictation of VM-2099) completes **without
   truncation** under stock config with no agent-supplied cap. Synthesised, not
   spoken: a pre-rendered answer is replayed through the *real*
   ``record_audio_with_silence_detection`` VAD loop, whose length is governed
   by 30ms frame count rather than the wall clock, so 84.3 seconds of audio
   costs well under a second of test time. The inversion — the documentation's
   taught 30s cap truncating the same answer — is asserted alongside it, so a
   test that stopped being able to see truncation would fail.

Each proof runs in a **subprocess** with a scratch ``HOME`` and every
``VOICEMODE_*`` variable stripped. That is not ceremony: the cap is bound from
config at *import* time, so an in-process test can only ever re-read what was
bound when pytest started, and the developer's own
``~/.voicemode/voicemode.env`` would otherwise decide the answer (on this
machine it says 300s — see the task README). A fresh interpreter per
configuration is the only honest way to ask "what does *this* config produce?".

Cost: ~2s per test (interpreter start + voicemode import), ~20s for the module.
Deliberately NOT marked ``slow``: CI selects ``-m "not slow"``, and a proof that
Mike is not cut off is worth twenty seconds of every CI run — a marker here
would quietly retire the only test that measures the named thing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Result marker: probe stdout also carries voicemode's own log lines.
MARKER = "VM2099_JSON "

# Mike's answer that dictated this task, measured (README, Objective).
MIKE_ANSWER_SECONDS = 84.3

# The number the documentation used to teach ("30–45s for normal questions").
TAUGHT_CAP_SECONDS = 30.0


def _run_probe(script: str, probe_args: dict, env_extra: dict | None = None,
               timeout: int = 300) -> dict:
    """Run ``script`` in a fresh interpreter with a controlled voicemode config.

    Every ``VOICEMODE_*`` variable is stripped and ``HOME`` points at a scratch
    directory, so the only configuration in play is what ``env_extra`` says
    (voicemode reads ``~/.voicemode/voicemode.env`` via ``Path.home()``).
    ``PYTHONPATH`` pins the *worktree* source, so the probe can never
    accidentally measure an installed copy.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOICEMODE_")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["VM2099_PROBE_ARGS"] = json.dumps(probe_args)
    env.update(env_extra or {})

    with tempfile.TemporaryDirectory() as scratch_home:
        env["HOME"] = scratch_home
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            cwd=scratch_home,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    if proc.returncode != 0:
        raise AssertionError(
            f"probe failed (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout[-4000:]}\n"
            f"--- stderr ---\n{proc.stderr[-4000:]}"
        )

    for line in proc.stdout.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    raise AssertionError(
        f"probe produced no {MARKER!r} result line\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n"
        f"--- stderr ---\n{proc.stderr[-4000:]}"
    )


# --------------------------------------------------------------------------
# Probe 1: what ceiling reaches the recorder?
# --------------------------------------------------------------------------
_PROBE_CALL_PATH = r'''
import asyncio, json, os
import numpy as np
from unittest.mock import AsyncMock, patch

import voice_mode.config as config
import voice_mode.tools.converse as conv

ARGS = json.loads(os.environ["VM2099_PROBE_ARGS"])
seen = []


def fake_record(max_duration, disable_silence_detection=False, min_duration=0.0,
                vad_aggressiveness=None, stop_event=None):
    """Stand in for the recorder and report the ceiling it was handed."""
    seen.append({"max_duration": max_duration, "min_duration": min_duration})
    return (np.zeros(config.SAMPLE_RATE, dtype=np.int16), True)


async def main():
    fn = getattr(conv.converse, "fn", conv.converse)
    conv.FFMPEG_AVAILABLE = True
    config.FFMPEG_AVAILABLE = True
    with patch.object(conv, "startup_initialization", new_callable=AsyncMock), \
         patch.object(conv, "text_to_speech_with_failover", new_callable=AsyncMock) as tts, \
         patch.object(conv, "record_audio_with_silence_detection", side_effect=fake_record), \
         patch.object(conv, "speech_to_text", new_callable=AsyncMock) as stt, \
         patch.object(conv, "play_audio_feedback", new_callable=AsyncMock):
        tts.return_value = (True, {"generation": 0.1, "playback": 0.1}, {})
        stt.return_value = {"text": "synthetic answer", "provider": "whisper"}
        return await fn(**ARGS["kwargs"])


result = asyncio.run(main())
print("VM2099_JSON " + json.dumps({
    "config_default_listen_duration": config.DEFAULT_LISTEN_DURATION,
    "recordings": seen,
    "result": str(result)[:400],
}))
'''


# --------------------------------------------------------------------------
# Probe 2: replay a long answer through the real VAD recording loop
# --------------------------------------------------------------------------
_PROBE_LONG_ANSWER = r'''
import asyncio, json, os
import numpy as np
from unittest.mock import AsyncMock, patch

import voice_mode.config as config
import voice_mode.tools.converse as conv

ARGS = json.loads(os.environ["VM2099_PROBE_ARGS"])

CHUNK_MS = config.VAD_CHUNK_DURATION_MS
CHUNK_S = CHUNK_MS / 1000.0
SPEECH_CHUNKS = int(round(ARGS["answer_seconds"] / CHUNK_S))
SILENCE_CHUNKS = int(round(ARGS["trailing_silence_seconds"] / CHUNK_S))


class FakeInputStream:
    """A pre-rendered answer, replayed into the real recorder's callback.

    The recording loop advances ``recording_duration`` by one VAD frame per
    chunk consumed, so audio length is a function of frame COUNT, not of the
    wall clock: an 84.3 second answer replays in well under a second. Frames
    are queued on enter, before the loop starts reading them, exactly as a live
    stream's callback would deliver them.
    """

    def __init__(self, *, samplerate, channels, dtype, callback, blocksize, **kwargs):
        self.callback = callback
        self.blocksize = blocksize

    def __enter__(self):
        rng = np.random.default_rng(2099)
        silence = np.zeros((self.blocksize, 1), dtype=np.int16)
        for i in range(SPEECH_CHUNKS + SILENCE_CHUNKS):
            if i < SPEECH_CHUNKS:
                frame = rng.integers(-8000, 8000, size=(self.blocksize, 1)).astype(np.int16)
            else:
                frame = silence
            self.callback(frame, self.blocksize, None, None)
        return self

    def __exit__(self, *exc):
        return False


class FakeVad:
    """Speech for the answer's frames, silence afterwards — in frame order."""

    def __init__(self, aggressiveness=3):
        self.calls = 0

    def is_speech(self, chunk_bytes, sample_rate):
        self.calls += 1
        return self.calls <= SPEECH_CHUNKS


captured = {}


async def fake_stt(audio_data, *args, **kwargs):
    captured["samples"] = int(len(audio_data))
    return {"text": "synthetic answer", "provider": "whisper"}


def no_fixed_duration_fallback(max_duration, *args, **kwargs):
    """Tripwire: without VAD the recorder blocks on a REAL sd.rec for the full
    ceiling (minutes of wall clock, and nothing this probe can measure). Fail
    loudly instead of hanging."""
    raise AssertionError(
        "recorder fell back to fixed-duration recording — this probe measures "
        "the VAD path"
    )


async def main():
    fn = getattr(conv.converse, "fn", conv.converse)
    conv.FFMPEG_AVAILABLE = True
    config.FFMPEG_AVAILABLE = True
    with patch.object(conv, "startup_initialization", new_callable=AsyncMock), \
         patch.object(conv, "text_to_speech_with_failover", new_callable=AsyncMock) as tts, \
         patch.object(conv, "play_audio_feedback", new_callable=AsyncMock), \
         patch.object(conv, "speech_to_text", side_effect=fake_stt), \
         patch.object(conv, "record_audio", no_fixed_duration_fallback), \
         patch.object(conv, "DISABLE_SILENCE_DETECTION", False), \
         patch.object(conv.sd, "InputStream", FakeInputStream), \
         patch.object(conv.webrtcvad, "Vad", FakeVad):
        tts.return_value = (True, {"generation": 0.1, "playback": 0.1}, {})
        return await fn(**ARGS["kwargs"])


if not conv.VAD_AVAILABLE:
    # No webrtcvad: the VAD loop this probe drives does not run at all. Report
    # it rather than measuring the fallback path and calling it a proof.
    print("VM2099_JSON " + json.dumps({"vad_available": False}))
    raise SystemExit(0)

result = asyncio.run(main())
samples = captured.get("samples")
print("VM2099_JSON " + json.dumps({
    "vad_available": True,
    "config_default_listen_duration": config.DEFAULT_LISTEN_DURATION,
    "offered_answer_seconds": ARGS["answer_seconds"],
    "captured_samples": samples,
    "captured_seconds": (samples / config.SAMPLE_RATE) if samples else None,
    "result": str(result)[:400],
}))
'''


class TestEffectiveCapFollowsConfig:
    """Criterion: a call passing NO listen_duration_max uses the CONFIG value.

    Read at the call path (the recorder's argument), which is where being cut
    off is actually decided.
    """

    @pytest.mark.parametrize("configured", ["137.5", "42.25"])
    def test_scalar_message_path(self, configured):
        out = _run_probe(
            _PROBE_CALL_PATH,
            {"kwargs": {"message": "Tell me everything.", "wait_for_response": True}},
            env_extra={"VOICEMODE_DEFAULT_LISTEN_DURATION": configured},
        )
        expected = float(configured)
        # The config key is honoured...
        assert out["config_default_listen_duration"] == expected
        # ...and the number the recorder is actually handed follows it.
        assert out["recordings"], "converse never reached the recorder"
        assert out["recordings"][0]["max_duration"] == expected

    @pytest.mark.parametrize("configured", ["137.5", "42.25"])
    def test_per_turn_ask_path(self, configured):
        """The turns path (VM-1775) is the one that taught the invented caps."""
        out = _run_probe(
            _PROBE_CALL_PATH,
            {"kwargs": {"turns": [{"ask": "Tell me everything."}]}},
            env_extra={"VOICEMODE_DEFAULT_LISTEN_DURATION": configured},
        )
        expected = float(configured)
        assert out["config_default_listen_duration"] == expected
        assert out["recordings"], "the ask turn never reached the recorder"
        assert out["recordings"][0]["max_duration"] == expected

    def test_stock_config_ceiling_is_the_stock_config_value(self):
        """With no config key set at all, the call path still follows config."""
        out = _run_probe(
            _PROBE_CALL_PATH,
            {"kwargs": {"message": "Tell me everything.", "wait_for_response": True}},
        )
        stock = out["config_default_listen_duration"]
        assert out["recordings"][0]["max_duration"] == stock
        # Stock must leave room for the answer that produced this task.
        assert stock > MIKE_ANSWER_SECONDS, (
            f"stock ceiling {stock}s would cut off Mike's {MIKE_ANSWER_SECONDS}s answer"
        )

    def test_an_agent_supplied_cap_still_overrides(self):
        """The escape hatch survives — an articulated need can still pass one.

        VM-2099 removes the *teaching*, not the parameter. If this ever stops
        being true the fix has gone further than anyone asked.
        """
        out = _run_probe(
            _PROBE_CALL_PATH,
            {"kwargs": {"message": "Quick one?", "wait_for_response": True,
                        "listen_duration_max": 12.0}},
            env_extra={"VOICEMODE_DEFAULT_LISTEN_DURATION": "137.5"},
        )
        assert out["recordings"][0]["max_duration"] == 12.0

    def test_min_extension_still_works_with_a_config_owned_ceiling(self):
        """VM-1168's legitimate adjacent case: extend the FLOOR, not the ceiling.

        A per-turn ``listen_duration_min`` of 15 must arrive as 15.0 while the
        ceiling stays the config's — min-extension and cap-invention must not
        be confused for each other.
        """
        out = _run_probe(
            _PROBE_CALL_PATH,
            {"kwargs": {"turns": [{"ask": "Give me the long list.",
                                   "listen_duration_min": 15}]}},
            env_extra={"VOICEMODE_DEFAULT_LISTEN_DURATION": "137.5"},
        )
        assert out["recordings"][0]["min_duration"] == 15.0
        assert out["recordings"][0]["max_duration"] == 137.5


class TestRecursiveProof:
    """Criterion: Mike's ≥84.3s answer completes without truncation.

    Stock config, no agent-supplied cap, the real VAD recording loop. Synthetic
    audio — VM-2099 forbids opening a voice channel while Mike is being cut off.
    """

    ANSWER_SECONDS = 85.0  # ≥ Mike's measured 84.3s
    TRAILING_SILENCE = 1.5  # > SILENCE_THRESHOLD_MS (1000ms): ends the turn naturally

    @staticmethod
    def _require_vad(out: dict) -> None:
        if not out.get("vad_available"):
            pytest.skip("webrtcvad unavailable — the VAD recording loop does not run")

    def test_84_3_second_answer_is_not_truncated(self):
        out = _run_probe(
            _PROBE_LONG_ANSWER,
            {"kwargs": {"message": "Dictate the task.", "wait_for_response": True},
             "answer_seconds": self.ANSWER_SECONDS,
             "trailing_silence_seconds": self.TRAILING_SILENCE},
        )
        self._require_vad(out)
        captured = out["captured_seconds"]
        stock_cap = out["config_default_listen_duration"]
        assert captured is not None, "the answer never reached transcription"
        # The whole answer survived...
        assert captured >= MIKE_ANSWER_SECONDS, (
            f"answer truncated at {captured:.1f}s — Mike's {MIKE_ANSWER_SECONDS}s "
            f"answer was cut off under a stock {stock_cap}s ceiling"
        )
        # ...and it ended on silence, not on the ceiling. (Equality with the
        # ceiling is what truncation looks like from here.)
        assert captured < stock_cap, (
            f"recording ran to the {stock_cap}s ceiling — that is truncation, "
            "not a turn that ended when Mike stopped talking"
        )

    def test_the_taught_30s_cap_truncates_the_same_answer(self):
        """Inversion: the number the docs used to teach cuts Mike off.

        Without this, a proof that "the answer survived" could be passing
        because the harness cannot see truncation at all.
        """
        out = _run_probe(
            _PROBE_LONG_ANSWER,
            {"kwargs": {"message": "Dictate the task.", "wait_for_response": True,
                        "listen_duration_max": TAUGHT_CAP_SECONDS},
             "answer_seconds": self.ANSWER_SECONDS,
             "trailing_silence_seconds": self.TRAILING_SILENCE},
        )
        self._require_vad(out)
        captured = out["captured_seconds"]
        assert captured is not None
        assert captured < MIKE_ANSWER_SECONDS, (
            "the taught 30s cap failed to truncate an 85s answer — this probe "
            "cannot detect truncation, so the proof above proves nothing"
        )
        assert captured == pytest.approx(TAUGHT_CAP_SECONDS, abs=0.5)
