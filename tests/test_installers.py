"""
Tests for whisper.cpp and kokoro-fastapi installation tools
"""
import os
import sys
import tempfile
import shutil
import json
import platform
import subprocess
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the actual async functions from the new locations
import voice_mode.tools.services.whisper.install as whisper_install
import voice_mode.tools.services.kokoro.install as kokoro_install

# Get the actual async functions from the MCP tool decorators
install_whisper_cpp = whisper_install.whisper_install.fn
install_kokoro_fastapi = kokoro_install.kokoro_install.fn


def mock_exists_for_whisper(path):
    """Helper to mock os.path.exists for whisper.cpp tests"""
    if "ggml-" in path and path.endswith(".bin"):
        return True  # Model file exists
    if path.endswith("jfk.wav"):
        return True  # Sample file exists
    if path.endswith("main") and "/whisper.cpp/" in path:
        return True  # Check for already installed
    return False  # Install dir doesn't exist


class TestWhisperCppInstaller:
    """Test cases for whisper.cpp installation tool"""
    
    @pytest.mark.asyncio
    async def test_default_installation_path(self):
        """Test that default installation path is set correctly"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_for_whisper), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_whisper_cpp()
            
            assert result["install_path"] == os.path.expanduser("~/.voicemode/whisper.cpp")
    
    @pytest.mark.asyncio
    async def test_custom_installation_path(self):
        """Test installation with custom path"""
        custom_path = "/tmp/my-whisper"
        
        def mock_exists(path):
            # Model file and sample file should exist
            if "ggml-" in path and path.endswith(".bin"):
                return True
            if path.endswith("jfk.wav"):
                return True
            if path.endswith("download-ggml-model.sh"):
                return True
            return False
        
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('platform.system', return_value='Darwin'), \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('voice_mode.tools.services.whisper.install.download_whisper_model') as mock_download:
            
            mock_run.return_value = MagicMock(returncode=0)
            mock_download.return_value = {
                "success": True,
                "path": f"{custom_path}/models/ggml-large-v2.bin",
                "message": "Model already exists"
            }
            
            result = await install_whisper_cpp(install_dir=custom_path)
            
            assert result["success"] is True
            assert result["install_path"] == custom_path
    
    @pytest.mark.asyncio
    async def test_already_installed(self):
        """Test behavior when whisper.cpp is already installed"""
        def mock_exists(path):
            # First check is for install_dir
            if path.endswith("/.voicemode/whisper.cpp"):
                return True
            # Second check is for main executable
            if path.endswith("/main"):
                return True
            return False
            
        with patch('os.path.exists', side_effect=mock_exists):
            result = await install_whisper_cpp()
            
            assert result["success"] is True
            assert result["already_installed"] is True
            assert "already installed" in result["message"]
    
    @pytest.mark.asyncio
    async def test_force_reinstall(self):
        """Test force reinstall functionality"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=True), \
             patch('shutil.rmtree') as mock_rmtree, \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_whisper_cpp(force_reinstall=True)
            
            # Verify that existing installation was removed
            mock_rmtree.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_macos_gpu_detection(self):
        """Test GPU detection on macOS"""
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_for_whisper), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_whisper_cpp()
            
            assert result["success"] is True
            assert result["gpu_enabled"] is True
            assert result["gpu_type"] == "metal"
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex mocking issues with empty error - needs investigation")
    async def test_linux_cuda_detection(self):
        """Test CUDA detection on Linux"""
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_for_whisper), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
            # First call is nvidia-smi check (success)
            # Subsequent calls are for build and systemd
            mock_run.side_effect = [
                MagicMock(returncode=0),  # nvidia-smi
                MagicMock(returncode=0),  # git clone
                MagicMock(returncode=0),  # make clean
                MagicMock(returncode=0),  # make
                MagicMock(returncode=0),  # download model
                MagicMock(returncode=0),  # systemctl --user daemon-reload
                MagicMock(returncode=0),  # systemctl --user enable
                MagicMock(returncode=0),  # systemctl --user start
            ]
            
            result = await install_whisper_cpp()
            
            if not result["success"]:
                print(f"Failed on Linux CUDA: {result}")
            assert result["success"] is True
            assert result["gpu_enabled"] is True
            assert result["gpu_type"] == "cuda"
    
    @pytest.mark.asyncio
    async def test_missing_dependencies_macos(self):
        """Test missing dependencies detection on macOS"""
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['xcode-select'])), \
             patch('os.path.exists', return_value=False):
            
            result = await install_whisper_cpp()
            
            assert result["success"] is False
            assert "Missing dependencies" in result["error"]
            assert any("Xcode" in dep for dep in result["missing"])
    
    @pytest.mark.asyncio
    async def test_model_download(self):
        """Test different model downloads"""
        models = ["tiny", "base", "small", "medium", "large-v3"]
        
        for model in models:
            def mock_exists_model(path):
                # Model file should exist after download
                if f"ggml-{model}.bin" in path:
                    return True
                if path.endswith("jfk.wav"):
                    return True
                if path.endswith("download-ggml-model.sh"):
                    return True
                return False
                
            with patch('subprocess.run') as mock_run, \
                 patch('os.path.exists', side_effect=mock_exists_model), \
                 patch('shutil.which', return_value=True), \
                 patch('os.chdir'), \
                 patch('os.makedirs'), \
                 patch('platform.system', return_value='Darwin'), \
                 patch('builtins.open', create=True), \
                 patch('os.chmod'), \
                 patch('voice_mode.tools.services.whisper.install.download_whisper_model') as mock_download:
                
                mock_run.return_value = MagicMock(returncode=0)
                mock_download.return_value = {
                    "success": True,
                    "path": f"/Users/admin/.voicemode/whisper.cpp/models/ggml-{model}.bin",
                    "message": f"Model {model} downloaded successfully"
                }
                
                result = await install_whisper_cpp(model=model)
                
                if not result["success"]:
                    print(f"Failed for model {model}: {result}")
                assert result["success"] is True
                assert result["model_path"].endswith(f"ggml-{model}.bin")
    
    @pytest.mark.asyncio
    async def test_build_failure(self):
        """Test handling of build failures"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            # Make the make command fail
            mock_run.side_effect = [
                MagicMock(returncode=0),  # git clone
                MagicMock(returncode=0),  # make clean
                subprocess.CalledProcessError(1, ['make'], stderr=b"Build error")
            ]
            
            result = await install_whisper_cpp()
            
            assert result["success"] is False
            assert "Command failed" in result["error"]


class TestKokoroFastAPIInstaller:
    """Test cases for kokoro-fastapi installation tool"""
    
    @pytest.mark.asyncio
    async def test_default_installation_paths(self):
        """Test that default paths are set correctly"""
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu_mac.sh" in path or "start-cpu.sh" in path or "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('platform.system', return_value='Darwin'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            # Mock aiohttp session
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi()
            
            assert result["success"] is True
            assert result["install_path"] == os.path.expanduser("~/.voicemode/kokoro-fastapi")
            # Note: models_path is not returned by the installer anymore
    
    @pytest.mark.asyncio
    async def test_python_version_check(self):
        """Test Python version requirement"""
        with patch('sys.version_info', (3, 9)):
            result = await install_kokoro_fastapi()
            
            assert result["success"] is False
            assert "Python 3.10+ required" in result["error"]
    
    @pytest.mark.asyncio
    async def test_git_requirement(self):
        """Test git requirement check"""
        with patch('shutil.which', return_value=None):
            result = await install_kokoro_fastapi()
            
            assert result["success"] is False
            assert "Git is required" in result["error"]
    
    @pytest.mark.asyncio
    async def test_uv_installation(self):
        """Test UV package manager installation"""
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu_mac.sh" in path or "start-cpu.sh" in path or "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which') as mock_which, \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('platform.system', return_value='Darwin'):
            
            # Mock which calls: git (True), uv (False), then True for others
            def which_side_effect(cmd):
                if cmd == "git":
                    return True
                if cmd == "uv":
                    return None  # UV not found
                return True
            mock_which.side_effect = which_side_effect
            mock_run.return_value = MagicMock(returncode=0)
            
            # Mock aiohttp
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi()
            
            # Debug: print all run calls
            for call in mock_run.call_args_list:
                print(f"Run call: {call}")
            
            # Verify UV installation was attempted
            assert any("uv/install.sh" in str(call) for call in mock_run.call_args_list)
    
    @pytest.mark.asyncio
    async def test_model_download(self):
        """Test model file downloads"""
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu_mac.sh" in path or "start-cpu.sh" in path or "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('platform.system', return_value='Darwin'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            # Track downloaded files
            downloaded_files = []
            
            async def mock_get(url):
                downloaded_files.append(url)
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
                mock_response.raise_for_status = MagicMock()
                return mock_response
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get = mock_get
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi(install_models=True)
            
            # The new installer doesn't download models directly - it's handled by the start script
            # So we just verify the installation succeeded
            assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_skip_model_download(self):
        """Test skipping model download"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_kokoro_fastapi(install_models=False)
            
            # Verify aiohttp session was not created (no downloads)
            mock_session.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_service_auto_start(self):
        """Test automatic service startup with systemd on Linux"""
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu_mac.sh" in path or "start-cpu.sh" in path or "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('subprocess.Popen') as mock_popen, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('asyncio.sleep'), \
             patch('platform.system', return_value='Linux'):  # Linux to test auto_start
            
            mock_run.return_value = MagicMock(returncode=0)
            mock_popen.return_value = MagicMock(pid=12345)
            
            # Mock both model download and health check
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            # Create a proper async context manager for the get response
            async def mock_get(*args, **kwargs):
                cm = AsyncMock()
                cm.__aenter__.return_value = mock_response
                cm.__aexit__.return_value = None
                return cm
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get = mock_get
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi(auto_start=True)
            
            if not result["success"]:
                print(f"Failed auto start: {result}")
            assert result["success"] is True
            # On Linux, it should have systemd service info
            assert result["service_status"] == "managed_by_systemd"
            assert "systemd_service" in result
            assert result["systemd_service"].endswith("kokoro-fastapi-8880.service")
            assert result["systemd_enabled"] is True
    
    @pytest.mark.asyncio
    async def test_custom_port(self):
        """Test custom port configuration"""
        custom_port = 9999
        
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu_mac.sh" in path or "start-cpu.sh" in path or "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True) as mock_open, \
             patch('os.chmod'), \
             patch('platform.system', return_value='Darwin'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            # Mock aiohttp
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi(port=custom_port)
            
            assert result["success"] is True
            # Verify port in config
            assert result["service_url"] == f"http://127.0.0.1:{custom_port}"
    
    @pytest.mark.asyncio
    async def test_systemd_service_creation(self):
        """Test systemd service creation on Linux"""
        def mock_exists_kokoro(path):
            # Start script should exist
            if "start-gpu.sh" in path:
                return True
            if path.endswith("/main.py"):
                return False  # Not installed yet
            return False
            
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', side_effect=mock_exists_kokoro), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True) as mock_open, \
             patch('os.chmod'), \
             patch('platform.system', return_value='Linux'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            # Mock aiohttp
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi()
            
            assert result["success"] is True
            assert "systemd_service" in result
            assert result["systemd_enabled"] is True
            
            # Check that systemctl commands were called
            systemctl_calls = [call for call in mock_run.call_args_list if "systemctl" in str(call)]
            assert len(systemctl_calls) >= 3  # daemon-reload, enable, start
    
    @pytest.mark.asyncio
    async def test_force_reinstall(self):
        """Test force reinstall for kokoro-fastapi"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=True), \
             patch('shutil.rmtree') as mock_rmtree, \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            # Mock aiohttp
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi(force_reinstall=True)
            
            # Verify existing installation was removed
            mock_rmtree.assert_called_once()


# Integration test fixtures
@pytest.fixture
def temp_install_dir():
    """Create a temporary directory for installation tests"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_INTEGRATION_TESTS") != "1",
                    reason="Integration tests disabled by default. Set RUN_INTEGRATION_TESTS=1 to enable.")
