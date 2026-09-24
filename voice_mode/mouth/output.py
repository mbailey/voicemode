"""Where the audio goes: ONE named device, or nowhere. Never the default by accident.

Tonight (2026-09-24 ~20:04) the AirPods dropped and the system default fell
back to the MacBook speakers in Mike's bag. So a device is named exactly
(case-insensitive), never matched as a substring: ``airpods`` must not pick
the ``Speakers + AirPods`` aggregate, which plays through the speakers too.
``default`` is the system default, and only when asked for by that name.
``null`` plays nothing, in real time, so stop and cut behave as they would live.
"""

from __future__ import annotations

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


class NullOut:
    name = "null"
    latency = 0.0

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate

    def write(self, block: np.ndarray) -> None:
        time.sleep(len(block) / self.sample_rate)

    def drain(self) -> None:
        pass

    def abort(self) -> None:
        pass


class DeviceOut:
    def __init__(self, name: str, sample_rate: int) -> None:
        idx, self.name = resolve(name)
        sd = _sd()
        self.sample_rate = sample_rate
        self.stream = sd.OutputStream(device=idx, samplerate=sample_rate, channels=1,
                                      dtype="float32")
        self.stream.start()
        self.latency = float(self.stream.latency or 0.0)

    def write(self, block: np.ndarray) -> None:
        self.stream.write(block.reshape(-1, 1))

    def drain(self) -> None:
        self.stream.stop()  # returns once what was written has played
        self.stream.close()

    def abort(self) -> None:
        self.stream.abort()  # drops what is still buffered
        self.stream.close()


def open_output(name: str, sample_rate: int):
    if name == "null":
        return NullOut(sample_rate)
    return DeviceOut(name, sample_rate)
