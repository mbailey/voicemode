"""Tests for clone voice profile CRUD (add, list, remove)."""

import json
import urllib.error
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from voice_mode.tools.clone.profiles import (
    VOICES_DIR,
    VOICES_JSON,
    _load_voices_json,
    _save_voices_json,
    _transcribe_audio,
    clone_add,
    clone_list,
    clone_remove,
)


@pytest.fixture
def tmp_voicemode(tmp_path, monkeypatch):
    """Set up a temporary ~/.voicemode directory for testing."""
    voices_json = tmp_path / "voices.json"
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()

    monkeypatch.setattr(
        "voice_mode.tools.clone.profiles.VOICES_JSON", voices_json
    )
    monkeypatch.setattr(
        "voice_mode.tools.clone.profiles.VOICES_DIR", voices_dir
    )

    return {
        "base": tmp_path,
        "voices_json": voices_json,
        "voices_dir": voices_dir,
    }


@pytest.fixture
def sample_audio(tmp_path):
    """Create a minimal valid WAV file for testing."""
    audio_path = tmp_path / "test-clip.wav"
    with wave.open(str(audio_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1 second of silence
    return audio_path


@pytest.fixture
def populated_voices(tmp_voicemode):
    """Pre-populate voices.json with test data."""
    data = {
        "voices": {
            "alice": {
                "ref_audio": str(tmp_voicemode["voices_dir"] / "alice.wav"),
                "ref_text": "Hello, I am Alice.",
                "description": "Test voice Alice",
            },
            "bob": {
                "ref_audio": str(tmp_voicemode["voices_dir"] / "bob.wav"),
                "ref_text": "Hello, I am Bob.",
                "description": "Test voice Bob",
            },
        }
    }
    tmp_voicemode["voices_json"].write_text(json.dumps(data, indent=2))

    # Create dummy audio files
    for name in ["alice", "bob"]:
        audio = tmp_voicemode["voices_dir"] / f"{name}.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 100)

    return data


class TestLoadVoicesJson:
    """Test _load_voices_json helper."""

    def test_missing_file_returns_empty(self, tmp_voicemode):
        result = _load_voices_json()
        assert result == {"voices": {}}

    def test_loads_valid_json(self, tmp_voicemode, populated_voices):
        result = _load_voices_json()
        assert "alice" in result["voices"]
        assert "bob" in result["voices"]
        assert len(result["voices"]) == 2

    def test_invalid_json_returns_empty(self, tmp_voicemode):
        tmp_voicemode["voices_json"].write_text("not valid json{{{")
        result = _load_voices_json()
        assert result == {"voices": {}}

    def test_missing_voices_key(self, tmp_voicemode):
        tmp_voicemode["voices_json"].write_text(json.dumps({"other": "data"}))
        result = _load_voices_json()
        assert result == {"other": "data", "voices": {}}


class TestSaveVoicesJson:
    """Test _save_voices_json helper."""

    def test_saves_valid_json(self, tmp_voicemode):
        data = {"voices": {"test": {"ref_audio": "/tmp/test.wav", "ref_text": "hi"}}}
        _save_voices_json(data)
        loaded = json.loads(tmp_voicemode["voices_json"].read_text())
        assert loaded["voices"]["test"]["ref_text"] == "hi"

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "deep" / "nested" / "voices.json"
        monkeypatch.setattr("voice_mode.tools.clone.profiles.VOICES_JSON", nested)
        _save_voices_json({"voices": {}})
        assert nested.exists()

    def test_file_ends_with_newline(self, tmp_voicemode):
        _save_voices_json({"voices": {}})
        content = tmp_voicemode["voices_json"].read_text()
        assert content.endswith("\n")


class TestCloneAdd:
    """Test clone_add -- adding a new voice profile."""

    @pytest.mark.asyncio
    async def test_add_with_explicit_ref_text(self, tmp_voicemode, sample_audio):
        result = await clone_add(
            name="testvoice",
            audio_file=str(sample_audio),
            description="A test voice",
            ref_text="This is the transcript.",
        )
        assert result["success"] is True
        assert result["name"] == "testvoice"
        assert result["ref_text"] == "This is the transcript."
        assert result["description"] == "A test voice"

        # Verify audio was copied
        dest = tmp_voicemode["voices_dir"] / "testvoice.wav"
        assert dest.exists()

        # Verify voices.json was updated
        data = json.loads(tmp_voicemode["voices_json"].read_text())
        assert "testvoice" in data["voices"]
        assert data["voices"]["testvoice"]["ref_text"] == "This is the transcript."

    @pytest.mark.asyncio
    async def test_add_with_auto_transcribe(self, tmp_voicemode, sample_audio):
        mock_text = "Auto transcribed text from Whisper."
        with patch(
            "voice_mode.tools.clone.profiles._transcribe_audio",
            return_value=mock_text,
        ):
            result = await clone_add(
                name="autovoice",
                audio_file=str(sample_audio),
                description="Auto-transcribed voice",
            )
        assert result["success"] is True
        assert result["ref_text"] == mock_text

    @pytest.mark.asyncio
    async def test_add_duplicate_rejected(self, tmp_voicemode, populated_voices, sample_audio):
        result = await clone_add(
            name="alice",
            audio_file=str(sample_audio),
            ref_text="duplicate",
        )
        assert result["success"] is False
        assert "already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_add_missing_audio_file(self, tmp_voicemode):
        result = await clone_add(
            name="ghost",
            audio_file="/nonexistent/audio.wav",
            ref_text="hello",
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_add_empty_name_rejected(self, tmp_voicemode, sample_audio):
        result = await clone_add(
            name="",
            audio_file=str(sample_audio),
            ref_text="hello",
        )
        assert result["success"] is False
        assert "empty" in result["error"]

    @pytest.mark.asyncio
    async def test_add_normalizes_name_to_lowercase(self, tmp_voicemode, sample_audio):
        result = await clone_add(
            name="MyVoice",
            audio_file=str(sample_audio),
            ref_text="hello",
        )
        assert result["success"] is True
        assert result["name"] == "myvoice"

    @pytest.mark.asyncio
    async def test_add_whisper_connection_error_cleans_up(self, tmp_voicemode, sample_audio):
        with patch(
            "voice_mode.tools.clone.profiles._transcribe_audio",
            side_effect=ConnectionError("Cannot reach Whisper"),
        ):
            result = await clone_add(
                name="failvoice",
                audio_file=str(sample_audio),
            )
        assert result["success"] is False
        assert "Whisper" in result["error"]

        # Audio file should have been cleaned up
        dest = tmp_voicemode["voices_dir"] / "failvoice.wav"
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_add_with_model_and_base_url(self, tmp_voicemode, sample_audio):
        result = await clone_add(
            name="custom",
            audio_file=str(sample_audio),
            ref_text="test",
            model="custom-model",
            base_url="http://localhost:9999/v1",
        )
        assert result["success"] is True
        data = json.loads(tmp_voicemode["voices_json"].read_text())
        assert data["voices"]["custom"]["model"] == "custom-model"
        assert data["voices"]["custom"]["base_url"] == "http://localhost:9999/v1"

    @pytest.mark.asyncio
    async def test_add_without_optional_model_fields(self, tmp_voicemode, sample_audio):
        result = await clone_add(
            name="minimal",
            audio_file=str(sample_audio),
            ref_text="test",
        )
        assert result["success"] is True
        data = json.loads(tmp_voicemode["voices_json"].read_text())
        # model and base_url should not be present when not explicitly set
        assert "model" not in data["voices"]["minimal"]
        assert "base_url" not in data["voices"]["minimal"]


class TestCloneList:
    """Test clone_list -- listing voice profiles."""

    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_voicemode):
        result = await clone_list()
        assert result["success"] is True
        assert result["count"] == 0
        assert result["voices"] == []

    @pytest.mark.asyncio
    async def test_list_populated(self, tmp_voicemode, populated_voices):
        result = await clone_list()
        assert result["success"] is True
        assert result["count"] == 2
        names = [v["name"] for v in result["voices"]]
        assert "alice" in names
        assert "bob" in names

    @pytest.mark.asyncio
    async def test_list_sorted_alphabetically(self, tmp_voicemode, populated_voices):
        result = await clone_list()
        names = [v["name"] for v in result["voices"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_includes_description(self, tmp_voicemode, populated_voices):
        result = await clone_list()
        alice = next(v for v in result["voices"] if v["name"] == "alice")
        assert alice["description"] == "Test voice Alice"

    @pytest.mark.asyncio
    async def test_list_missing_file(self, tmp_voicemode):
        # voices.json does not exist -- should return empty list, not error
        result = await clone_list()
        assert result["success"] is True
        assert result["count"] == 0


class TestCloneRemove:
    """Test clone_remove -- removing voice profiles."""

    @pytest.mark.asyncio
    async def test_remove_existing_profile(self, tmp_voicemode, populated_voices):
        result = await clone_remove("alice")
        assert result["success"] is True
        assert result["name"] == "alice"

        # Verify removed from voices.json
        data = json.loads(tmp_voicemode["voices_json"].read_text())
        assert "alice" not in data["voices"]
        assert "bob" in data["voices"]  # Other profiles untouched

    @pytest.mark.asyncio
    async def test_remove_deletes_audio_file(self, tmp_voicemode, populated_voices):
        audio_path = tmp_voicemode["voices_dir"] / "alice.wav"
        assert audio_path.exists()

        result = await clone_remove("alice", remove_audio=True)
        assert result["success"] is True
        assert result["audio_removed"] is True
        assert not audio_path.exists()

    @pytest.mark.asyncio
    async def test_remove_keeps_audio_when_requested(self, tmp_voicemode, populated_voices):
        audio_path = tmp_voicemode["voices_dir"] / "alice.wav"
        assert audio_path.exists()

        result = await clone_remove("alice", remove_audio=False)
        assert result["success"] is True
        assert result["audio_removed"] is False
        assert audio_path.exists()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_profile(self, tmp_voicemode, populated_voices):
        result = await clone_remove("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_empty_name_rejected(self, tmp_voicemode):
        result = await clone_remove("")
        assert result["success"] is False
        assert "empty" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_normalizes_name(self, tmp_voicemode, populated_voices):
        result = await clone_remove("  Alice  ")
        assert result["success"] is True
        assert result["name"] == "alice"

    @pytest.mark.asyncio
    async def test_remove_audio_string_param(self, tmp_voicemode, populated_voices):
        """Test that remove_audio accepts string 'false'."""
        audio_path = tmp_voicemode["voices_dir"] / "bob.wav"
        result = await clone_remove("bob", remove_audio="false")
        assert result["success"] is True
        assert result["audio_removed"] is False
        assert audio_path.exists()

    @pytest.mark.asyncio
    async def test_remove_missing_audio_file_succeeds(self, tmp_voicemode):
        """Removing a profile whose audio file is already gone should succeed."""
        data = {
            "voices": {
                "ghost": {
                    "ref_audio": "/nonexistent/ghost.wav",
                    "ref_text": "boo",
                    "description": "Ghost voice",
                }
            }
        }
        tmp_voicemode["voices_json"].write_text(json.dumps(data))

        result = await clone_remove("ghost", remove_audio=True)
        assert result["success"] is True
        assert result["audio_removed"] is False


class TestTranscribeAudio:
    """Test _transcribe_audio -- Whisper STT integration."""

    def test_transcribe_connection_error(self, sample_audio):
        """Verify ConnectionError when Whisper is unreachable."""
        with patch(
            "voice_mode.tools.clone.profiles.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(ConnectionError, match="Whisper"):
                _transcribe_audio(sample_audio)

    def test_transcribe_successful(self, sample_audio):
        """Test successful transcription via mocked urllib."""
        response_body = json.dumps({"text": "Hello world"}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("voice_mode.tools.clone.profiles.urllib.request.urlopen", return_value=mock_response):
            result = _transcribe_audio(sample_audio)
        assert result == "Hello world"

    def test_transcribe_empty_result_raises(self, sample_audio):
        """Test that empty transcription raises RuntimeError."""
        response_body = json.dumps({"text": ""}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("voice_mode.tools.clone.profiles.urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(RuntimeError, match="empty"):
                _transcribe_audio(sample_audio)
