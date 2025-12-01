"""Tests for service health check functionality."""

import os
import tempfile
from pathlib import Path
import pytest

from voice_mode.tools.service import load_service_template


def test_systemd_template_simplified():
    """Test that systemd templates are simplified (v1.2.0+).

    Note: As of v1.2.0, templates were simplified to only need START_SCRIPT.
    Health checks were removed in favor of letting start scripts handle config.
    """
    from unittest.mock import patch

    # Mock platform to get Linux templates
    with patch('voice_mode.tools.service.platform.system', return_value='Linux'):
        # Test Kokoro systemd template - simplified
        kokoro_template = load_service_template("kokoro")
        assert "{START_SCRIPT}" in kokoro_template
        assert "[Service]" in kokoro_template
        assert "[Unit]" in kokoro_template
        assert "[Install]" in kokoro_template

        # Test Whisper systemd template - simplified
        whisper_template = load_service_template("whisper")
        assert "{START_SCRIPT}" in whisper_template
        assert "[Service]" in whisper_template


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
    """Test that templates use consistent placeholders.

    Note: As of v1.2.0, templates were simplified to only need START_SCRIPT.
    Port, directory, and log configs are handled by start scripts via voicemode.env.
    """
    from unittest.mock import patch

    # Mock platform to get Linux templates
    with patch('voice_mode.tools.service.platform.system', return_value='Linux'):
        # Kokoro templates - simplified to just START_SCRIPT
        kokoro_systemd = load_service_template("kokoro")
        assert "{START_SCRIPT}" in kokoro_systemd
        # Removed in v1.2.0: KOKORO_PORT, KOKORO_DIR (handled by start script)

        # Whisper templates - simplified to just START_SCRIPT
        whisper_systemd = load_service_template("whisper")
        assert "{START_SCRIPT}" in whisper_systemd
        # Removed in v1.2.0: WHISPER_PORT, LOG_DIR, INSTALL_DIR (handled by start script)