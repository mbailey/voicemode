"""Shared test fixtures and configuration for VoiceMode tests."""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio

# Add voice_mode to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent))


# Commands that should never run in tests - these affect system services
BLOCKED_COMMANDS = {
    "launchctl",
    "systemctl",
    "brew",
}


def _safe_subprocess_run(original_run):
    """Wrapper that blocks dangerous system commands during tests."""
    def wrapper(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, str):
            cmd_parts = cmd.split()
        else:
            cmd_parts = list(cmd) if cmd else []

        if cmd_parts and cmd_parts[0] in BLOCKED_COMMANDS:
            # Return a mock result instead of running the command
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        return original_run(*args, **kwargs)
    return wrapper


def _safe_subprocess_popen(original_popen):
    """Wrapper that blocks dangerous system commands during tests."""
    def wrapper(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, str):
            cmd_parts = cmd.split()
        else:
            cmd_parts = list(cmd) if cmd else []

        if cmd_parts and cmd_parts[0] in BLOCKED_COMMANDS:
            # Return a mock process instead of running the command
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.poll.return_value = 0
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            return mock_proc

        return original_popen(*args, **kwargs)
    return wrapper


@pytest.fixture(autouse=True)
def block_dangerous_commands(monkeypatch):
    """
    Automatically block dangerous system commands in all tests.

    This prevents tests from accidentally running launchctl, systemctl,
    or other system commands that could affect running services.
    Tests that need to verify these commands are called should use
    explicit mocking with patch().
    """
    original_run = subprocess.run
    original_popen = subprocess.Popen

    monkeypatch.setattr("subprocess.run", _safe_subprocess_run(original_run))
    monkeypatch.setattr("subprocess.Popen", _safe_subprocess_popen(original_popen))


@pytest.fixture(autouse=True)
def isolate_home_directory(tmp_path, monkeypatch):
    """
    Redirect Path.home() and os.path.expanduser() to a temporary directory.

    This prevents tests from writing plist files to ~/Library/LaunchAgents/
    or systemd service files to ~/.config/systemd/user/. The isolation is
    automatic for all tests.

    Without this fixture, running pytest would install service files to
    the real home directory, causing:
    - Apple notifications about services being configured
    - Services potentially starting automatically
    - Developer's local service configuration being affected
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Create expected subdirectories that tests may write to
    (fake_home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    (fake_home / ".config" / "systemd" / "user").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "logs").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "services").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "config").mkdir(parents=True, exist_ok=True)

    # Mock Path.home() to return the fake home directory
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # Mock os.path.expanduser() to handle ~ expansion
    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path.startswith("~"):
            return str(fake_home) + path[1:]
        return original_expanduser(path)

    monkeypatch.setattr("os.path.expanduser", mock_expanduser)

    yield fake_home


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_mcp():
    """Create a mock FastMCP instance for testing tools."""
    from fastmcp import FastMCP
    mcp = MagicMock(spec=FastMCP)
    mcp.tool = MagicMock()
    
    # Make the decorator work properly
    def tool_decorator(**kwargs):
        def decorator(func):
            func._mcp_tool_config = kwargs
            return func
        return decorator
    
    mcp.tool.side_effect = tool_decorator
    return mcp


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess calls."""
    import subprocess
    mock = MagicMock()
    mock.Popen = MagicMock()
    mock.run = MagicMock()
    mock.DEVNULL = subprocess.DEVNULL
    mock.PIPE = subprocess.PIPE
    monkeypatch.setattr("subprocess.Popen", mock.Popen)
    monkeypatch.setattr("subprocess.run", mock.run)
    return mock
