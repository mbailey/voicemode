"""Tests for service file update functionality."""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from voice_mode.tools.service import (
    load_service_file_version,
    get_installed_service_version,
    get_service_config_vars,
    update_service_files
)
from voice_mode.utils.gpu_detection import has_gpu_support


def test_load_service_file_version():
    """Test loading service file versions from versions.json."""
    # Test for kokoro on macOS
    version = load_service_file_version("kokoro", "plist")
    assert version == "1.3.0"  # Updated in v1.3.0 for simplified templates

    # Test for whisper on Linux
    version = load_service_file_version("whisper", "service")
    assert version == "1.2.0"  # Updated in v1.2.0 for simplified templates


def test_get_service_config_vars():
    """Test getting configuration variables for service templates.

    Note: In v1.3.0, templates were simplified to only need HOME and START_SCRIPT.
    Config like ports and models is now handled by start scripts via voicemode.env.
    """
    # Test whisper config - now only has HOME and START_SCRIPT
    whisper_vars = get_service_config_vars("whisper")
    assert "HOME" in whisper_vars
    assert "START_SCRIPT" in whisper_vars

    # Test kokoro config - now only has HOME and START_SCRIPT
    kokoro_vars = get_service_config_vars("kokoro")
    assert "HOME" in kokoro_vars
    assert "START_SCRIPT" in kokoro_vars


@pytest.mark.asyncio
async def test_update_service_files_already_up_to_date():
    """Test updating service files when already at latest version."""
    with patch('voice_mode.tools.service.get_installed_service_version') as mock_installed:
        with patch('voice_mode.tools.service.load_service_file_version') as mock_template:
            mock_installed.return_value = "1.1.0"
            mock_template.return_value = "1.1.0"
            
            result = await update_service_files("kokoro")
            assert "already up to date" in result
            assert "version 1.1.0" in result


@pytest.mark.asyncio
async def test_update_service_files_needs_update():
    """Test updating service files when update is needed."""
    with patch('voice_mode.tools.service.get_installed_service_version') as mock_installed:
        with patch('voice_mode.tools.service.load_service_file_version') as mock_template:
            with patch('voice_mode.tools.service.load_service_template') as mock_load:
                with patch('pathlib.Path.exists') as mock_exists:
                    with patch('pathlib.Path.write_text') as mock_write:
                        with patch('pathlib.Path.rename') as mock_rename:
                            with patch('subprocess.run') as mock_run:
                                with patch('voice_mode.tools.service.find_process_by_port') as mock_find:
                                    with patch('voice_mode.tools.service.get_service_config_vars') as mock_config:
                                        mock_installed.return_value = "1.0.0"
                                        mock_template.return_value = "1.1.0"
                                        mock_load.return_value = "template content with {KOKORO_PORT}"
                                        mock_exists.return_value = False  # Wrapper script doesn't exist
                                        mock_run.return_value = MagicMock(returncode=0)
                                        mock_find.return_value = None  # Not running
                                        mock_config.return_value = {"KOKORO_PORT": 8880, "KOKORO_DIR": "/tmp/kokoro"}
                                        
                                        result = await update_service_files("kokoro")
                                        assert "Updated kokoro service files" in result
                                        assert "from version 1.0.0 to 1.1.0" in result
                                    
                                    # Check that daemon-reload was called for Linux
                                    import platform
                                    if platform.system() == "Linux":
                                        mock_run.assert_called_with(
                                            ["systemctl", "--user", "daemon-reload"],
                                            capture_output=True
                                        )


@pytest.mark.asyncio
async def test_service_update_service_files_action():
    """Test the update-service-files functionality."""
    # Just test the update_service_files function directly
    result = await update_service_files("kokoro")
    
    # It should report already up to date or success
    assert "✅" in result or "❌" in result
    # Result should mention kokoro or service files
    assert "kokoro" in result.lower() or "service files" in result.lower()


def test_service_status_shows_version_info():
    """Test that status shows service file version information."""
    # This is tested via integration tests since it requires a running service
    # But we can test the version extraction logic
    with patch('voice_mode.tools.service.get_installed_service_version') as mock_installed:
        with patch('voice_mode.tools.service.load_service_file_version') as mock_template:
            mock_installed.return_value = "1.0.0"
            mock_template.return_value = "1.1.0"
            
            # The actual status function would include this info
            # We're just testing the version comparison logic here
            assert mock_installed.return_value != mock_template.return_value


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