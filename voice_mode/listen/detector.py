"""Speech classification and end-of-turn detection for ``listen``.

Two small interfaces, so that Silero (spec task 3.4) can slot in beside the
silence timer without touching the loop:

- a *frame classifier*: ``classify(frame) -> bool`` (is this frame speech?)
- a *turn detector*: ``feed(frame) -> Verdict``, named by ``name`` (written
  as ``detector`` on every ``turn`` line)

The only detector today is ``vad-silence``: a turn opens after a short run
of speech frames and ends after ``silence_s`` of continuous non-speech.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import numpy as np

from .sources import FRAME_S, SAMPLE_RATE

# Spec (ruled, Mike 03:29-03:32 Thu 2026-09-24): "the current two seconds".
# NOTE: converse's own threshold, config.SILENCE_THRESHOLD_MS, defaults to
# 1000 ms in this tree; the spec and the task's success criteria name 2 s,
# so listen defaults to 2.0 s and says so here rather than importing it.
DEFAULT_SILENCE_S = float(os.getenv("VOICEMODE_LISTEN_SILENCE_S", "2.0"))
# converse uses webrtcvad at VOICEMODE_VAD_AGGRESSIVENESS=3; borrowed.
DEFAULT_VAD_AGGRESSIVENESS = int(os.getenv("VOICEMODE_LISTEN_VAD_AGGRESSIVENESS", "3"))

Classifier = Callable[[np.ndarray], bool]


class WebRtcClassifier:
    """webrtcvad (already a VoiceMode dependency) on 30 ms frames."""

    def __init__(self, aggressiveness: int = DEFAULT_VAD_AGGRESSIVENESS) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(aggressiveness)

    def __call__(self, frame: np.ndarray) -> bool:
        return bool(self._vad.is_speech(frame.astype(np.int16).tobytes(), SAMPLE_RATE))


class EnergyClassifier:
    """Mean-absolute-amplitude threshold. For tests and a no-webrtcvad fallback."""

    def __init__(self, threshold: float = 500.0) -> None:
        self.threshold = threshold

    def __call__(self, frame: np.ndarray) -> bool:
        return float(np.mean(np.abs(frame.astype(np.int32)))) >= self.threshold


def default_classifier() -> Classifier:
    try:
        return WebRtcClassifier()
    except ImportError:
        return EnergyClassifier()


@dataclass
class Verdict:
    speech: bool  # this frame is speech
    in_turn: bool  # a turn is open after this frame
    turn_started: bool = False  # this frame opened a turn
    end_of_turn: bool = False  # this frame closed a turn


class TurnDetector(Protocol):
    name: str

    def feed(self, frame: np.ndarray) -> Verdict:
        ...


class SilenceTurnDetector:
    """``vad-silence``: end of turn after ``silence_s`` of continuous non-speech.

    ``start_s`` of consecutive speech is needed to OPEN a turn, so a click or
    a cough does not start one (a false turn in a silent room is a finding,
    per the measurement slice). Once open, any speech frame resets the
    silence count, so a pause shorter than ``silence_s`` stays inside the
    turn and a longer one ends it.
    """

    name = "vad-silence"

    def __init__(
        self,
        silence_s: float = DEFAULT_SILENCE_S,
        *,
        classifier: Optional[Classifier] = None,
        start_s: float = 0.09,
    ) -> None:
        self.silence_s = silence_s
        self.classifier = classifier or default_classifier()
        self._start_frames = max(1, int(round(start_s / FRAME_S)))
        self._silence_frames_needed = max(1, int(round(silence_s / FRAME_S)))
        self._run = 0  # consecutive speech frames while no turn is open
        self._silence = 0  # consecutive non-speech frames while a turn is open
        self.in_turn = False

    def feed(self, frame: np.ndarray) -> Verdict:
        speech = self.classifier(frame)
        if not self.in_turn:
            self._run = self._run + 1 if speech else 0
            if self._run >= self._start_frames:
                self.in_turn = True
                self._silence = 0
                self._run = 0
                return Verdict(speech=True, in_turn=True, turn_started=True)
            return Verdict(speech=speech, in_turn=False)
        if speech:
            self._silence = 0
            return Verdict(speech=True, in_turn=True)
        self._silence += 1
        if self._silence >= self._silence_frames_needed:
            self.in_turn = False
            self._silence = 0
            return Verdict(speech=False, in_turn=False, end_of_turn=True)
        return Verdict(speech=False, in_turn=True)


DETECTORS = {SilenceTurnDetector.name: SilenceTurnDetector}


def make_detector(name: str = "vad-silence", **kwargs) -> TurnDetector:
    try:
        return DETECTORS[name](**kwargs)
    except KeyError:
        raise ValueError(f"unknown detector {name!r}; known: {sorted(DETECTORS)}") from None
