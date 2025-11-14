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


def test_unified_startup_scripts_exist():
    """Test that unified startup scripts exist where appropriate.

    Note: Only Whisper uses a unified startup script in templates.
    Kokoro uses its own startup scripts that come with the installation.
    """
    templates_dir = Path(__file__).parent.parent / "voice_mode" / "templates" / "scripts"

    # Check Whisper unified startup script (used by both macOS and Linux)
    whisper_script = templates_dir / "start-whisper-server.sh"
    assert whisper_script.exists()
    assert whisper_script.stat().st_mode & 0o111  # Check executable

    # Kokoro doesn't have a unified startup script in templates
    # It uses start-gpu_mac.sh, start-gpu.sh, or start-cpu.sh from the Kokoro installation


def test_startup_script_content():
    """Test that unified startup scripts contain proper configuration loading.

    Note: Only Whisper has a unified startup script to test.
    Kokoro uses its own scripts from the installation package.
    """
    templates_dir = Path(__file__).parent.parent / "voice_mode" / "templates" / "scripts"

    # Check Whisper startup script
    whisper_script = templates_dir / "start-whisper-server.sh"
    content = whisper_script.read_text()
    assert "#!/bin/bash" in content
    assert "source" in content  # Sources voicemode.env
    assert "VOICEMODE_WHISPER_MODEL" in content  # Reads model config
    assert "VOICEMODE_WHISPER_PORT" in content  # Reads port config

    # Kokoro doesn't have a unified startup script to test here
    # Its scripts (start-gpu_mac.sh, start-gpu.sh, start-cpu.sh) come with the installation


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