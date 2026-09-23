"""`voicemode exchanges tail --heard` (VM-2270 1.4)."""

import json
import re
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from voice_mode import heard
from voice_mode.cli_commands.exchanges import exchanges


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path))
    return tmp_path


def test_format_shows_every_kind_quiet_events_too(base):
    heard.partial("so the", device="airpods")
    heard.turn("so the bot", device="airpods", detector="vad-silence")
    heard.event(heard.EV_HEARTBEAT)
    heard.event(heard.EV_LISTEN_STOPPED, reason="ceiling")
    got = [re.sub(r"\d\d:\d\d:\d\d", "T", heard.format_record(r))
           for r in heard.follow(backlog=10, poll=0, stop=lambda: True)]
    assert got == [
        "#1 T partial mic/airpods  so the",
        "#2 T turn    mic/airpods  so the bot  [vad-silence]",
        "#3 T event   mic  heartbeat",
        "#4 T event   mic  listen-stopped (ceiling)",
    ]


def test_follow_picks_up_new_lines_and_crosses_midnight(base):
    d = heard.log_dir()
    d.mkdir(parents=True)
    yday = heard.log_path(date.today() - timedelta(days=1))
    yday.write_text(json.dumps({"seq": 5, "kind": "turn", "text": "late", "source": "mic"}) + "\n")
    polls = {"n": 0}

    def stop():
        polls["n"] += 1
        if polls["n"] == 1:
            heard.turn("after midnight")  # written while following
            return False
        return True

    seqs = [r["seq"] for r in heard.follow(backlog=10, poll=0, stop=stop)]
    assert seqs == [5, 6]


def test_backlog_is_the_last_n(base):
    for i in range(20):
        heard.turn(f"t{i}")
    got = [r["text"] for r in heard.follow(backlog=3, poll=0, stop=lambda: True)]
    assert got == ["t17", "t18", "t19"]


def test_cli_flag(base):
    heard.turn("through the CLI", device="airpods")
    real = heard.follow
    with patch.object(heard, "follow",
                      lambda backlog: real(backlog=backlog, poll=0, stop=lambda: True)):
        r = CliRunner().invoke(exchanges, ["tail", "--heard", "-n", "5"])
        j = CliRunner().invoke(exchanges, ["tail", "--heard", "-f", "json"])
    assert r.exit_code == 0 and r.output.rstrip().endswith("mic/airpods  through the CLI")
    assert json.loads(j.output)["text"] == "through the CLI"
