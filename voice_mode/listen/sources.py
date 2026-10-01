"""Audio sources for ``listen``: fixed-size 16 kHz mono int16 frames.

A source is opened, names itself (``name``: ``mic`` or ``file``) and its
``device``, and yields frames of exactly ``FRAME_SAMPLES`` samples until it
ends or is closed. The loop's clock is the audio itself (frames consumed x
frame length), so a source paced at real time runs the loop at wall time,
and an unpaced source runs a test in milliseconds.

This is listen's OWN capture. It does not use ``converse``'s recording path
(``tools/converse.py``); only ``sounddevice``, which both happen to use.
"""

from __future__ import annotations

import queue
import time
import wave
from pathlib import Path
from typing import Iterator, Optional, Protocol

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad accepts 10, 20 or 30 ms frames
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480
FRAME_S = FRAME_MS / 1000.0


class SourceError(RuntimeError):
    """The source cannot deliver audio (device gone, file unreadable)."""


class Source(Protocol):
    name: str  # "mic" or "file" (the line's `source`)
    device: str  # the line's `device`

    def frames(self) -> Iterator[np.ndarray]:
        ...

    def close(self) -> None:
        ...


class ArraySource:
    """Frames from an in-memory int16 array.

    ``realtime`` paces frame ``i`` to ``start + i * FRAME_S`` on the wall
    clock (catching up without sleeping if the consumer fell behind).
    ``tail_silence_s`` pads the end with silence frames (``None`` pads
    forever, as a quiet room would; ``0`` ends the source when the audio
    ends).
    """

    def __init__(
        self,
        samples: np.ndarray,
        *,
        name: str = "file",
        device: str = "array",
        realtime: bool = True,
        tail_silence_s: Optional[float] = None,
    ) -> None:
        samples = np.asarray(samples, dtype=np.int16).reshape(-1)
        pad = (-len(samples)) % FRAME_SAMPLES
        if pad:
            samples = np.concatenate([samples, np.zeros(pad, dtype=np.int16)])
        self._samples = samples
        self.name = name
        self.device = device
        self.realtime = realtime
        self.tail_silence_s = tail_silence_s
        self._closed = False

    @property
    def duration_s(self) -> float:
        return len(self._samples) / SAMPLE_RATE

    def frames(self) -> Iterator[np.ndarray]:
        start = time.monotonic()
        n_audio = len(self._samples) // FRAME_SAMPLES
        if self.tail_silence_s is None:
            n_total: Optional[int] = None
        else:
            n_total = n_audio + int(round(self.tail_silence_s / FRAME_S))
        silence = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        i = 0
        while not self._closed and (n_total is None or i < n_total):
            if self.realtime:
                delay = start + i * FRAME_S - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            if i < n_audio:
                yield self._samples[i * FRAME_SAMPLES:(i + 1) * FRAME_SAMPLES]
            else:
                yield silence
            i += 1

    def close(self) -> None:
        self._closed = True


