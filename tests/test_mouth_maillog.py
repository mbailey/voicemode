"""The mouth's mailbox is its own log (Mike, voice 21:52-21:54): threaded entries per line."""

from __future__ import annotations

import email
import email.policy
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_mode import mouth
from voice_mode.mouth import inbox, player

from tests.test_mouth_inbox import HOST, deliver


@pytest.fixture
def box(tmp_path, monkeypatch):
    d, logs, mail = tmp_path / "mouth", tmp_path / "logs", tmp_path / "maildir"
    for sub in ("new", "cur", "tmp"):
        (mail / sub).mkdir(parents=True)
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(logs))
    monkeypatch.setenv("VOICEMODE_MOUTH_DEVICE", "null")
    monkeypatch.setenv("VOICEMODE_MOUTH_BACKEND", "silence")
    monkeypatch.setenv("VOICEMODE_MOUTH_MAIL_LOG", str(mail))
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_ALLOW", raising=False)
    return SimpleNamespace(d=d, logs=logs, mail=mail, n=[0])


def entries(mail: Path) -> list:
    out = []
    for f in sorted((mail / "cur").iterdir()):
        m = email.message_from_bytes(f.read_bytes(), policy=email.policy.default)
        if m.get("X-Mouth-Log"):
            out.append(m)
    return out


def play_all(d):
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": 0.3}, daemon=True)
    t.start()
    t.join(8)


def test_a_direct_say_is_one_thread_queued_saying_said(box):
    item = mouth.say("Hello Mike.", spawn=False)
    play_all(box.d)
    es = entries(box.mail)
    assert [e["X-Mouth-Log"] for e in es] == ["queued", "saying", "said"]
    root = es[0]["Message-ID"]
    assert es[0]["In-Reply-To"] is None
    assert es[1]["In-Reply-To"] == root and es[2]["In-Reply-To"] == root
    assert all(e["X-Mouth-Utt"] == item["utt"] for e in es)
    assert es[0]["Subject"] == f'queued {item["utt"]}: "Hello Mike."'
    assert es[2]["Subject"].startswith('said done 0.') and es[2]["Subject"].endswith(': "Hello Mike."')
    assert 'reason: "done"' in es[2].get_content()
    assert not list((box.mail / "new").iterdir())      # never a request for the watcher


def test_a_mailed_line_threads_under_the_request_mail(box):
    mid = deliver(box, "by mail")
    inbox.process_new(box.mail, box.d)
    play_all(box.d)
    es = entries(box.mail)
    assert [e["X-Mouth-Log"] for e in es] == ["queued", "saying", "said"]
    assert all(e["In-Reply-To"] == mid for e in es)


def test_a_retracted_line_still_closes_its_thread(box):
    a, b = mouth.say("word " * 20, spawn=False), mouth.say("never mind", spawn=False)
    t = threading.Thread(target=player.serve, kwargs={"d": box.d, "idle_exit_s": 0.3}, daemon=True)
    t.start()
    time.sleep(0.3)
    mouth.retract(b["utt"])
    mouth.stop()
    t.join(8)
    said = [e for e in entries(box.mail) if e["X-Mouth-Log"] == "said"]
    assert {e["X-Mouth-Utt"]: e["Subject"].split()[1] for e in said} == {a["utt"]: "stop", b["utt"]: "retracted"}


def test_no_mail_log_unless_asked(box, monkeypatch):
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_LOG")
    mouth.say("quiet", spawn=False)
    play_all(box.d)
    assert entries(box.mail) == []


def test_the_watcher_logs_enabled_and_disabled(box, monkeypatch):
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_LOG")
    calls = []

    def stop_after_one(*a, **k):
        calls.append(1)
        raise KeyboardInterrupt
    monkeypatch.setattr(inbox.time, "sleep", stop_after_one)
    with pytest.raises(KeyboardInterrupt):
        inbox.watch(box.mail)
    kinds = [e["X-Mouth-Log"] for e in entries(box.mail)]
    assert kinds == ["enabled", "disabled"]
