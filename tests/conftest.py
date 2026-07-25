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
    """Wrapper that blocks dangerous system commands during tests.

    Returns a callable class (not a function) so that type subscripting like
    Popen[bytes] works. The mcp library uses this in type annotations and
    Python 3.10 raises TypeError on subscripted functions.
    """
    class SafePopen:
        """Callable wrapper for subprocess.Popen that blocks dangerous commands."""

        def __class_getitem__(cls, params):
            """Support type subscripting (e.g., Popen[bytes])."""
            return original_popen[params]

        def __new__(cls, *args, **kwargs):
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

    return SafePopen


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

    # Re-pin module-level path constants that captured Path.home() at IMPORT
    # time, so patching Path.home() above doesn't reach them. Without this, a
    # test transparently shares (and can clobber) the developer's real
    # ~/.voicemode state — e.g. converse() blocks on the live `conch` lock held
    # by a running voicemode process, and the autofocus sentinel toggles focus
    # off. Pin them into the isolated fake home instead.
    try:
        from voice_mode.conch import Conch
        monkeypatch.setattr(Conch, "LOCK_FILE", fake_home / ".voicemode" / "conch")
    except Exception:
        pass
    try:
        # VM-1775 impl-005: _emit_converse_state (the VM-1793 phase emitter)
        # writes ~/.voicemode/state.json on every survey speaking/listening
        # transition -- unconditionally, unlike the opt-in SAVE_AUDIO/
        # SAVE_TRANSCRIPTIONS debug writers. Any test that drives a real
        # `_ask_turns_pipeline`/`converse(turns=[{"ask": ...}])` call would
        # otherwise clobber the developer's real state.json, same class of
        # bug the Conch.LOCK_FILE re-pin above already guards against.
        import voice_mode.tools.converse as _converse_module
        monkeypatch.setattr(
            _converse_module, "BASE_DIR", fake_home / ".voicemode",
        )
    except Exception:
        pass
    try:
        # VM-1775 impl-007b (fable pre-merge audit F3): ConversationLogger
        # derives its base dir from voice_mode.config.BASE_DIR, frozen from
        # the REAL Path.home() at import time -- the exact same bug-class as
        # the Conch/converse BASE_DIR re-pins above, one file short. Without
        # this, any test that drives a real _ask_turns_pipeline / listen path
        # (most of test_ask_turns_pipeline.py, test_survey_return_contract.py,
        # test_listen_and_transcribe.py, test_state_emitter.py) writes real
        # entries into the developer's actual
        # ~/.voicemode/logs/conversations/exchanges_*.jsonl on every run.
        # Re-pin the module-level BASE_DIR constant into the fake home AND
        # reset the process-wide singleton, so a stale instance already
        # constructed (in an earlier test, or at import time) against the
        # real home isn't reused -- the next get_conversation_logger() call
        # builds a fresh one against the fake home.
        import voice_mode.conversation_logger as _convo_logger_module
        monkeypatch.setattr(_convo_logger_module, "BASE_DIR", fake_home / ".voicemode")
        monkeypatch.setattr(_convo_logger_module, "_conversation_logger", None)
    except Exception:
        pass
    try:
        # VM-1901 observability-001: same bug class again, closed for the
        # LAST module that had it. voice_mode.voice_profiles.VOICES_DIR is
        # frozen from the real os.path.expanduser("~/.voicemode/voices") at
        # import time, and its `_registry`/`_loaded` cache is a bare module
        # global with no per-test reset. Individual tests that need a custom
        # tree already cope by monkeypatching VOICEMODE_VOICES_DIR + calling
        # `importlib.reload(voice_profiles)` themselves -- but that reload
        # mutates the SAME module dict every other importer's already-bound
        # `resolve_voice`/`_ensure_loaded` references share (Python globals
        # are a live dict lookup, not a snapshot), so a stale tmp_path from
        # one test's reload silently outlives it for every later test in the
        # process. This went unnoticed while only simple_failover's deep,
        # rarely-exercised call path used resolve_voice(); VM-1901 made
        # converse() call it unconditionally on every single call (the
        # totality fix requires resolving BEFORE the conch, not just deep in
        # TTS), so re-pin + reset it here exactly like the three re-pins
        # above, so every test starts from a clean, fake-home-scoped state
        # regardless of what an earlier test's reload left behind.
        import voice_mode.voice_profiles as _voice_profiles_module
        monkeypatch.setattr(
            _voice_profiles_module, "VOICES_DIR", fake_home / ".voicemode" / "voices",
        )
        monkeypatch.setattr(_voice_profiles_module, "_loaded", False)
        monkeypatch.setattr(
            _voice_profiles_module, "_registry", _voice_profiles_module._Registry(),
        )
    except Exception:
        pass
    try:
        # VM-1901 observability-001: voice_mode.config.TTS_VOICES is frozen at
        # import time too, from `VOICEMODE_VOICES` -- which on a developer
        # machine is commonly set for real in ~/.voicemode/voicemode.env
        # (e.g. a personal clone voice like "laurie"), loaded via find_dotenv
        # BEFORE this fixture ever runs. That default is exactly what
        # converse() now resolves unconditionally on every call (the totality
        # fix above), so without this re-pin the whole suite's outcome would
        # depend on whichever developer's real voicemode.env happens to be on
        # PATH -- a personal voice that doesn't exist in the isolated fake
        # home's (nonexistent) voices dir would make every plain converse()
        # call in the suite fail resolution. Reset to the coded default so
        # the suite is deterministic regardless of the host's real config.
        # Re-pin at BOTH names: `voice_mode.config.TTS_VOICES` (the source
        # constant) and `voice_mode.tools.converse.TTS_VOICES` (a `from
        # voice_mode.config import TTS_VOICES` value binding in converse.py,
        # NOT a live attribute lookup -- patching config's copy alone would
        # leave converse.py's own name pointing at the original list).
        import voice_mode.config as _config_module
        monkeypatch.setattr(_config_module, "TTS_VOICES", ["af_sky", "alloy"])
        monkeypatch.setattr(_converse_module, "TTS_VOICES", ["af_sky", "alloy"])
    except Exception:
        pass
    try:
        from voice_mode.cli_commands import autofocus
        monkeypatch.setattr(
            autofocus, "SENTINEL_FILE",
            fake_home / ".voicemode" / "autofocus-disabled",
        )
        monkeypatch.setattr(
            autofocus, "VOICEMODE_ENV_FILE",
            fake_home / ".voicemode" / "voicemode.env",
        )
    except Exception:
        pass

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
