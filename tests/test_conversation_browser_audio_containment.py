"""scripts/conversation_browser.py: /audio/ stays inside AUDIO_DIR (VM-2484).

CodeQL py/path-injection flagged ``serve_audio``: the URL's filename went
straight into a filesystem path. ``contained_path`` now resolves each candidate
and refuses anything outside AUDIO_DIR. Flask is an optional runtime extra
(``voice-mode[scripts]``) and is also in the ``[test]`` extra, so these tests
run under ``make test``; they skip only in an environment without flask.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("flask")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def browser(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / "vm"))
    import scripts.conversation_browser as cb

    cb = importlib.reload(cb)
    audio = tmp_path / "vm" / "audio"
    (audio / "2025" / "07").mkdir(parents=True)
    cb.app.config["TESTING"] = True
    return cb, audio


def test_contained_path_accepts_inside_and_refuses_outside(browser, tmp_path):
    cb, audio = browser
    inside = audio / "2025" / "07" / "x.wav"
    assert cb.contained_path(inside, audio) == os.path.realpath(inside)
    assert cb.contained_path(audio / ".." / "secret.txt", audio) is None
    assert cb.contained_path(Path("/etc/passwd"), audio) is None
    # The directory itself is not a file inside it.
    assert cb.contained_path(audio, audio) is None
    # A sibling whose name merely starts with the base is outside.
    assert cb.contained_path(tmp_path / "vm" / "audio-evil" / "x.wav", audio) is None


def test_serves_dated_and_flat_files(browser):
    cb, audio = browser
    (audio / "2025" / "07" / "20250702_100000_tts.wav").write_bytes(b"dated")
    (audio / "old_tts.wav").write_bytes(b"flat")
    client = cb.app.test_client()

    assert client.get("/audio/20250702_100000_tts.wav").data == b"dated"
    assert client.get("/audio/old_tts.wav").data == b"flat"
    assert client.get("/audio/missing.wav").status_code == 404


def test_traversal_is_refused(browser, tmp_path):
    cb, audio = browser
    (tmp_path / "vm" / "secret.txt").write_text("secret")

    # Called directly: Flask's <filename> converter already stops "/", but
    # ".." on its own must still not reach outside AUDIO_DIR.
    with cb.app.test_request_context():
        resp = cb.serve_audio("..")
    assert resp[1] in (400, 404)

    client = cb.app.test_client()
    resp = client.get("/audio/..%2Fsecret.txt")
    assert resp.status_code in (400, 404)
    assert b"secret" not in resp.data


def test_debug_off_by_default():
    source = (Path(__file__).parent.parent / "scripts" / "conversation_browser.py").read_text()
    assert "debug=True" not in source
    assert "VOICEMODE_BROWSER_DEBUG" in source
