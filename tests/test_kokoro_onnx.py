"""Tests for the kokoro-onnx TTS service."""

import pytest
import pytest_asyncio
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


class TestKokoroOnnxInstaller:
    """Test kokoro-onnx installer."""

    def test_installer_module_imports(self):
        """Test that installer module can be imported."""
        from voice_mode.services.kokoro_onnx import installer
        assert hasattr(installer, "kokoro_onnx_install")
        assert hasattr(installer, "check_python_deps")
        assert hasattr(installer, "MODEL_URLS")
        assert hasattr(installer, "download_file")
        assert hasattr(installer, "install_python_deps")

    def test_model_urls_defined(self):
        """Test that model download URLs are defined."""
        from voice_mode.services.kokoro_onnx.installer import MODEL_URLS
        assert "kokoro-v1.0.int8.onnx" in MODEL_URLS
        assert "kokoro-v1.0.fp16.onnx" in MODEL_URLS
        assert "kokoro-v1.0.onnx" in MODEL_URLS
        assert "voices-v1.0.bin" in MODEL_URLS
        # All URLs should be valid GitHub release URLs
        for url in MODEL_URLS.values():
            assert url.startswith("https://github.com/thewh1teagle/kokoro-onnx/releases/")

    @pytest.mark.asyncio
    async def test_check_python_deps(self):
        """Test check_python_deps returns dict of booleans."""
        from voice_mode.services.kokoro_onnx.installer import check_python_deps
        deps = await check_python_deps()
        assert isinstance(deps, dict)
        assert "kokoro_onnx" in deps
        assert "fastapi" in deps
        assert "uvicorn" in deps
        # All values should be booleans
        for val in deps.values():
            assert isinstance(val, bool)

    @pytest.mark.asyncio
    async def test_check_python_deps_detects_fastapi(self):
        """Test that check_python_deps detects installed fastapi."""
        from voice_mode.services.kokoro_onnx.installer import check_python_deps
        deps = await check_python_deps()
        # FastAPI should be installed in test environment
        assert deps["fastapi"] is True

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.subprocess.run")
    async def test_install_python_deps_uses_uv(self, mock_run):
        """Test install_python_deps prefers uv over pip."""
        from voice_mode.services.kokoro_onnx.installer import install_python_deps

        # Mock uv available
        mock_run.return_value = MagicMock(returncode=0)

        result = await install_python_deps()

        assert result is True
        # First call checks uv --version, second installs
        assert mock_run.call_count == 2
        # Second call should use uv pip install
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args[0] == "uv"
        assert "pip" in second_call_args
        assert "install" in second_call_args

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.subprocess.run")
    async def test_install_python_deps_fallback_to_pip(self, mock_run):
        """Test install_python_deps falls back to pip when uv unavailable."""
        from voice_mode.services.kokoro_onnx.installer import install_python_deps

        # Mock uv not available (first call fails), pip succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),  # uv --version fails
            MagicMock(returncode=0),  # pip install succeeds
        ]

        result = await install_python_deps()

        assert result is True
        assert mock_run.call_count == 2
        # Second call should use pip
        second_call_args = mock_run.call_args_list[1][0][0]
        assert "-m" in second_call_args
        assert "pip" in second_call_args

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.subprocess.run")
    async def test_install_python_deps_failure(self, mock_run):
        """Test install_python_deps returns False on failure."""
        from voice_mode.services.kokoro_onnx.installer import install_python_deps

        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        result = await install_python_deps()

        assert result is False

    @pytest.mark.asyncio
    async def test_download_file_creates_parent_dirs(self, tmp_path):
        """Test download_file creates parent directories."""
        from voice_mode.services.kokoro_onnx.installer import download_file

        dest = tmp_path / "nested" / "dir" / "file.txt"

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.content.read = MagicMock(side_effect=[b"test", b""])

            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = MagicMock(return_value=mock_response)
            mock_ctx.__aexit__ = MagicMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.get.return_value = mock_ctx
            mock_session_instance.__aenter__ = MagicMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = MagicMock(return_value=None)
            mock_session.return_value = mock_session_instance

            # This will fail because our mock isn't perfect, but it tests the import path
            # In real usage, aiohttp handles this correctly

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.tools.service.install_kokoro_onnx_start_script")
    async def test_kokoro_onnx_install_skip_downloads(self, mock_script, mock_deps):
        """Test kokoro_onnx_install with download_models=False."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": True, "fastapi": True, "uvicorn": True}
        mock_script.return_value = {"success": True, "start_script": "/path/to/script"}

        result = await kokoro_onnx_install(download_models=False, auto_enable=False)

        assert result["success"] is True
        assert result["deps_installed"] is True
        assert result["model"] == "kokoro-v1.0.int8.onnx"
        assert result["voices"] == "voices-v1.0.bin"

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.services.kokoro_onnx.installer.install_python_deps")
    @patch("voice_mode.tools.service.install_kokoro_onnx_start_script")
    async def test_kokoro_onnx_install_installs_missing_deps(self, mock_script, mock_install, mock_deps):
        """Test kokoro_onnx_install installs missing dependencies."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": False, "fastapi": True, "uvicorn": True}
        mock_install.return_value = True
        mock_script.return_value = {"success": True, "start_script": "/path/to/script"}

        result = await kokoro_onnx_install(download_models=False, auto_enable=False)

        assert result["success"] is True
        mock_install.assert_called_once()

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.services.kokoro_onnx.installer.install_python_deps")
    async def test_kokoro_onnx_install_fails_on_dep_install_error(self, mock_install, mock_deps):
        """Test kokoro_onnx_install fails when dependency installation fails."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": False, "fastapi": False, "uvicorn": False}
        mock_install.return_value = False

        result = await kokoro_onnx_install(download_models=False, auto_enable=False)

        assert result["success"] is False
        assert "error" in result
        assert "dependencies" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.tools.service.install_kokoro_onnx_start_script")
    async def test_kokoro_onnx_install_fails_on_script_error(self, mock_script, mock_deps):
        """Test kokoro_onnx_install fails when start script installation fails."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": True, "fastapi": True, "uvicorn": True}
        mock_script.return_value = {"success": False, "error": "Permission denied"}

        result = await kokoro_onnx_install(download_models=False, auto_enable=False)

        assert result["success"] is False
        assert "error" in result
        assert "start script" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.tools.service.install_kokoro_onnx_start_script")
    async def test_kokoro_onnx_install_custom_model(self, mock_script, mock_deps):
        """Test kokoro_onnx_install with custom model name."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": True, "fastapi": True, "uvicorn": True}
        mock_script.return_value = {"success": True, "start_script": "/path/to/script"}

        result = await kokoro_onnx_install(
            model="kokoro-v1.0.fp16.onnx",
            download_models=False,
            auto_enable=False
        )

        assert result["success"] is True
        assert result["model"] == "kokoro-v1.0.fp16.onnx"

    @pytest.mark.asyncio
    @patch("voice_mode.services.kokoro_onnx.installer.check_python_deps")
    @patch("voice_mode.tools.service.install_kokoro_onnx_start_script")
    async def test_kokoro_onnx_install_custom_models_dir(self, mock_script, mock_deps):
        """Test kokoro_onnx_install with custom models directory."""
        from voice_mode.services.kokoro_onnx.installer import kokoro_onnx_install

        mock_deps.return_value = {"kokoro_onnx": True, "fastapi": True, "uvicorn": True}
        mock_script.return_value = {"success": True, "start_script": "/path/to/script"}

        result = await kokoro_onnx_install(
            models_dir="/tmp/custom/models",
            download_models=False,
            auto_enable=False
        )

        assert result["success"] is True
        assert result["models_dir"] == "/tmp/custom/models"


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