class TestIntegration:
    """Integration tests (run with actual installations)"""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(os.environ.get("SKIP_INTEGRATION_TESTS") == "1", 
                        reason="Skipping integration tests")
    async def test_whisper_cpp_real_installation(self, temp_install_dir):
        """Test actual whisper.cpp installation (requires internet)"""
        result = await install_whisper_cpp(
            install_dir=temp_install_dir,
            model="tiny"  # Use smallest model for testing
        )
        
        assert result["success"] is True
        assert os.path.exists(result["install_path"])
        assert os.path.exists(result["model_path"])
        assert os.path.exists(os.path.join(result["install_path"], "main"))
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(os.environ.get("SKIP_INTEGRATION_TESTS") == "1", 
                        reason="Skipping integration tests")
    async def test_kokoro_fastapi_real_installation(self, temp_install_dir):
        """Test actual kokoro-fastapi installation (requires internet)"""
        models_dir = os.path.join(temp_install_dir, "models")
        
        result = await install_kokoro_fastapi(
            install_dir=os.path.join(temp_install_dir, "kokoro-fastapi"),
            models_dir=models_dir,
            auto_start=False,  # Don't start service in tests
            install_models=False  # Skip large model downloads in tests
        )
        
        assert result["success"] is True
        assert os.path.exists(result["install_path"])
        assert os.path.exists(os.path.join(result["install_path"], "main.py"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])