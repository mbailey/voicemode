"""Tests for service file update functionality."""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from voice_mode.tools.service import (
    get_service_config_vars,
)
from voice_mode.utils.gpu_detection import has_gpu_support


def test_get_service_config_vars():
    """Test getting configuration variables for service templates.

    Note: In v1.3.0, templates were simplified to only need HOME and START_SCRIPT.
    Config like ports and models is now handled by start scripts via voicemode.env.
    """
    # Test whisper config - now only has HOME and START_SCRIPT
    whisper_vars = get_service_config_vars("whisper")
    assert "HOME" in whisper_vars
    assert "START_SCRIPT" in whisper_vars

    # Test kokoro config - has HOME, START_SCRIPT, KOKORO_DIR, KOKORO_MAX_REQUESTS
    kokoro_vars = get_service_config_vars("kokoro")
    assert "HOME" in kokoro_vars
    assert "START_SCRIPT" in kokoro_vars
    assert "KOKORO_MAX_REQUESTS" in kokoro_vars
    assert int(kokoro_vars["KOKORO_MAX_REQUESTS"]) > 0


def test_get_service_config_vars_handles_missing_start_script():
    """Test that get_service_config_vars handles missing start scripts gracefully."""
    import platform
    import tempfile
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock find_kokoro_fastapi to return our temp directory
        with patch('voice_mode.tools.service.find_kokoro_fastapi') as mock_find:
            mock_find.return_value = tmpdir
            
            # On Linux, create only start-gpu.sh (not start.sh)
            if platform.system() != "Darwin":
                start_gpu = Path(tmpdir) / "start-gpu.sh"
                start_gpu.write_text("#!/bin/bash\necho test")
                start_gpu.chmod(0o755)
            else:
                # On macOS, create start-gpu_mac.sh
                start_mac = Path(tmpdir) / "start-gpu_mac.sh"
                start_mac.write_text("#!/bin/bash\necho test")
                start_mac.chmod(0o755)
            
            # Get config vars - should find the correct script
            config_vars = get_service_config_vars("kokoro")
            
            # START_SCRIPT should not be empty
            assert config_vars["START_SCRIPT"] != ""
            assert Path(config_vars["START_SCRIPT"]).exists()
            
            # Verify it found the right script
            if platform.system() != "Darwin":
                assert "start-gpu.sh" in config_vars["START_SCRIPT"]
            else:
                assert "start-gpu_mac.sh" in config_vars["START_SCRIPT"]


def test_get_service_config_vars_returns_empty_when_no_script_found():
    """Test that get_service_config_vars returns empty START_SCRIPT when no scripts exist."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock find_kokoro_fastapi to return our temp directory
        with patch('voice_mode.tools.service.find_kokoro_fastapi') as mock_find:
            mock_find.return_value = tmpdir
            
            # Don't create any start scripts
            
            # Get config vars
            config_vars = get_service_config_vars("kokoro")
            
            # START_SCRIPT should be empty when no scripts are found
            assert config_vars["START_SCRIPT"] == ""


def test_get_service_config_vars_selects_gpu_script_when_gpu_available():
    """Test that get_service_config_vars prefers GPU script when GPU is detected."""
    import platform
    import tempfile
    from pathlib import Path
    
    if platform.system() == "Darwin":
        pytest.skip("macOS always uses start-gpu_mac.sh")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock find_kokoro_fastapi to return our temp directory
        with patch('voice_mode.tools.service.find_kokoro_fastapi') as mock_find:
            with patch('voice_mode.tools.service.has_gpu_support') as mock_gpu:
                mock_find.return_value = tmpdir
                mock_gpu.return_value = True  # GPU is available
                
                # Create both GPU and CPU scripts
                gpu_script = Path(tmpdir) / "start-gpu.sh"
                cpu_script = Path(tmpdir) / "start-cpu.sh"
                gpu_script.write_text("#!/bin/bash\necho gpu")
                cpu_script.write_text("#!/bin/bash\necho cpu")
                gpu_script.chmod(0o755)
                cpu_script.chmod(0o755)
                
                # Get config vars - should prefer GPU script
                config_vars = get_service_config_vars("kokoro")
                
                # Should select GPU script
                assert "start-gpu.sh" in config_vars["START_SCRIPT"]
                assert Path(config_vars["START_SCRIPT"]).exists()


def test_get_service_config_vars_selects_cpu_script_when_no_gpu():
    """Test that get_service_config_vars prefers CPU script when no GPU is detected."""
    import platform
    import tempfile
    from pathlib import Path
    
    if platform.system() == "Darwin":
        pytest.skip("macOS always uses start-gpu_mac.sh")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock find_kokoro_fastapi to return our temp directory
        with patch('voice_mode.tools.service.find_kokoro_fastapi') as mock_find:
            with patch('voice_mode.tools.service.has_gpu_support') as mock_gpu:
                mock_find.return_value = tmpdir
                mock_gpu.return_value = False  # No GPU available
                
                # Create both GPU and CPU scripts
                gpu_script = Path(tmpdir) / "start-gpu.sh"
                cpu_script = Path(tmpdir) / "start-cpu.sh"
                gpu_script.write_text("#!/bin/bash\necho gpu")
                cpu_script.write_text("#!/bin/bash\necho cpu")
                gpu_script.chmod(0o755)
                cpu_script.chmod(0o755)
                
                # Get config vars - should prefer CPU script
                config_vars = get_service_config_vars("kokoro")
                
                # Should select CPU script
                assert "start-cpu.sh" in config_vars["START_SCRIPT"]
                assert Path(config_vars["START_SCRIPT"]).exists()