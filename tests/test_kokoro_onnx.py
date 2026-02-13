"""Tests for the kokoro-onnx TTS service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np


class TestKokoroOnnxConfig:
    """Test kokoro-onnx configuration."""

    def test_kokoro_onnx_port_in_config(self):
        """Test that KOKORO_ONNX_PORT is defined in config."""
        from voice_mode.config import KOKORO_ONNX_PORT
        assert KOKORO_ONNX_PORT == 8881

    def test_kokoro_onnx_model_in_config(self):
        """Test that KOKORO_ONNX_MODEL is defined in config."""
        from voice_mode.config import KOKORO_ONNX_MODEL
        assert KOKORO_ONNX_MODEL == "kokoro-v1.0.int8.onnx"

    def test_kokoro_onnx_voices_in_config(self):
        """Test that KOKORO_ONNX_VOICES is defined in config."""
        from voice_mode.config import KOKORO_ONNX_VOICES
        assert KOKORO_ONNX_VOICES == "voices-v1.0.bin"


class TestKokoroOnnxService:
    """Test kokoro-onnx service management."""

    def test_kokoro_onnx_in_valid_services(self):
        """Test that kokoro-onnx is in VALID_SERVICES."""
        from voice_mode.cli import VALID_SERVICES
        assert "kokoro-onnx" in VALID_SERVICES

    def test_service_config_vars(self):
        """Test that get_service_config_vars works for kokoro-onnx."""
        from voice_mode.tools.service import get_service_config_vars
        config = get_service_config_vars("kokoro-onnx")
        assert "HOME" in config
        assert "START_SCRIPT" in config
        assert "KOKORO_ONNX_DIR" in config


class TestKokoroOnnxServer:
    """Test kokoro-onnx server module."""

    def test_server_module_imports(self):
        """Test that server module can be imported."""
        from voice_mode.services.kokoro_onnx import server
        assert hasattr(server, "app")
        assert hasattr(server, "SpeechRequest")

    def test_speech_request_model(self):
        """Test SpeechRequest pydantic model."""
        from voice_mode.services.kokoro_onnx.server import SpeechRequest

        # Test defaults
        req = SpeechRequest(input="Hello")
        assert req.model == "kokoro"
        assert req.voice == "af_heart"
        assert req.response_format == "pcm"
        assert req.speed == 1.0

        # Test custom values
        req = SpeechRequest(
            input="Test",
            voice="am_adam",
            response_format="wav",
            speed=1.5
        )
        assert req.voice == "am_adam"
        assert req.response_format == "wav"
        assert req.speed == 1.5

    def test_get_models_dir(self):
        """Test get_models_dir returns a Path."""
        from voice_mode.services.kokoro_onnx.server import get_models_dir
        from pathlib import Path

        models_dir = get_models_dir()
        assert isinstance(models_dir, Path)

    def test_get_model_path(self):
        """Test get_model_path returns correct path."""
        from voice_mode.services.kokoro_onnx.server import get_model_path
        from pathlib import Path

        model_path = get_model_path()
        assert isinstance(model_path, Path)
        assert model_path.name == "kokoro-v1.0.int8.onnx"

    def test_get_voices_path(self):
        """Test get_voices_path returns correct path."""
        from voice_mode.services.kokoro_onnx.server import get_voices_path
        from pathlib import Path

        voices_path = get_voices_path()
        assert isinstance(voices_path, Path)
        assert voices_path.name == "voices-v1.0.bin"

    def test_health_endpoint(self):
        """Test health endpoint returns correct response."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "kokoro-onnx"

    def test_voices_endpoint(self):
        """Test voices endpoint returns voice list."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        client = TestClient(app)
        response = client.get("/v1/voices")
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert "af_heart" in data["voices"]

    def test_speech_endpoint_no_model(self):
        """Test speech endpoint returns error when model not found."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        client = TestClient(app)
        response = client.post(
            "/v1/audio/speech",
            json={"input": "Hello"}
        )
        # Should return 503 when model not found
        assert response.status_code == 503

    def test_speech_endpoint_empty_input(self):
        """Test speech endpoint returns error for empty input."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        # Mock kokoro to avoid model loading
        with patch("voice_mode.services.kokoro_onnx.server.get_kokoro") as mock_get:
            mock_kokoro = MagicMock()
            mock_get.return_value = mock_kokoro

            client = TestClient(app)
            response = client.post(
                "/v1/audio/speech",
                json={"input": "   "}  # whitespace only
            )
            assert response.status_code == 400

    @patch("voice_mode.services.kokoro_onnx.server.get_kokoro")
    def test_speech_endpoint_success(self, mock_get_kokoro):
        """Test speech endpoint returns audio data."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        # Mock kokoro
        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (np.zeros(1000, dtype=np.float32), 24000)
        mock_get_kokoro.return_value = mock_kokoro

        client = TestClient(app)
        response = client.post(
            "/v1/audio/speech",
            json={"input": "Hello world", "voice": "af_heart"}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/pcm"
        assert len(response.content) > 0

    @patch("voice_mode.services.kokoro_onnx.server.get_kokoro")
    def test_speech_endpoint_wav_format(self, mock_get_kokoro):
        """Test speech endpoint returns WAV audio."""
        from fastapi.testclient import TestClient
        from voice_mode.services.kokoro_onnx.server import app

        # Mock kokoro
        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (np.zeros(1000, dtype=np.float32), 24000)
        mock_get_kokoro.return_value = mock_kokoro

        client = TestClient(app)
        response = client.post(
            "/v1/audio/speech",
            json={"input": "Hello", "response_format": "wav"}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        # WAV files start with RIFF header
        assert response.content[:4] == b"RIFF"


class TestKokoroOnnxStartScript:
    """Test kokoro-onnx start script template."""

    def test_start_script_exists(self):
        """Test that start script template exists."""
        from pathlib import Path
        template_path = (
            Path(__file__).parent.parent
            / "voice_mode"
            / "templates"
            / "scripts"
            / "start-kokoro-onnx.sh"
        )
        assert template_path.exists()

    def test_start_script_executable_header(self):
        """Test start script has bash header."""
        from pathlib import Path
        template_path = (
            Path(__file__).parent.parent
            / "voice_mode"
            / "templates"
            / "scripts"
            / "start-kokoro-onnx.sh"
        )
        content = template_path.read_text()
        assert content.startswith("#!/bin/bash")
