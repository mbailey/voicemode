"""mail feeds mouth (Mike, voice 21:40): a mail to mouth@<host> becomes a line.

No sound, no server, no postfix: mails are written straight into a temp
maildir's new/, the silence backend speaks them onto the null device.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_mode.mouth import inbox, player

HOST = socket.gethostname().split(".")[0].lower()


@pytest.fixture
def box(tmp_path, monkeypatch):
    d, logs, mail = tmp_path / "mouth", tmp_path / "logs", tmp_path / "maildir"
    for sub in ("new", "cur", "tmp"):
        (mail / sub).mkdir(parents=True)
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(logs))
    monkeypatch.setenv("VOICEMODE_MOUTH_DEVICE", "null")
    monkeypatch.setenv("VOICEMODE_MOUTH_BACKEND", "silence")
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_ALLOW", raising=False)
    return SimpleNamespace(d=d, logs=logs, mail=mail, n=[0])


def deliver(box, body="", subject="hi", sender=f"cora@{HOST}.sparrow-hydra.ts.net", **headers) -> str:
    box.n[0] += 1
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, f"mouth@{HOST}", subject
    mid = f"<{box.n[0]}.test@{HOST}.session-mail>"
    m["Message-ID"] = mid
    m["X-Session-From"] = "9af31984"
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    m.set_content(body)
    (box.mail / "new" / f"{time.time_ns()}.{box.n[0]}.{HOST}").write_bytes(bytes(m))
    return mid


def lines(logs):
    return [json.loads(x) for f in sorted(Path(logs).glob("heard_*.jsonl")) for x in f.read_text().splitlines()]


def run_player(d, idle=0.3):
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": idle}, daemon=True)
    t.start()
    return t


def test_a_mail_becomes_a_line_spoken_as_its_sender(box):
    mid = deliver(box, "**Hello** Mike, the `mouth` reads [mail](http://x).")
    r = inbox.process_new(box.mail, box.d)
    assert [x["action"] for x in r] == ["queued"]
    assert not list((box.mail / "new").iterdir()) and len(list((box.mail / "cur").iterdir())) == 1
    run_player(box.d).join(5)
    saying = next(x for x in lines(box.logs) if x["kind"] == "saying")
    assert saying["text"] == "Hello Mike, the mouth reads mail."
    assert (saying["agent"], saying["session"], saying["mail_id"]) == ("cora", "9af31984", mid)


def test_an_empty_body_speaks_the_subject(box):
    deliver(box, "", subject="Parking runs out in forty seconds")
    inbox.process_new(box.mail, box.d)
    run_player(box.d).join(5)
    assert next(x for x in lines(box.logs) if x["kind"] == "saying")["text"] == "Parking runs out in forty seconds"


def test_supersedes_amends_a_line_not_yet_spoken(box):
    deliver(box, "word " * 20)                      # keeps the player busy
    old = deliver(box, "the old words")
    inbox.process_new(box.mail, box.d)
    th = run_player(box.d)
    time.sleep(0.3)
    deliver(box, "the new words", Supersedes=old)
    r = inbox.process_new(box.mail, box.d)
    assert r[0]["action"] == "amended"
    th.join(8)
    spoken = [x["text"] for x in lines(box.logs) if x["kind"] == "saying"]
    assert "the new words" in spoken and "the old words" not in spoken


def test_supersedes_with_an_empty_body_retracts(box):
    deliver(box, "word " * 20)
    old = deliver(box, "never mind this")
    inbox.process_new(box.mail, box.d)
    th = run_player(box.d)
    time.sleep(0.3)
    deliver(box, "", subject="retract", Supersedes=old)
    assert inbox.process_new(box.mail, box.d)[0]["action"] == "retracted"
    th.join(8)
    said = [x for x in lines(box.logs) if x["kind"] == "said"]
    assert any(x["reason"] == "retracted" for x in said)
    assert "never mind this" not in [x["text"] for x in lines(box.logs) if x["kind"] == "saying"]


def test_a_correction_to_a_line_already_spoken_is_queued_as_news(box):
    old = deliver(box, "the meeting is at three")
    inbox.process_new(box.mail, box.d)
    run_player(box.d).join(5)
    deliver(box, "correction, the meeting is at four", Supersedes=old)
    assert inbox.process_new(box.mail, box.d)[0]["action"] == "queued"


def test_importance_high_and_x_mouth_priority(box):
    deliver(box, "first")
    deliver(box, "second")
    deliver(box, "urgent", Importance="high")
    inbox.process_new(box.mail, box.d)
    run_player(box.d).join(8)
    assert [x["text"] for x in lines(box.logs) if x["kind"] == "saying"] == ["urgent", "first", "second"]


def test_per_line_headers(box):
    deliver(box, "left ear please", X_Mouth_Channel="left", X_Mouth_Voice="af_bella")
    inbox.process_new(box.mail, box.d)
    run_player(box.d).join(5)
    saying = next(x for x in lines(box.logs) if x["kind"] == "saying")
    assert (saying["pan"], saying["voice"]) == (-1.0, "af_bella")


def test_a_stranger_is_refused_and_never_spoken(box):
    deliver(box, "buy now", sender="spam@example.com")
    r = inbox.process_new(box.mail, box.d)
    assert r[0]["action"] == "refused"
    assert not list((box.mail / "new").iterdir())          # filed, not left to retry
    assert not (box.d / "queue").exists() or not list((box.d / "queue").glob("*.json"))


def test_the_allow_list_admits_a_named_sender(box, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_MAIL_ALLOW", "mike@failmode.com,@ms2.sparrow-hydra.ts.net")
    deliver(box, "from ms2", sender="cora@ms2.sparrow-hydra.ts.net")
    deliver(box, "from mike", sender="mike@failmode.com")
    assert [x["action"] for x in inbox.process_new(box.mail, box.d)] == ["queued", "queued"]


def test_a_sound_by_mail(box, tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg")
    import wave
    import numpy as np
    wav = tmp_path / "chime.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes((np.zeros(24000) + 1000).astype("<i2").tobytes())
    deliver(box, "", subject="chime", X_Mouth_File=str(wav), X_Mouth_End="0.5")
    inbox.process_new(box.mail, box.d)
    run_player(box.d).join(5)
    said = next(x for x in lines(box.logs) if x["kind"] == "said")
    assert said["backend"] == "file" and said["dur_s"] == pytest.approx(0.5, abs=0.03)


def test_speakable():
    assert inbox.speakable("## Head\n- one\n- **two**\n> quoted") == "Head\none\ntwo\nquoted"
