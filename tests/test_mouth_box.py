"""The queue is a maildir (Mike, 02:55 / 03:26 Sat 2026-09-26): new = to
speak, cur = done and flagged; a playlist by priority; replace = supersede."""

import email
import email.policy
import json
import threading
from pathlib import Path

import pytest

from voice_mode import mouth
from voice_mode.mouth import box, paths, player


@pytest.fixture
def d(tmp_path, monkeypatch):
    d = tmp_path / "mouth"
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("VOICEMODE_MOUTH_DEVICE", "null")
    monkeypatch.setenv("VOICEMODE_MOUTH_BACKEND", "silence")
    monkeypatch.delenv("VOICEMODE_MOUTH_MAILBOX", raising=False)
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_LOG", raising=False)
    return d


def spoken(tmp_path) -> list:
    return [json.loads(x)["text"] for f in sorted((tmp_path / "logs").glob("heard_*.jsonl"))
            for x in f.read_text().splitlines() if json.loads(x)["kind"] == "saying"]


def play_all(d, idle=0.3):
    t = threading.Thread(target=player.serve, kwargs={"d": d, "idle_exit_s": idle}, daemon=True)
    t.start()
    t.join(10)


def test_where_the_box_is(tmp_path, monkeypatch):
    monkeypatch.delenv("VOICEMODE_MOUTH_MAILBOX", raising=False)
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / "vm"))
    live = paths.default_mouth_dir()
    assert box.box_dir(live) == Path.home() / ".mail" / "agents" / "mouth"   # the live mouth's own
    assert box.box_dir(tmp_path / "other") == tmp_path / "other" / "box"     # a test's never is
    monkeypatch.setenv("VOICEMODE_MOUTH_MAILBOX", str(tmp_path / "m"))
    assert box.box_dir(live) == tmp_path / "m"


def test_say_drops_a_mail_into_new(d):
    item = mouth.say("Hello *Mike*  ", voice="pip", hold="turn-end", expires_s=30, interest="high",
                     priority=20, d=d, spawn=False)
    (f,) = (d / "box" / "new").iterdir()
    m = email.message_from_bytes(f.read_bytes(), policy=email.policy.default)
    assert m["Message-ID"] == item["mail_id"] and m["X-Mouth-Utt"] == item["utt"]
    assert (m["X-Mouth-Voice"], m["X-Mouth-When"], m["X-Mouth-Expires"], m["X-Mouth-Priority"]) == \
        ("pip", "turn-end", "30", "20")
    back = box.read(f, d)
    assert back["text"] == "Hello *Mike*  ", "a dropped line is spoken exactly, never un-markdowned"
    assert (back["priority"], back["_rank"], back["interest"]) == (20, 20.0, "high")


def test_done_is_flagged_in_cur(d, tmp_path):
    mouth.say("one", d=d, spawn=False)
    play_all(d)
    (f,) = (d / "box" / "cur").iterdir()
    assert f.name.endswith(":2,S") and not list((d / "box" / "new").iterdir())


def test_a_playlist_by_say(d, tmp_path):
    mouth.say("plain", d=d, spawn=False)
    mouth.say("twenty", priority=20, d=d, spawn=False)
    mouth.say("next", priority="next", d=d, spawn=False)
    mouth.say("ten", priority="10", d=d, spawn=False)
    assert [x["text"] for x in box.Queue(d).lines()] == ["next", "ten", "twenty", "plain"]
    assert mouth.status(d)["queued"] == 4
    play_all(d)
    assert spoken(tmp_path) == ["next", "ten", "twenty", "plain"]


def test_a_bad_priority_is_refused(d):
    with pytest.raises(ValueError):
        mouth.say("x", priority="soonish", d=d, spawn=False)


def test_amend_keeps_the_place_and_files_the_old_one_when_taken(d, tmp_path):
    a = mouth.say("first", d=d, spawn=False)
    b = mouth.say("second, draft", d=d, spawn=False)
    mouth.say("third", d=d, spawn=False)
    mouth.amend(b["utt"], "second, final", d=d)
    assert [x["text"] for x in box.Queue(d).lines()] == ["first", "second, final", "third"]
    assert box.Queue(d).find(b["utt"])["amended_from"] == "second, draft"
    play_all(d)
    assert spoken(tmp_path) == ["first", "second, final", "third"]
    flags = sorted(f.name.split(":2,")[1] for f in (d / "box" / "cur").iterdir())
    assert flags == ["S", "S", "S", "T"]
    assert a["utt"] != b["utt"]


def test_retract_files_it_unspoken(d, tmp_path):
    a = mouth.say("keep", d=d, spawn=False)
    b = mouth.say("drop", d=d, spawn=False)
    rec = mouth.retract(b["utt"], d=d)
    assert rec["reason"] == "retracted"
    (f,) = (d / "box" / "cur").iterdir()
    assert f.name.endswith(":2,T")
    play_all(d)
    assert spoken(tmp_path) == ["keep"]
    with pytest.raises(ValueError):
        mouth.retract(a["utt"], d=d)                   # already spoken: nothing to retract


def test_a_taken_line_files_what_it_replaced_at_once(d):
    """If the player dies mid-line, a replaced opener must not come back."""
    b = mouth.say("draft", d=d, spawn=False)
    mouth.amend(b["utt"], "final", d=d)
    q = box.Queue(d)
    (x,) = q.lines()
    assert q.take(x) is not None
    assert not list((d / "box" / "new").iterdir())
    assert sorted(f.name.split(":2,")[1] for f in (d / "box" / "cur").iterdir()) == ["", "T"]


def test_the_body_round_trips_exactly(d):
    for text in ["word " * 20, "héllo — “quotes”", "two\nlines", "x" * 1200, "ends in a newline\n"]:
        f = box.drop(box.ensure(d / "box"), {"utt": "u1", "text": text, "requested_t": 1.0})
        assert box.read(f, d)["text"] == text
        f.unlink()
