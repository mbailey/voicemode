"""Where the audio goes: ONE named device, or nowhere. Never the default by accident.

Tonight (2026-09-24 ~20:04) the AirPods dropped and the system default fell
back to the MacBook speakers in Mike's bag. So a device is named exactly
(case-insensitive), never matched as a substring: ``airpods`` must not pick
the ``Speakers + AirPods`` aggregate, which plays through the speakers too.
``default`` is the system default, and only when asked for by that name.
``null`` plays nothing, in real time, so stop and cut behave as they would live.

``pan`` puts a voice in one ear (Mike, voice 20:43: "speak through the left
air pod, the right air pod"): -1 is left only, 1 right only, equal-power
between. Without a pan the stream is mono, exactly as before. A 1-channel
device plays mono and says so (``pan_ignored``) rather than dropping words.
"""

from __future__ import annotations

import math
import os
import queue
import time
from typing import Optional

import numpy as np


class DeviceAbsent(RuntimeError):
    pass


def _sd():
    import sounddevice as sd

    return sd


def output_names(rescan: bool = True) -> list[str]:
    sd = _sd()
    if rescan:  # PortAudio caches the list at init; a resident player must look again
        sd._terminate()
        sd._initialize()
    return [d["name"] for d in sd.query_devices() if d["max_output_channels"] > 0]


def resolve(name: str) -> tuple[Optional[int], str]:
    """(PortAudio index or None for the default, the device's own name). Exact names only."""
    sd = _sd()
    names = output_names()
    if name == "default":
        idx = sd.default.device[1]
        if idx is None or idx < 0:
            raise DeviceAbsent("no default output device")
        return None, sd.query_devices(idx)["name"]
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and d["name"].lower() == name.lower():
            return i, d["name"]
    raise DeviceAbsent(f"output device {name!r} is not present; present: {', '.join(names)}")


class DeviceLost(RuntimeError):
    """The device stopped taking audio mid-play (AirPods out of the ear, into the case)."""


def pan_gains(pan: float) -> tuple[float, float]:
    """Equal-power (left, right) gains for pan in [-1, 1]; -1 is left only."""
    pan = max(-1.0, min(1.0, float(pan)))
    theta = (pan + 1.0) * math.pi / 4.0
    left, right = math.cos(theta), math.sin(theta)
    return (0.0 if left < 1e-9 else left, 0.0 if right < 1e-9 else right)


class NullOut:
    """Plays nothing, in real time, with a one-block buffer like a real device's."""

    name = "null"
    latency = 0.05  # the writer may run this far ahead; a cut drops it
    pan_ignored = None

    def __init__(self, sample_rate: int, pan: Optional[float] = None) -> None:
        self.sample_rate = sample_rate
        self.frames_played = 0
        self.underrun_frames = 0
        self.underruns = 0
        self._clock: Optional[float] = None  # when the audio written so far ends

    def write(self, block: np.ndarray) -> None:
        now = time.monotonic()
        if self._clock is not None and now > self._clock + 0.005:  # the buffer ran dry
            self.underrun_frames += int((now - self._clock) * self.sample_rate)
            self.underruns += 1
        start = now if self._clock is None else max(now, self._clock)
        self._clock = start + len(block) / self.sample_rate
        time.sleep(max(0.0, self._clock - self.latency - now))
        self.frames_played += len(block)

    def drain(self) -> None:
        if self._clock is not None:
            time.sleep(max(0.0, self._clock - time.monotonic()))

    def abort(self) -> None:
        pass


