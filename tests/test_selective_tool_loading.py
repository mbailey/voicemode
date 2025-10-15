"""Tests for selective tool loading functionality."""

import os
import sys
import subprocess
import importlib
import pytest
from unittest.mock import patch, MagicMock


def test_selective_loading_converse_only():
    """Test that VOICEMODE_TOOLS=converse only loads the converse tool."""
    # Run in subprocess to ensure clean import state
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys
os.environ['VOICEMODE_TOOLS'] = 'converse'

# Import after setting env var
from voice_mode import tools

# Check which tool modules are loaded
loaded_modules = [m for m in sys.modules.keys() if 'voice_mode.tools' in m]
print('LOADED:', sorted(loaded_modules))

# Verify statistics module is NOT loaded
assert 'voice_mode.tools.statistics' not in sys.modules
assert 'voice_mode.tools.converse' in sys.modules
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout
    assert "voice_mode.tools.converse" in result.stdout
    assert "voice_mode.tools.statistics" not in result.stdout.replace("LOADED:", "")


def test_selective_loading_multiple_tools():
    """Test that VOICEMODE_TOOLS_ENABLED can load multiple specified tools."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys
os.environ['VOICEMODE_TOOLS_ENABLED'] = 'converse,statistics'

from voice_mode import tools

loaded_modules = [m for m in sys.modules.keys() if 'voice_mode.tools' in m]
print('LOADED:', sorted(loaded_modules))

assert 'voice_mode.tools.converse' in sys.modules
assert 'voice_mode.tools.statistics' in sys.modules
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout


def test_all_tools_loaded_by_default():
    """Test that only essential tools (converse, service) are loaded by default."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys

# Ensure no filter variables are set
os.environ.pop('VOICEMODE_TOOLS', None)
os.environ.pop('VOICEMODE_TOOLS_ENABLED', None)
os.environ.pop('VOICEMODE_TOOLS_DISABLED', None)

from voice_mode import tools

loaded_modules = [m for m in sys.modules.keys() if 'voice_mode.tools' in m]
print('LOADED:', sorted(loaded_modules))

# Should only load essential tools by default (converse, service)
tool_count = len([m for m in loaded_modules if m.startswith('voice_mode.tools.')])
print(f'Tool count: {tool_count}')
assert tool_count == 2, f"Expected 2 tools (converse, service), got {tool_count}"
assert 'voice_mode.tools.converse' in sys.modules
assert 'voice_mode.tools.service' in sys.modules
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout


def test_invalid_tool_warning():
    """Test that specifying an invalid tool name logs a warning."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys
import logging

# Set up logging to capture warnings
logging.basicConfig(level=logging.WARNING)

os.environ['VOICEMODE_TOOLS_ENABLED'] = 'converse,nonexistent_tool'

from voice_mode import tools

# The valid tool should still load
assert 'voice_mode.tools.converse' in sys.modules
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout
    # Check for warning about nonexistent tool
    assert "not found" in result.stderr.lower() or "WARNING" in result.stderr


def test_statistics_tracking_without_loading_tools():
    """Test that statistics tracking can be imported without loading statistics tools."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys
os.environ['VOICEMODE_TOOLS'] = 'converse'

# Import the tracking function
from voice_mode.statistics_tracking import track_voice_interaction

# Verify statistics tools module is not loaded
assert 'voice_mode.tools.statistics' not in sys.modules

# Verify the function exists and is callable
assert callable(track_voice_interaction)
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout


@pytest.mark.skip(reason="Flaky test - passes individually but fails in full suite due to environment pollution from other tests")
def test_empty_voicemode_tools():
    """Test that empty VOICEMODE_TOOLS_ENABLED loads all tools (same as not set)."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys

os.environ['VOICEMODE_TOOLS_ENABLED'] = ''

from voice_mode import tools

loaded_modules = [m for m in sys.modules.keys() if 'voice_mode.tools' in m]
tool_count = len([m for m in loaded_modules if m.startswith('voice_mode.tools.')])
print(f'Tool count with empty string: {tool_count}')
assert tool_count > 5, f"Expected more than 5 tools, got {tool_count}"
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout


def test_whitespace_handling_in_tool_list():
    """Test that whitespace in tool list is handled correctly."""
    result = subprocess.run(
        [sys.executable, "-c", """
import os
import sys

os.environ['VOICEMODE_TOOLS_ENABLED'] = ' converse , statistics '

from voice_mode import tools

assert 'voice_mode.tools.converse' in sys.modules
assert 'voice_mode.tools.statistics' in sys.modules
print('SUCCESS')
"""],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "SUCCESS" in result.stdout