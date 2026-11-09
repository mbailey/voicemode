"""TTS temp files are closed before they are deleted.

Windows refuses to delete a file that is still open (WinError 32). core.py deletes its TTS
temp files inside the ``with`` that opened them, so on Windows every buffered turn failed
after playback. These tests apply Windows' rule on any OS.
"""
import os
import tempfile
from pathlib import Path

from voice_mode.core import _close_and_unlink


def test_closes_before_it_deletes(monkeypatch):
    handle = tempfile.NamedTemporaryFile(suffix=".pcm", delete=False)
    handle.write(b"\0\0")
    real_unlink = os.unlink

    def windows_unlink(path):
        if not handle.closed:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", windows_unlink)
    _close_and_unlink(handle)
    assert handle.closed
    assert not Path(handle.name).exists()


def test_a_failed_delete_does_not_raise(monkeypatch, tmp_path):
    handle = open(tmp_path / "x.pcm", "wb")

    def refuse(path):
        raise PermissionError(32, "in use")

    monkeypatch.setattr(os, "unlink", refuse)
    _close_and_unlink(handle)  # must not raise: the audio already played
    assert handle.closed


def test_no_temp_file_is_deleted_while_open():
    source = (Path(__file__).resolve().parent.parent / "voice_mode" / "core.py").read_text()
    assert "os.unlink(tmp_file.name)" not in source