class DeviceOut:
    """A callback stream fed from a short queue, so the player never blocks on the device.

    A blocking ``stream.write`` can wait forever when CoreAudio stops pulling
    (Cora's review of 598e54dd, 20:16): the player hangs, the queue stalls and
    no ``said`` is written. Here ``write`` waits at most ``lost_after_s`` for
    room in the queue, and ``drain`` at most the audio still queued plus
    ``lost_after_s``; past either, ``DeviceLost``. ``frames_played`` counts
    what the device actually pulled, not what was handed over.
    """

    queue_blocks = 4     # ~200 ms of 50 ms blocks between the player and the device
    lost_after_s = 1.0   # Jefferson's "standard maximum" silence, as it happens

    # Underruns: silence the device got MID-line because synthesis fell behind
    # (21:05-21:08 Thu 2026-09-24: the clone dropped below real time and every
    # line broke up, 1.5-8.2 s of gaps each). Always counted. With
    # $VOICEMODE_MOUTH_REBUFFER_S > 0, a dry-out HOLDS until that much is
    # buffered again: a few longer pauses instead of many 50 ms stutters. Off
    # (0) by default: it changes how a line sounds, so it waits for a word.

    def __init__(self, name: str, sample_rate: int, pan: Optional[float] = None) -> None:
        idx, self.name = resolve(name)
        sd = _sd()
        self.sample_rate = sample_rate
        self.gains: Optional[np.ndarray] = None
        self.pan_ignored: Optional[str] = None
        channels = 1
        if pan is not None:
            have = sd.query_devices(idx)["max_output_channels"] if idx is not None else 2
            if have >= 2:
                channels = 2
                self.gains = np.array(pan_gains(pan), dtype=np.float32)
            else:
                self.pan_ignored = f"{have}-channel device"
        self.rebuffer_s = float(os.environ.get("VOICEMODE_MOUTH_REBUFFER_S") or 0)
        self.q: queue.Queue = queue.Queue(
            maxsize=max(self.queue_blocks, math.ceil(self.rebuffer_s / 0.05) + 2))
        self.frames_queued = 0
        self.frames_played = 0
        self.underrun_frames = 0
        self.underruns = 0
        self.draining = False
        self._dry = False
        self._hold = False
        self._cur: Optional[np.ndarray] = None
        self._pos = 0
        self.stream = sd.OutputStream(device=idx, samplerate=sample_rate, channels=channels,
                                      dtype="float32", callback=self._callback)
        self.stream.start()
        self.latency = float(getattr(self.stream, "latency", 0.0) or 0.0)

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ARG002
        if self._hold:
            ahead = (self.frames_queued - self.frames_played) / self.sample_rate
            if ahead >= self.rebuffer_s or self.draining:
                self._hold = False
            else:
                outdata[:] = 0
                self.underrun_frames += frames
                return
        filled = 0
        while filled < frames:
            if self._cur is None or self._pos >= len(self._cur):
                try:
                    self._cur, self._pos = self.q.get_nowait(), 0
                except queue.Empty:
                    break
            n = min(frames - filled, len(self._cur) - self._pos)
            outdata[filled:filled + n] = self._cur[self._pos:self._pos + n]
            self._pos += n
            filled += n
        if filled < frames:
            outdata[filled:] = 0
            if self.frames_queued > 0 and not self.draining:
                self.underrun_frames += frames - filled
                if not self._dry:
                    self.underruns += 1
                    self._dry = True
                if self.rebuffer_s > 0:
                    self._hold = True
        else:
            self._dry = False
        self.frames_played += filled

    def write(self, block: np.ndarray) -> None:
        frames = block.reshape(-1, 1)
        if self.gains is not None:
            frames = frames * self.gains  # (n, 1) * (2,) -> (n, 2)
        try:
            self.q.put(frames, timeout=self.lost_after_s)
        except queue.Full:
            raise DeviceLost(f"{self.name!r} took no audio for {self.lost_after_s:.1f}s") from None
        self.frames_queued += len(block)

    def drain(self) -> None:
        self.draining = True
        left = (self.frames_queued - self.frames_played) / self.sample_rate
        deadline = time.monotonic() + left + self.lost_after_s
        while self.frames_played < self.frames_queued:
            if time.monotonic() > deadline:
                raise DeviceLost(f"{self.name!r} stopped pulling with "
                                 f"{(self.frames_queued - self.frames_played) / self.sample_rate:.2f}s left")
            time.sleep(0.01)
        time.sleep(self.latency)  # the last frames are in the device's own buffer
        self.abort()

    def abort(self) -> None:
        try:
            self.stream.abort()
        finally:
            self.stream.close()


def open_output(name: str, sample_rate: int, pan: Optional[float] = None):
    if name == "null":
        return NullOut(sample_rate, pan)
    return DeviceOut(name, sample_rate, pan)
