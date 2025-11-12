"""Tests for service health check functionality."""

import os
import tempfile
from pathlib import Path
import pytest

from voice_mode.tools.service import load_service_template


def test_systemd_template_has_health_check():
    """Test that systemd templates include health check commands."""
    from unittest.mock import patch
    
    # Mock platform to get Linux templates
    with patch('voice_mode.tools.service.platform.system', return_value='Linux'):
        # Test Kokoro systemd template
        kokoro_template = load_service_template("kokoro")
        assert "ExecStartPost=" in kokoro_template
        assert "curl" in kokoro_template
        assert "/health" in kokoro_template
        assert "Waiting for Kokoro to be ready" in kokoro_template
        
        # Test Whisper systemd template  
        whisper_template = load_service_template("whisper")
        assert "ExecStartPost=" in whisper_template
        assert "curl" in whisper_template
        assert "/health" in whisper_template
        assert "Waiting for Whisper to be ready" in whisper_template


def test_launchd_wrapper_scripts_exist():
    """Test that launchd wrapper scripts with health checks exist."""
    templates_dir = Path(__file__).parent.parent / "voice_mode" / "templates" / "launchd"
    
    kokoro_wrapper = templates_dir / "start-kokoro-with-health-check.sh"
    assert kokoro_wrapper.exists()
    assert kokoro_wrapper.stat().st_mode & 0o111  # Check executable
    
    whisper_wrapper = templates_dir / "start-whisper-with-health-check.sh"
    assert whisper_wrapper.exists()
    assert whisper_wrapper.stat().st_mode & 0o111  # Check executable


def test_wrapper_script_content():
    """Test that wrapper scripts contain proper health check logic."""
    templates_dir = Path(__file__).parent.parent / "voice_mode" / "templates" / "launchd"
    
    # Check Kokoro wrapper
    kokoro_wrapper = templates_dir / "start-kokoro-with-health-check.sh"
    content = kokoro_wrapper.read_text()
    assert "#!/bin/bash" in content
    assert "curl -sf http://127.0.0.1:{KOKORO_PORT}/health" in content
    assert "kill -0 $SERVICE_PID" in content  # Process check
    assert "Kokoro is ready" in content
    
    # Check Whisper wrapper
    whisper_wrapper = templates_dir / "start-whisper-with-health-check.sh"
    content = whisper_wrapper.read_text()
    assert "#!/bin/bash" in content
    assert "curl -sf http://127.0.0.1:{WHISPER_PORT}/health" in content
    assert "kill -0 $SERVICE_PID" in content  # Process check
    assert "Whisper is ready" in content


def test_health_check_timeout_handling():
    """Test that health checks handle timeouts properly."""
    templates_dir = Path(__file__).parent.parent / "voice_mode" / "templates" / "launchd"
    
    for script_name in ["start-kokoro-with-health-check.sh", "start-whisper-with-health-check.sh"]:
        script_path = templates_dir / script_name
        content = script_path.read_text()
        
        # Check for process monitoring during health check
        assert "if ! kill -0 $SERVICE_PID" in content
        assert "failed to start" in content
        assert "exit 1" in content  # Proper error exit


def test_template_placeholders():
    """Test that templates use consistent placeholders."""
    from unittest.mock import patch
    
    # Mock platform to get Linux templates
    with patch('voice_mode.tools.service.platform.system', return_value='Linux'):
        # Kokoro templates
        kokoro_systemd = load_service_template("kokoro")
        assert "{KOKORO_PORT}" in kokoro_systemd
        assert "{KOKORO_DIR}" in kokoro_systemd
        assert "{START_SCRIPT}" in kokoro_systemd
        
        # Whisper templates (v1.1.0 uses startup script approach)
        whisper_systemd = load_service_template("whisper")
        assert "{WHISPER_PORT}" in whisper_systemd  # Used in health check
        assert "{START_SCRIPT_PATH}" in whisper_systemd  # New startup script approach
        assert "{LOG_DIR}" in whisper_systemd  # File-based logging
        assert "{INSTALL_DIR}" in whisper_systemd  # Working directory