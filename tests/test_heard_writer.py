"""The heard log writer (ambient-listen task 1.1, VM-2270).

Every test writes into a tmp VOICEMODE_BASE_DIR; nothing touches ~/.voicemode.
"""

import json
import multiprocessing
from datetime import date, timedelta

import pytest

from voice_mode import heard


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path))
    return tmp_path


def lines(path):
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_path_is_a_sibling_of_the_exchange_log(base):
    assert heard.log_path(date(2026, 9, 24)) == (
        base / "logs" / "conversations" / "heard_2026-09-24.jsonl")


def test_one_line_per_record_seq_counts_from_one(base):
    heard.partial("so the bot will", device="airpods")
    heard.partial("post what I say", device="airpods")
    heard.turn("so the bot will post what I say", detector="vad-silence", device="airpods")
    heard.event(heard.EV_HEARTBEAT)
    recs = lines(heard.log_path())
    assert [r["seq"] for r in recs] == [1, 2, 3, 4]
    assert [r["kind"] for r in recs] == ["partial", "partial", "turn", "event"]
    assert recs[0]["final"] is False and recs[2]["final"] is True
    assert "final" not in recs[3]
    assert recs[2]["detector"] == "vad-silence"
    assert recs[3]["event"] == "heartbeat"
    assert all(r["source"] == "mic" and r["v"] == heard.SCHEMA for r in recs)
    assert "+" in recs[0]["ts"] or "-" in recs[0]["ts"][19:]  # offset present


def test_none_fields_are_dropped_extra_fields_kept(base):
    rec = heard.turn("hello", via="converse", session=None, agent="pip")
    assert "session" not in rec and rec["via"] == "converse" and rec["agent"] == "pip"


def test_seq_keeps_counting_across_midnight(base):
    d = heard.log_dir()
    d.mkdir(parents=True)
    yesterday = heard.log_path(date.today() - timedelta(days=1))
    yesterday.write_text(json.dumps({"seq": 41, "kind": "turn", "text": "x"}) + "\n")
    rec = heard.turn("after midnight")
    assert rec["seq"] == 42
    assert lines(heard.log_path())[0]["seq"] == 42


def test_a_torn_last_line_is_skipped_not_trusted(base):
    heard.turn("one")
    heard.turn("two")
    with open(heard.log_path(), "a") as f:
        f.write('{"seq": 999, "kind": "tu')  # a write in flight
    assert heard.last_seq() == 2


def test_bad_calls_refused(base):
    with pytest.raises(ValueError):
        heard.append("utterance", text="x")
    with pytest.raises(ValueError):
        heard.append("turn")
    with pytest.raises(ValueError):
        heard.append("event")
    with pytest.raises(ValueError, match="writer's to set"):
        heard.turn("x", seq=7)
    assert not heard.log_path().exists()


def _burst(n):
    for i in range(n):
        heard.partial(f"chunk {i}")


def test_concurrent_writers_never_share_a_seq(base):
    ctx = multiprocessing.get_context("fork")
    procs = [ctx.Process(target=_burst, args=(50,)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0
    seqs = [r["seq"] for r in lines(heard.log_path())]
    assert sorted(seqs) == list(range(1, 201))
    assert seqs == sorted(seqs)  # appended in seq order under the lock