def load_wav(path: str | Path) -> np.ndarray:
    """Read a WAV as 16 kHz mono int16, converting channels/rate if needed."""
    path = Path(path).expanduser()
    try:
        with wave.open(str(path), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
    except (OSError, wave.Error) as exc:
        raise SourceError(f"cannot read WAV {path}: {exc}") from exc
    if width != 2:
        raise SourceError(f"{path}: only 16-bit PCM WAV is supported (got {8 * width}-bit)")
    data = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if rate != SAMPLE_RATE:
        data = _resample(data, rate)
    return data


def _resample(data: np.ndarray, rate: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(rate, SAMPLE_RATE)
    out = resample_poly(data.astype(np.float32), SAMPLE_RATE // g, rate // g)
    return np.clip(out, -32768, 32767).astype(np.int16)


class FileSource(ArraySource):
    """``file:PATH.wav`` -- a WAV fed at real time (or unpaced, for tests).

    It ends when the WAV does (capture then stops with reason ``eof``).
    ``tail_silence_s`` pads that many seconds of silence after it first, as
    a room going quiet would; ``None`` pads forever.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        realtime: bool = True,
        tail_silence_s: Optional[float] = 0.0,
    ) -> None:
        self.path = Path(path).expanduser()
        super().__init__(
            load_wav(self.path),
            name="file",
            device=self.path.name,
            realtime=realtime,
            tail_silence_s=tail_silence_s,
        )


def _sd():
    """The ``sounddevice`` module, imported late: the one seam tests patch."""
    import sounddevice

    return sounddevice


def resolve_input_device(device: Optional[int | str] = None) -> tuple[Optional[int], str]:
    """``(index, name)`` of an input device, the name as ``sounddevice`` reports it.

    ``None`` is the system's default input (index ``None``: PortAudio's own
    default). An ``int`` (or all-digit string) is a device index. Any other
    string is a case-insensitive SUBSTRING of an input device's name
    (``--device C930e``); an exact name wins over a substring, and more than
    one substring match is an error that names them.
    """
    sd = _sd()
    try:
        if device is None:
            return None, str(sd.query_devices(kind="input")["name"])
        if isinstance(device, int) or (isinstance(device, str) and device.isdigit()):
            index = int(device)
            info = sd.query_devices(index)
            if int(info.get("max_input_channels", 1)) < 1:
                raise SourceError(f"device {index} ({info['name']!r}) has no input channels")
            return index, str(info["name"])
        inputs = [(i, str(d["name"])) for i, d in enumerate(sd.query_devices()) if int(d.get("max_input_channels", 0)) > 0]
    except SourceError:
        raise
    except Exception as exc:  # PortAudio raises ValueError/PortAudioError
        raise SourceError(f"no input device {device!r}: {exc}") from exc
    want = str(device).lower()
    exact = [(i, n) for i, n in inputs if n.lower() == want]
    if exact:
        return exact[0]
    matches = [(i, n) for i, n in inputs if want in n.lower()]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(repr(n) for _, n in (matches or inputs))
    if not matches:
        raise SourceError(f"no input device matches {device!r}; inputs are: {names}")
    raise SourceError(f"{device!r} matches more than one input device: {names}")


def resolve_input_device_name(device: Optional[int | str] = None) -> str:
    """The input device's name as ``sounddevice`` reports it (e.g. ``airpods``)."""
    return resolve_input_device(device)[1]


class MicSource:
    """The microphone, through ``sounddevice``; input only, never output.

    Opens a 16 kHz mono int16 input stream if the device takes it, else the
    device's own rate, resampled to 16 kHz. A mic that delivers nothing for
    ``stall_s`` raises :class:`SourceError`, so a dead device ends the
    listen with reason ``error`` instead of looking like a silent room.
    """

    name = "mic"

    def __init__(self, device: Optional[int | str] = None, *, stall_s: float = 5.0) -> None:
        self._device_arg, self.device = resolve_input_device(device)
        self.stall_s = stall_s
        self._q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._rate = SAMPLE_RATE
        self._closed = False

    def _open(self) -> None:
        sd = _sd()

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            self._q.put(indata[:, 0].copy())

        last_exc: Optional[Exception] = None
        default_rate = int(sd.query_devices(self._device_arg, kind="input")["default_samplerate"])
        for rate in (SAMPLE_RATE, default_rate):
            try:
                self._stream = sd.InputStream(
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=int(rate * FRAME_MS / 1000),
                    device=self._device_arg,
                    callback=callback,
                )
                self._stream.start()
                self._rate = rate
                return
            except Exception as exc:
                last_exc = exc
        raise SourceError(f"cannot open input device {self.device!r}: {last_exc}")

    def frames(self) -> Iterator[np.ndarray]:
        self._open()
        buf = np.zeros(0, dtype=np.int16)
        while not self._closed:
            try:
                block = self._q.get(timeout=self.stall_s)
            except queue.Empty:
                if self._closed:
                    return
                raise SourceError(f"input device {self.device!r} delivered no audio for {self.stall_s:.0f}s")
            if self._rate != SAMPLE_RATE:
                block = _resample(block, self._rate)
            buf = np.concatenate([buf, block])
            while len(buf) >= FRAME_SAMPLES:
                yield buf[:FRAME_SAMPLES]
                buf = buf[FRAME_SAMPLES:]

    def close(self) -> None:
        self._closed = True
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def open_source(
    spec: str,
    *,
    realtime: bool = True,
    device: Optional[int | str] = None,
    tail_silence_s: Optional[float] = 0.0,
) -> Source:
    """``mic`` (``device``: index or name substring) or ``file:PATH.wav``."""
    if spec == "mic":
        return MicSource(device)
    if spec.startswith("file:"):
        return FileSource(spec[len("file:"):], realtime=realtime, tail_silence_s=tail_silence_s)
    raise SourceError(f"unknown source {spec!r}: expected 'mic' or 'file:PATH.wav'")
