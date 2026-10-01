"""The mouth's default voice: the line's own, then the settings file, then
$VOICEMODE_MOUTH_VOICE, then af_sky (Mike, voice 03:14 Sat 2026-09-26)."""

import json

import pytest

from voice_mode import mouth
from voice_mode.mouth import voices


@pytest.fixture
def d(tmp_path, monkeypatch):
    d = tmp_path / "mouth"
    d.mkdir()
    monkeypatch.setenv("VOICEMODE_MOUTH_DIR", str(d))
    monkeypatch.setenv("VOICEMODE_MOUTH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("VOICEMODE_MOUTH_SETTINGS", raising=False)
    monkeypatch.delenv("VOICEMODE_MOUTH_VOICE", raising=False)
    monkeypatch.delenv("VOICEMODE_MOUTH_MAIL_LOG", raising=False)
    return d


def queued(d, **kw):
    return mouth.say("hello", device="null", spawn=False, d=d, **kw)["voice"]


def test_builtin_when_nothing_is_set(d):
    assert voices.default_voice(d) == ("af_sky", "builtin")
    assert queued(d) == "af_sky"


def test_env_when_no_file(d, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_VOICE", "laurie")
    assert voices.default_voice(d) == ("laurie", "env")
    assert queued(d) == "laurie"


def test_settings_file_beats_env(d, monkeypatch):
    monkeypatch.setenv("VOICEMODE_MOUTH_VOICE", "laurie")
    (d / "settings.json").write_text(json.dumps({"voice": "bf_emma", "output": "default"}))
    assert voices.default_voice(d) == ("bf_emma", "settings")
    assert queued(d) == "bf_emma"


def test_the_lines_own_voice_beats_the_file(d):
    (d / "settings.json").write_text(json.dumps({"voice": "bf_emma"}))
    assert queued(d, voice="pip") == "pip"


def test_read_for_every_line(d):
    f = d / "settings.json"
    f.write_text(json.dumps({"voice": "bf_emma"}))
    assert queued(d) == "bf_emma"
    f.write_text(json.dumps({"voice": "am_adam"}))
    assert queued(d) == "am_adam"


@pytest.mark.parametrize("body", ["", "not json", "[1, 2]", '{"voice": ""}', '{"voice": 7}',
                                  '{"output": "default"}'])
def test_a_file_that_does_not_answer_falls_through(d, monkeypatch, body):
    monkeypatch.setenv("VOICEMODE_MOUTH_VOICE", "laurie")
    (d / "settings.json").write_text(body)
    assert voices.default_voice(d) == ("laurie", "env")


def test_settings_path_from_env(d, tmp_path, monkeypatch):
    f = tmp_path / "elsewhere" / "mouth.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"voice": "bm_george"}))
    monkeypatch.setenv("VOICEMODE_MOUTH_SETTINGS", str(f))
    assert voices.settings_path(d) == f
    assert queued(d) == "bm_george"


def test_voices_lists_both_kinds_and_the_default(d, monkeypatch):
    monkeypatch.setattr(voices, "clones", lambda: ["laurie", "pip"])
    (d / "settings.json").write_text(json.dumps({"voice": "pip"}))
    v = voices.voices(d)
    assert v["default"] == "pip" and v["from"] == "settings"
    assert v["settings"] == str(d / "settings.json")
    assert "af_sky" in v["kokoro"] and v["clone"] == ["laurie", "pip"]
