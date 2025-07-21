"""
Tests for whisper.cpp and kokoro-fastapi installation tools
"""
import os
import sys
import tempfile
import shutil
import json
import platform
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the actual async functions from the module
import voice_mode.tools.installers as installers

# Get the actual async functions from the MCP tool decorators
install_whisper_cpp = installers.install_whisper_cpp.fn
install_kokoro_fastapi = installers.install_kokoro_fastapi.fn


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
            
            assert result["install_path"] == os.path.expanduser("~/whisper.cpp")
    
    @pytest.mark.asyncio
    async def test_custom_installation_path(self):
        """Test installation with custom path"""
        custom_path = "/tmp/my-whisper"
        
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_whisper_cpp(install_dir=custom_path)
            
            assert result["install_path"] == custom_path
    
    @pytest.mark.asyncio
    async def test_already_installed(self):
        """Test behavior when whisper.cpp is already installed"""
        with patch('os.path.exists', side_effect=[True, True]):
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
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await install_whisper_cpp()
            
            assert result["gpu_enabled"] is True
            assert result["gpu_type"] == "metal"
    
    @pytest.mark.asyncio
    async def test_linux_cuda_detection(self):
        """Test CUDA detection on Linux"""
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'):
            
            # First call is nvidia-smi check (success)
            # Subsequent calls are for build
            mock_run.side_effect = [
                MagicMock(returncode=0),  # nvidia-smi
                MagicMock(returncode=0),  # git clone
                MagicMock(returncode=0),  # make clean
                MagicMock(returncode=0),  # make
                MagicMock(returncode=0),  # download model
            ]
            
            result = await install_whisper_cpp()
            
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
            with patch('subprocess.run') as mock_run, \
                 patch('os.path.exists', return_value=False), \
                 patch('shutil.which', return_value=True), \
                 patch('os.chdir'), \
                 patch('os.makedirs'):
                
                mock_run.return_value = MagicMock(returncode=0)
                
                result = await install_whisper_cpp(model=model)
                
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
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
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
            
            assert result["install_path"] == os.path.expanduser("~/kokoro-fastapi")
            assert result["models_path"] == os.path.expanduser("~/Models/kokoro")
    
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
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which') as mock_which, \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
            # First call returns None (UV not found), subsequent calls return True
            mock_which.side_effect = [None, True, True, True]
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
            
            # Verify UV installation was attempted
            assert any("uv/install.sh" in str(call) for call in mock_run.call_args_list)
    
    @pytest.mark.asyncio
    async def test_model_download(self):
        """Test model file downloads"""
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'):
            
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
            
            # Verify model files were downloaded
            assert any("kokoro-v0_19.onnx" in url for url in downloaded_files)
            assert any("voices.json" in url for url in downloaded_files)
    
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
        """Test automatic service startup"""
        with patch('subprocess.run') as mock_run, \
             patch('subprocess.Popen') as mock_popen, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True), \
             patch('os.chmod'), \
             patch('asyncio.sleep'):
            
            mock_run.return_value = MagicMock(returncode=0)
            mock_popen.return_value = MagicMock(pid=12345)
            
            # Mock both model download and health check
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b"test"]))
            mock_response.raise_for_status = MagicMock()
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = await install_kokoro_fastapi(auto_start=True)
            
            assert "service_status" in result
            assert result["service_status"] == "running"
            assert result["service_pid"] == 12345
    
    @pytest.mark.asyncio
    async def test_custom_port(self):
        """Test custom port configuration"""
        custom_port = 9999
        
        with patch('subprocess.run') as mock_run, \
             patch('os.path.exists', return_value=False), \
             patch('shutil.which', return_value=True), \
             patch('os.chdir'), \
             patch('os.makedirs'), \
             patch('aiohttp.ClientSession') as mock_session, \
             patch('builtins.open', create=True) as mock_open, \
             patch('os.chmod'), \
             patch('json.dump') as mock_json_dump:
            
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
            
            # Verify port in config
            assert result["service_url"] == f"http://127.0.0.1:{custom_port}"
            
            # Check that config was written with correct port
            config_calls = [call for call in mock_json_dump.call_args_list 
                          if call[0][0].get('port') == custom_port]
            assert len(config_calls) > 0
    
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