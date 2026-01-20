#!/usr/bin/env python3
"""Minimal help tests for voice-mode.

Reduced from ~270 parametrized tests to 2 high-value tests (VM-473).
The original tests were temporary guards for performance/import issues
that are now solved and were blocking legitimate deprecations.
"""

import subprocess
import sys
import os


class TestHelpBasics:
    """Basic sanity checks for help functionality."""

    def test_help_main_command_sections(self):
        """Test that main help command has all expected sections."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '--help'],
            capture_output=True,
            text=True,
            timeout=2
        )

        assert result.returncode == 0
        output = result.stdout.lower()

        # Main help should have these sections
        expected_sections = ['usage', 'options', 'commands']

        for section in expected_sections:
            assert section in output, f"Missing section '{section}' in main help"

    def test_help_no_heavy_imports(self):
        """Verify help doesn't trigger heavy imports."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '--help'],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )

        assert result.returncode == 0

        stderr_lower = result.stderr.lower()

        # These indicate heavy imports that shouldn't happen for help
        unwanted_indicators = ['numba', 'torch', 'tensorflow']

        for indicator in unwanted_indicators:
            assert indicator not in stderr_lower, \
                f"Heavy import detected in help: {indicator}"
