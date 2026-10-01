"""Where the audio goes: ONE named device, or nowhere. Never the default by accident.

Tonight (2026-09-24 ~20:04) the AirPods dropped and the system default fell
back to the MacBook speakers in Mike's bag. So a device is named exactly
(case-insensitive), never matched as a substring: ``airpods`` must not pick
the ``Speakers + AirPods`` aggregate, which plays through the speakers too.
``default`` is the system default, and only when asked for by that name.
``null`` plays nothing, in real time, so stop and cut behave as they would live.
``call:<N>`` speaks into live Delta Chat call N through the kin bot's mouth
leg (``call`` alone: the one live call). See :class:`CallOut`.

``pan`` puts a voice in one ear (Mike, voice 20:43: "speak through the left
air pod, the right air pod"): -1 is left only, 1 right only, equal-power
between. Without a pan the stream is mono, exactly as before. A 1-channel
device plays mono and says so (``pan_ignored``) rather than dropping words.
"""

from __future__ import annotations

import glob
import json
import math
import os
import queue
import socket
import struct
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


# -- a live call: call:<N> -----------------------------------------------------
#
# Mike, voice 12:37-12:47 Sat 2026-09-26 (the hero video): he calls the Kin
# bot, the call joins our ears, and our voices have to reach it. The bot that
# holds the call serves a Unix socket (kin's mouthleg.py); the mouth hands it
# finished audio, paced in real time a little ahead of the call, so hold,
# barge-in, retract and the playlist work exactly as they do on the AirPods.

CALL_RATE = 48000       # what the call's voice track holds
CALL_LOOK_S = 1.0       # how long a bot may take to answer a probe or a header


def call_socks() -> list[str]:
    """Every bot's mouth-leg socket. $VOICEMODE_MOUTH_CALL_SOCKS (colon-separated)
    overrides the search of ~/.<agent>/delta-chat[/<profile>]/call-mouth.sock."""
    env = os.environ.get("VOICEMODE_MOUTH_CALL_SOCKS")
    if env:
        return [os.path.expanduser(p) for p in env.split(":") if p]
    home = os.path.expanduser("~")
    return sorted(set(glob.glob(os.path.join(home, ".*", "delta-chat", "call-mouth.sock"))
                      + glob.glob(os.path.join(home, ".*", "delta-chat", "*", "call-mouth.sock"))))


