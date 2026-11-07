"""call:<N> - the mouth speaks into a live call through the kin bot's mouth leg.

A fake bot speaks the leg's protocol on a real Unix socket (kin's
mouthleg.py is the real one; its own tests cover that side).
"""

from __future__ import annotations

import json
import os
import socket
import struct
import tempfile
import threading
import time

import numpy as np
import pytest

from voice_mode.mouth import output, player

from test_mouth import box, lines, run_player, say  # noqa: F401 - fixtures


class FakeBot:
    def __init__(self, calls, agent="pip", listen=True):
        self.dir = tempfile.mkdtemp(prefix="mc-", dir="/tmp")   # AF_UNIX paths are short
        self.path = os.path.join(self.dir, "call-mouth.sock")
        self.calls, self.agent = list(calls), agent
        self.lines: list[dict] = []
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(self.path)
        if listen:
            self.srv.listen(8)
            threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        f = c.makefile("rb")
        hdr = json.loads(f.readline())
        if hdr.get("probe"):
            c.sendall((json.dumps({"ok": True, "agent": self.agent, "profile": "",
                                   "calls": self.calls}) + "\n").encode())
            c.close()
            return
        if hdr.get("call") not in self.calls:
            c.sendall(b'{"ok": false, "error": "call is not live here"}\n')
            c.close()
            return
        line = {"header": hdr, "samples": 0, "ended": "eof", "pcm": []}
        self.lines.append(line)
        c.sendall(json.dumps({"ok": True, "call": hdr["call"]}).encode() + b"\n")
        while True:
            head = f.read(5)
            if len(head) < 5:
                break
            kind, n = head[:1], struct.unpack(">I", head[1:])[0]
            payload = f.read(n) if n else b""
            if kind == b"A":
                a = np.frombuffer(payload, dtype="<i2")
                line["samples"] += len(a)
                line["pcm"].append(a)
            else:
                line["ended"] = {b"D": "done", b"C": "cut"}[kind]
                break
        ok = line["ended"] == "done"
        try:
            c.sendall(json.dumps({"ok": ok, "ended": line["ended"]}).encode() + b"\n")
        except OSError:
            pass
        c.close()

    def close(self):
        self.srv.close()


@pytest.fixture
def bots(monkeypatch):
    made = []

    def make(*a, **kw):
        b = FakeBot(*a, **kw)
        made.append(b)
        monkeypatch.setenv("VOICEMODE_MOUTH_CALL_SOCKS", ":".join(x.path for x in made))
        return b
    yield make
    for b in made:
        b.close()


def test_no_bot_no_call(monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_CALL_SOCKS", "/tmp/nope-nothing-here.sock")
    with pytest.raises(output.DeviceAbsent, match="no call is live; live calls: none"):
        output.open_output("call", 24000)


def test_the_wrong_call_names_the_live_ones(bots):
    bots([5531])
    with pytest.raises(output.DeviceAbsent, match=r"call 77 is not live; live calls: call:5531 \(pip\)"):
        output.open_output("call:77", 24000)


def test_a_call_device_takes_a_number(bots):
    bots([5531])
    with pytest.raises(output.DeviceAbsent, match="call:<N>"):
        output.open_output("call:kin", 24000)


def test_a_stale_socket_is_skipped(bots):
    bots([1], listen=False)          # the file is there, nobody is listening
    live = bots([5531])
    out = output.open_output("call", 24000)
    out.abort()
    assert live.lines[0]["header"]["call"] == 5531


def test_bare_call_with_two_live_calls_is_ambiguous(bots):
    bots([1])
    bots([2], agent="cora")
    with pytest.raises(output.DeviceAbsent, match="ambiguous"):
        output.open_output("call", 24000)


def test_a_line_goes_in_whole_at_48k_and_the_bot_keeps_it(bots):
    bot = bots([5531])
    out = output.open_output("call:5531", 24000, meta={"text": "Morning Mike.", "who": "pip"})
    assert out.name == "call:5531" and out.pan_ignored is None
    t0 = time.monotonic()
    for _ in range(6):                               # 0.3 s in 50 ms blocks
        out.write(np.full(1200, 0.25, dtype=np.float32))
    out.drain()
    took = time.monotonic() - t0
    assert 0.25 < took < 0.6                         # paced in real time, not dumped
    line = bot.lines[0]
    assert line["ended"] == "done" and out.result == {"ok": True, "ended": "done"}
    assert line["header"] == {"call": 5531, "rate": 48000, "text": "Morning Mike.", "who": "pip"}
    assert abs(line["samples"] - 14400) <= 2         # 0.3 s at 48 kHz
    assert out.frames_played == 7200


def test_a_cut_tells_the_bot(bots):
    bot = bots([5531])
    out = output.open_output("call:5531", 24000)
    out.write(np.zeros(1200, dtype=np.float32))
    out.abort()
    time.sleep(0.05)
    assert bot.lines[0]["ended"] == "cut"


def test_resampling_has_no_seams():
    out = output.CallOut.__new__(output.CallOut)
    out.sample_rate, out._last, out._pos = 24000, np.zeros(0, dtype=np.float32), 0.0
    ramp = np.linspace(-1, 1, 24000, dtype=np.float32)
    y = np.concatenate([out._resample(ramp[i:i + 1200]) for i in range(0, 24000, 1200)])
    assert abs(len(y) - 48000) <= 2
    assert np.all(np.diff(y) > 0)                    # monotonic straight through every seam


def test_pan_on_a_call_plays_mono_and_says_so(bots):
    bots([5531])
    out = output.open_output("call:5531", 24000, pan=-1)
    assert out.pan_ignored == "a call is mono"
    out.abort()


def test_the_player_speaks_into_the_call(box, bots):  # noqa: F811
    bot = bots([5531])
    item = say("Hello from the mouth.", device="call:5531")
    run_player(box.d).join(10)
    said = [r for r in lines(box.logs) if r["kind"] == "said"]
    assert said and said[0]["utt"] == item["utt"]
    assert said[0]["reason"] == "done" and said[0]["device"] == "call:5531"
    assert bot.lines[0]["header"]["text"] == "Hello from the mouth."
    assert bot.lines[0]["header"]["who"] == "pip"
    assert bot.lines[0]["ended"] == "done"


def test_the_player_refuses_a_call_that_is_not_live(box, bots):  # noqa: F811
    bots([5531])
    say("Hello?", device="call:9")
    run_player(box.d).join(10)
    said = [r for r in lines(box.logs) if r["kind"] == "said"]
    assert said[0]["reason"] == "device-absent" and "call 9 is not live" in said[0]["detail"]
