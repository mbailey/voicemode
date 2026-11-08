"""TTS temp files are closed before they are deleted.

Windows refuses to delete a file that is still open (WinError 32). core.py deletes its TTS
temp files inside the ``with`` that opened them, so on Windows every buffered turn failed
after playback. These tests apply Windows' rule on any OS.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.core import _close_and_unlink, text_to_speech


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


# A whole buffered turn through text_to_speech (VM-2536, on top of #587): the
# helper is used where it matters, and a turn on Linux/macOS is unchanged.

def _openai_client(audio: bytes):
    response = MagicMock()
    response.read = AsyncMock(return_value=audio)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    client = MagicMock()
    client.audio.speech.with_streaming_response.create = MagicMock(return_value=response)
    return client


@pytest.fixture
def buffered_turn(monkeypatch, tmp_path):
    """Run one buffered PCM turn with no device, recording what it did.

    Temp files go to ``tmp_path/tts`` so a leftover is visible; ``Path.home`` is
    ``tmp_path/manual-playback-home`` so the last-resort "save for manual playback" copy is too.
    """
    tts_dir = tmp_path / "tts"
    home = tmp_path / "manual-playback-home"
    tts_dir.mkdir()
    home.mkdir()
    opened = []
    real_ntf = tempfile.NamedTemporaryFile

    def recording_ntf(*args, **kwargs):
        kwargs["dir"] = str(tts_dir)
        handle = real_ntf(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", recording_ntf)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("voice_mode.config.STREAMING_ENABLED", False)
    player = MagicMock()
    pydub_play = MagicMock()

    async def run():
        with patch("voice_mode.core.NonBlockingAudioPlayer", return_value=player), \
             patch("voice_mode.core._wait_for_player_with_control", new=AsyncMock(return_value=False)), \
             patch("pydub.playback.play", pydub_play):
            return await text_to_speech(
                text="hello",
                openai_clients={"tts": _openai_client(b"\0\0" * 2400)},
                tts_model="tts-1",
                tts_voice="nova",
                tts_base_url="https://api.openai.com/v1",
                audio_format="pcm",
            )

    def windows_rule():
        real_unlink = os.unlink

        def unlink(path, *args, **kwargs):
            if any(h.name == os.fspath(path) and not h.closed for h in opened):
                raise PermissionError(
                    13, "[WinError 32] The process cannot access the file because "
                    "it is being used by another process", os.fspath(path))
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", unlink)

    return {"run": run, "windows_rule": windows_rule, "player": player,
            "pydub_play": pydub_play, "tts_dir": tts_dir, "home": home}


@pytest.mark.asyncio
async def test_buffered_turn_as_today_on_linux_and_macos(buffered_turn):
    """No Windows rule: one play, success, temp file gone, nothing saved to home."""
    ok, _metrics = await buffered_turn["run"]()
    assert ok is True
    assert buffered_turn["player"].play.call_count == 1
    assert buffered_turn["pydub_play"].call_count == 0
    assert list(buffered_turn["tts_dir"].iterdir()) == []
    assert list(buffered_turn["home"].iterdir()) == []


@pytest.mark.asyncio
async def test_buffered_turn_survives_the_windows_rule(buffered_turn):
    """Windows rule: the same as above. Before #587 the delete failed after the
    audio played, so the turn replayed through pydub, copied the reply into the
    home directory, and then raised WinError 32 out of text_to_speech."""
    buffered_turn["windows_rule"]()
    ok, _metrics = await buffered_turn["run"]()
    assert ok is True
    assert buffered_turn["player"].play.call_count == 1
    assert buffered_turn["pydub_play"].call_count == 0
    assert list(buffered_turn["tts_dir"].iterdir()) == []
    assert list(buffered_turn["home"].iterdir()) == []