def _ask(sock_path: str, header: dict) -> tuple[socket.socket, dict]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(CALL_LOOK_S)
    try:
        s.connect(sock_path)
        s.sendall((json.dumps(header) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            got = s.recv(4096)
            if not got:
                break
            buf += got
        return s, json.loads(buf or b"{}")
    except BaseException:
        s.close()
        raise


def live_calls() -> list[tuple[int, str, str]]:
    """(call id, who holds it, socket) for every live call any bot can speak into."""
    out = []
    for path in call_socks():
        try:
            s, info = _ask(path, {"probe": True})
            s.close()
        except (OSError, ValueError):
            continue            # a stale socket: that bot is not running
        who = info.get("agent", "?") + (f"/{info['profile']}" if info.get("profile") else "")
        out += [(int(c), who, path) for c in info.get("calls") or []]
    return out


def find_call(name: str) -> tuple[int, str]:
    """``call:<N>`` (or ``call``: the only live call) -> (N, the socket to use)."""
    want = name.split(":", 1)[1].strip() if ":" in name else ""
    if want and not want.isdigit():
        raise DeviceAbsent(f"{name!r}: a call device is call:<N>, N the call's id")
    live = live_calls()
    have = ", ".join(f"call:{c} ({who})" for c, who, _ in live) or "none"
    hits = [x for x in live if not want or x[0] == int(want)]
    if not hits:
        raise DeviceAbsent((f"call {want} is not live" if want else "no call is live")
                           + f"; live calls: {have}")
    if len(hits) > 1:
        raise DeviceAbsent(f"{name!r} is ambiguous; live calls: {have}")
    return hits[0][0], hits[0][2]


class CallOut:
    """A live call as a device: finished audio into the kin bot's mouth leg.

    Paced like :class:`NullOut` - real time, ``latency`` ahead - so the bot's
    queue only ever holds that much, and a cut or a retract drops a fraction
    of a second. ``abort`` tells the bot to cut; if the mouth dies instead,
    the bot sees EOF and cuts anyway. The call ending mid-line is
    :class:`DeviceLost`. Audio is resampled to 48 kHz (linear: speech into
    Opus) and sent as int16.
    """

    latency = 0.2
    lost_after_s = 1.0

    def __init__(self, name: str, sample_rate: int, pan: Optional[float] = None,
                 meta: Optional[dict] = None) -> None:
        self.call, path = find_call(name)
        self.name = f"call:{self.call}"
        self.sample_rate = sample_rate
        self.pan_ignored = "a call is mono" if pan is not None else None
        self.frames_played = 0
        self.underrun_frames = 0
        self.underruns = 0
        self.result: Optional[dict] = None     # the bot's word on how the line ended
        self._clock: Optional[float] = None
        self._last = np.zeros(0, dtype=np.float32)
        self._pos = 0.0
        meta = meta or {}
        header = {"call": self.call, "rate": CALL_RATE, "text": meta.get("text") or "",
                  "who": meta.get("who") or ""}
        try:
            self._sock, reply = _ask(path, header)
        except (OSError, ValueError) as e:
            raise DeviceAbsent(f"call {self.call}: the bot did not answer ({e})") from None
        if not reply.get("ok"):
            self._sock.close()
            raise DeviceAbsent(f"call {self.call}: {reply.get('error') or 'refused'}")
        self._sock.settimeout(self.lost_after_s)

    def _resample(self, block: np.ndarray) -> np.ndarray:
        """Linear, carrying the position across blocks so the seams are smooth."""
        if self.sample_rate == CALL_RATE:
            return block
        x = np.concatenate([self._last, block.astype(np.float32).reshape(-1)])
        if len(x) < 2:
            self._last = x
            return np.zeros(0, dtype=np.float32)
        step = self.sample_rate / CALL_RATE
        n = int(math.floor((len(x) - 1 - self._pos) / step)) + 1 if self._pos <= len(x) - 1 else 0
        pos = self._pos + step * np.arange(n)
        y = np.interp(pos, np.arange(len(x)), x).astype(np.float32)
        self._pos = (pos[-1] + step if n else self._pos) - (len(x) - 1)
        self._last = x[-1:]
        return y

    def _send(self, kind: bytes, payload: bytes = b"") -> None:
        try:
            self._sock.sendall(kind + struct.pack(">I", len(payload)) + payload)
        except socket.timeout:
            raise DeviceLost(f"{self.name} took no audio for {self.lost_after_s:.1f}s") from None
        except OSError as e:
            raise DeviceLost(f"{self.name} ended mid-line ({e})") from None

    def _read_result(self, timeout: float) -> None:
        try:
            self._sock.settimeout(timeout)
            buf = b""
            while not buf.endswith(b"\n"):
                got = self._sock.recv(4096)
                if not got:
                    break
                buf += got
            self.result = json.loads(buf) if buf.strip() else None
        except (OSError, ValueError):
            self.result = None

    def write(self, block: np.ndarray) -> None:
        now = time.monotonic()
        if self._clock is not None and now > self._clock + 0.005:  # synthesis fell behind
            self.underrun_frames += int((now - self._clock) * self.sample_rate)
            self.underruns += 1
        y = self._resample(block)
        pcm = (np.clip(y, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        if pcm:
            self._send(b"A", pcm)
        start = now if self._clock is None else max(now, self._clock)
        self._clock = start + len(block) / self.sample_rate
        time.sleep(max(0.0, self._clock - self.latency - time.monotonic()))
        self.frames_played += len(block)

    def drain(self) -> None:
        self._send(b"D")
        self._read_result(self.lost_after_s)
        if self.result is not None and not self.result.get("ok"):
            self._close()
            raise DeviceLost(f"{self.name}: {self.result.get('ended')} "
                             f"({self.result.get('error') or 'the bot did not keep the line'})")
        if self._clock is not None:        # the call plays what is queued in real time
            time.sleep(max(0.0, self._clock - time.monotonic()))
        self._close()

    def abort(self) -> None:
        try:
            self._send(b"C")
            self._read_result(0.5)
        except DeviceLost:
            pass
        self._close()

    def _close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def open_output(name: str, sample_rate: int, pan: Optional[float] = None,
                meta: Optional[dict] = None):
    """``meta`` (the line's text and who says it) matters only to a call: the bot
    tells its echo guard and its transcript."""
    if name == "null":
        return NullOut(sample_rate, pan)
    if name == "call" or name.startswith("call:"):
        return CallOut(name, sample_rate, pan, meta)
    return DeviceOut(name, sample_rate, pan)
