# VM-310: Test Isolation for Plist Files - Technical Specification

## Overview

Prevent tests from writing plist files to the real `~/Library/LaunchAgents/` directory by adding an autouse fixture that mocks `Path.home()` to return a temporary directory.

## Problem Summary

Running `pytest` installs plist files to `~/Library/LaunchAgents/` on macOS, causing:
1. Apple notifications about services being configured to start automatically
2. Services potentially starting automatically
3. Developer's local service configuration being affected

The existing `conftest.py` blocks subprocess calls to `launchctl`, `systemctl`, and `brew`, but does NOT block file writes using `Path.home()` or `os.path.expanduser()`.

## Solution: Mock Path.home() Globally in conftest.py

### Why This Approach

1. **Single point of isolation** - All plist-writing code consistently uses `Path.home()` for the LaunchAgents path
2. **Existing pattern** - Some tests already mock `Path.home()` successfully (test_unified_service.py:153, test_diagnostics.py:20)
3. **Minimal code changes** - One fixture in conftest.py covers all cases
4. **No production code changes** - Fix is entirely in test infrastructure
5. **Also handles os.path.expanduser()** - The fixture will mock both `Path.home()` and `os.path.expanduser()` for complete coverage

## Files to Modify

### Primary Change

**`tests/conftest.py`** - Add autouse fixture to mock Path.home()

```python
@pytest.fixture(autouse=True)
def isolate_home_directory(tmp_path, monkeypatch):
    """
    Redirect Path.home() and os.path.expanduser() to a temporary directory.

    This prevents tests from writing plist files to ~/Library/LaunchAgents/
    or systemd service files to ~/.config/systemd/user/. The isolation is
    automatic for all tests.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Create expected subdirectories
    (fake_home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    (fake_home / ".config" / "systemd" / "user").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "logs").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "services").mkdir(parents=True, exist_ok=True)
    (fake_home / ".voicemode" / "config").mkdir(parents=True, exist_ok=True)

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # Mock os.path.expanduser() to handle ~ expansion
    original_expanduser = os.path.expanduser
    def mock_expanduser(path):
        if path.startswith("~"):
            return str(fake_home) + path[1:]
        return original_expanduser(path)

    monkeypatch.setattr("os.path.expanduser", mock_expanduser)

    yield fake_home
```

### Files Using Path.home() for Service Paths

These files will automatically benefit from the isolation (no changes needed):

| File | Lines | Usage |
|------|-------|-------|
| `voice_mode/tools/service.py` | 124, 126, 189, 191, 347, 375, 451, 499, 517, 649, 686, 724, 768, 815, 937, 943, 962, 969 | LaunchAgents and systemd paths |
| `voice_mode/tools/whisper/install.py` | 162, 218 | Service file installation |
| `voice_mode/tools/whisper/uninstall.py` | 65, 87 | Service file removal |
| `voice_mode/tools/kokoro/uninstall.py` | 59, 97 | Service file removal |
| `voice_mode/tools/livekit/uninstall.py` | 52 | Service cleanup |
| `voice_mode/tools/configuration_management.py` | 14, 16, 423 | Config path |
| `voice_mode/tools/whisper/models.py` | 102, 222, 349, 358 | Model and config paths |
| `voice_mode/tools/livekit/frontend.py` | 99, 103, 107, 242, 527, 670 | Frontend paths |
| `voice_mode/tools/whisper/model_install.py` | 71, 72 | Model installation |

### New Test File

**`tests/test_isolation.py`** - Verify isolation works

```python
"""Tests to verify test isolation is working correctly."""

import os
import pytest
from pathlib import Path


class TestHomeIsolation:
    """Verify that Path.home() and os.path.expanduser() are properly isolated."""

    def test_path_home_is_isolated(self, isolate_home_directory):
        """Path.home() should return a temp directory, not real home."""
        home = Path.home()
        assert home == isolate_home_directory
        assert str(home) != os.environ.get("HOME", "")
        assert "LaunchAgents" not in str(home)

    def test_expanduser_is_isolated(self, isolate_home_directory):
        """os.path.expanduser() should use the fake home."""
        expanded = os.path.expanduser("~")
        assert expanded == str(isolate_home_directory)

        expanded_path = os.path.expanduser("~/.voicemode")
        assert expanded_path == str(isolate_home_directory / ".voicemode")

    def test_launchagents_directory_exists(self, isolate_home_directory):
        """The fake LaunchAgents directory should exist."""
        launchagents = isolate_home_directory / "Library" / "LaunchAgents"
        assert launchagents.exists()
        assert launchagents.is_dir()

    def test_systemd_directory_exists(self, isolate_home_directory):
        """The fake systemd user directory should exist."""
        systemd_dir = isolate_home_directory / ".config" / "systemd" / "user"
        assert systemd_dir.exists()
        assert systemd_dir.is_dir()

    def test_voicemode_directories_exist(self, isolate_home_directory):
        """Standard .voicemode directories should exist."""
        for subdir in ["logs", "services", "config"]:
            path = isolate_home_directory / ".voicemode" / subdir
            assert path.exists(), f"{subdir} should exist"
```

## Implementation Steps

### Step 1: Update conftest.py

1. Add the `isolate_home_directory` autouse fixture after the existing `block_dangerous_commands` fixture
2. Import `os` at the top if not already imported
3. The fixture must:
   - Create a temporary fake home directory
   - Set up expected subdirectory structure
   - Mock `pathlib.Path.home` to return the fake home
   - Mock `os.path.expanduser` to expand `~` to the fake home

### Step 2: Create test_isolation.py

1. Create new test file with tests that verify the isolation works
2. Tests should confirm:
   - `Path.home()` returns the temp directory
   - `os.path.expanduser("~")` returns the temp directory
   - Expected subdirectories exist

### Step 3: Run Tests

1. Run `pytest tests/test_isolation.py -v` to verify isolation tests pass
2. Run full test suite `pytest tests/ -v` to verify no regressions
3. Verify no plist files appear in real `~/Library/LaunchAgents/` after tests

## Fixture Order Considerations

The `isolate_home_directory` fixture should run BEFORE any test that might write files. Since it's `autouse=True`, pytest will automatically run it for every test. The `tmp_path` fixture is provided by pytest and creates a unique temporary directory per test.

## Edge Cases Handled

1. **Multiple Path.home() calls** - All return the same fake home
2. **os.path.expanduser("~/subpath")** - Correctly expands to fake home + subpath
3. **Non-tilde paths to expanduser** - Passed through unchanged
4. **Nested directories** - Pre-created to avoid mkdir errors in tests
5. **Parallel test execution** - Each test gets its own tmp_path, so no conflicts

## Success Criteria

1. Running `pytest` does not create any files in `~/Library/LaunchAgents/`
2. No Apple notifications about service installation during tests
3. All existing tests pass
4. New isolation tests verify the mechanism works
5. Tests that previously created real plist files now create them in temp directories

## Rollback Plan

If issues arise, the fixture can be disabled by:
1. Removing the `autouse=True` parameter
2. Or deleting the fixture entirely

The existing subprocess blocking remains in place as a secondary defense.
