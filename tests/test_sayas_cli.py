"""Unit tests for the sayas CLI entry point."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import sayas_command


# The sayas_command imports _load_voices_json from voice_mode.tools.clone.profiles
# at call time. Patch at the source module.
PROFILES_MODULE = "voice_mode.tools.clone.profiles"


@pytest.fixture
def voices_data():
    """Return test voice profile data."""
    return {
        "voices": {
            "alice": {
                "ref_audio": "/tmp/voices/alice.wav",
                "ref_text": "Hello, I am Alice.",
                "description": "Test voice Alice",
                "base_url": "http://localhost:8890/v1",
                "model": "test-model",
            },
            "bob": {
                "ref_audio": "/tmp/voices/bob.wav",
                "ref_text": "Hi, I am Bob.",
                "description": "Test voice Bob",
            },
        }
    }


@pytest.fixture
def empty_voices_data():
    """Return empty voice profile data."""
    return {"voices": {}}


def _patch_load(data):
    """Patch _load_voices_json at the source to return given data."""
    return patch(f"{PROFILES_MODULE}._load_voices_json", return_value=data)


class TestSayasHelp:
    """Test help and usage output."""

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(sayas_command, ["--help"])
        assert result.exit_code == 0
        assert "Speak as someone" in result.output
        assert "--list" in result.output
        assert "--preview" in result.output
        assert "--output" in result.output
        assert "--completion" in result.output

    def test_no_args_shows_help(self, empty_voices_data):
        """With no args and no voice, should show help and exit 1."""
        runner = CliRunner()
        with _patch_load(empty_voices_data):
            result = runner.invoke(sayas_command, [])
        assert result.exit_code == 1
        assert "Speak as someone" in result.output


class TestSayasList:
    """Test the --list / -l flag."""

    def test_list_voices(self, voices_data):
        runner = CliRunner()
        with _patch_load(voices_data):
            result = runner.invoke(sayas_command, ["-l"])
        assert result.exit_code == 0
        assert "Available voices:" in result.output
        assert "alice" in result.output
        assert "Test voice Alice" in result.output
        assert "bob" in result.output

    def test_list_long_flag(self, voices_data):
        runner = CliRunner()
        with _patch_load(voices_data):
            result = runner.invoke(sayas_command, ["--list"])
        assert result.exit_code == 0
        assert "alice" in result.output

    def test_list_no_voices(self, empty_voices_data):
        runner = CliRunner()
        with _patch_load(empty_voices_data):
            result = runner.invoke(sayas_command, ["-l"])
        assert result.exit_code == 0
        assert "No voice profiles found" in result.output


class TestSayasCompletion:
    """Test the --completion flag."""

    def test_completion_outputs_bash_script(self):
        runner = CliRunner()
        result = runner.invoke(sayas_command, ["--completion"])
        assert result.exit_code == 0
        assert "_sayas_completion" in result.output
        assert "complete" in result.output
        assert "COMPREPLY" in result.output


class TestSayasVoiceLookup:
    """Test voice name lookup and error handling."""

    def test_unknown_voice(self, voices_data):
        runner = CliRunner()
        with _patch_load(voices_data):
            result = runner.invoke(sayas_command, ["unknown", "hello"])
        assert result.exit_code == 1
        assert "Unknown voice: unknown" in result.output

    def test_unknown_voice_shows_available(self, voices_data):
        runner = CliRunner()
        with _patch_load(voices_data):
            result = runner.invoke(sayas_command, ["unknown", "hello"])
        assert result.exit_code == 1
        assert "alice" in result.output
        assert "bob" in result.output

    def test_voice_no_text(self, voices_data):
        runner = CliRunner()
        with _patch_load(voices_data):
            result = runner.invoke(sayas_command, ["alice"])
        assert result.exit_code == 1
        assert "No text provided" in result.output


class TestSayasGeneration:
    """Test TTS generation (with mocked HTTP)."""

    def test_generate_and_play(self, voices_data):
        """Test that sayas sends correct payload and plays audio."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake-audio-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen, \
             patch("voice_mode.cli._play_audio") as mock_play:
            result = runner.invoke(sayas_command, ["alice", "Hello world"])

        assert result.exit_code == 0
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "test-model"
        assert payload["input"] == "Hello world"
        assert payload["ref_audio"] == "/tmp/voices/alice.wav"
        assert payload["ref_text"] == "Hello, I am Alice."
        assert "localhost:8890" in request.full_url
        assert request.full_url.endswith("/audio/speech")
        mock_play.assert_called_once()

    def test_generate_save_to_file(self, voices_data, tmp_path):
        """Test saving output to a file instead of playing."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake-audio-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        outfile = str(tmp_path / "output.mp3")
        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("urllib.request.urlopen", return_value=mock_response):
            result = runner.invoke(sayas_command, ["alice", "Hello", "-o", outfile])

        assert result.exit_code == 0
        assert f"Saved to {outfile}" in result.output
        assert Path(outfile).read_bytes() == b"fake-audio-data"

    def test_generate_multi_word_text(self, voices_data):
        """Test that multiple text arguments are joined."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake-audio-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen, \
             patch("voice_mode.cli._play_audio"):
            result = runner.invoke(sayas_command, ["alice", "Hello", "world", "today"])

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["input"] == "Hello world today"

    def test_default_base_url_used(self, voices_data):
        """Test that bob (no base_url in profile) uses the default."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake-audio-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen, \
             patch("voice_mode.cli._play_audio"):
            result = runner.invoke(sayas_command, ["bob", "Hello"])

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert "ms2:8890" in request.full_url

    def test_connection_error(self, voices_data):
        """Test error handling when TTS service is unreachable."""
        import urllib.error
        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            result = runner.invoke(sayas_command, ["alice", "Hello"])

        assert result.exit_code == 1
        assert "Failed to reach clone TTS service" in result.output


class TestSayasPreview:
    """Test the -p / --preview flag."""

    def test_preview_shows_info(self, voices_data):
        """Test that preview shows voice info and plays ref audio."""
        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("voice_mode.cli.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("voice_mode.cli._play_audio"):
            result = runner.invoke(sayas_command, ["alice", "-p"])

        assert result.exit_code == 0
        assert "Preview: alice" in result.output
        assert "Test voice Alice" in result.output
        assert "Ref text: Hello, I am Alice." in result.output

    def test_preview_extracts_host(self, voices_data):
        """Test that preview extracts host from base_url for scp."""
        runner = CliRunner()
        with _patch_load(voices_data), \
             patch("voice_mode.cli.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run, \
             patch("voice_mode.cli._play_audio"):
            result = runner.invoke(sayas_command, ["alice", "-p"])

        scp_call = mock_run.call_args
        scp_args = scp_call[0][0]
        assert scp_args[0] == "scp"
        # alice has base_url=http://localhost:8890/v1, so host=localhost
        assert "localhost:" in scp_args[2]


class TestSayasEntryPoint:
    """Test the entry point wrapper."""

    def test_sayas_cli_callable(self):
        """Verify that sayas_cli is importable and callable."""
        from voice_mode.cli import sayas_cli
        assert callable(sayas_cli)

    def test_sayas_command_is_click_command(self):
        """Verify sayas_command is a Click command."""
        import click
        assert isinstance(sayas_command, click.Command)


class TestPlayAudio:
    """Test the _play_audio helper."""

    @patch("voice_mode.cli.shutil.which")
    @patch("voice_mode.cli.subprocess.run")
    def test_play_with_afplay(self, mock_run, mock_which):
        """Test that afplay is preferred on macOS."""
        mock_which.side_effect = lambda x: "/usr/bin/afplay" if x == "afplay" else None

        from voice_mode.cli import _play_audio
        _play_audio("/tmp/test.mp3")

        mock_run.assert_called_once_with(["afplay", "/tmp/test.mp3"], check=False)

    @patch("voice_mode.cli.shutil.which")
    @patch("voice_mode.cli.subprocess.run")
    def test_play_with_mpv(self, mock_run, mock_which):
        """Test fallback to mpv when afplay is not available."""
        mock_which.side_effect = lambda x: "/usr/bin/mpv" if x == "mpv" else None

        from voice_mode.cli import _play_audio
        _play_audio("/tmp/test.mp3")

        mock_run.assert_called_once_with(
            ["mpv", "--no-video", "--really-quiet", "/tmp/test.mp3"], check=False
        )

    @patch("voice_mode.cli.shutil.which", return_value=None)
    def test_play_no_player(self, mock_which):
        """Test message when no player is available."""
        from voice_mode.cli import _play_audio
        _play_audio("/tmp/test.mp3")


class TestCompletionFile:
    """Test the bundled completion file."""

    def test_completion_file_exists(self):
        """Verify the completion script is bundled."""
        from importlib.resources import files
        resource = files("voice_mode.data.completions").joinpath("sayas.bash")
        content = resource.read_text()
        assert "_sayas_completion" in content
        assert "complete" in content

    def test_get_completion_path(self):
        """Test the helper function to get completion path."""
        from voice_mode.data.completions import get_completion_path
        path = get_completion_path("sayas.bash")
        assert path.endswith("sayas.bash")
        assert os.path.exists(path)
