"""Shared fixtures for DJ module tests."""

from unittest.mock import Mock

import pytest

from voice_mode.dj import CommandResult, MpvBackend, MpvPlayer
from voice_mode.dj.controller import DJController


class MockBackend:
    """Mock mpv backend for testing.

    This class provides a controllable mock implementation of the
    MpvBackend protocol. Properties can be set directly and commands
    are tracked for verification.
    """

    def __init__(self):
        """Initialize with default mock state."""
        self._connected = True
        self._properties: dict = {
            "pid": 12345,
            "pause": False,
            "volume": 50.0,
            "time-pos": 30.0,
            "duration": 180.0,
            "path": "/path/to/track.mp3",
            "media-title": "Test Track",
            "chapter": 0,
            "chapter-list/count": 5,
            "chapter-metadata": {"title": "Chapter 1"},
        }
        self._commands: list = []
        self._command_results: dict = {}

    def send_command(self, command: list) -> CommandResult:
        """Record command and return appropriate result."""
        self._commands.append(command)

        # Check for custom command result
        cmd_key = tuple(command)
        if cmd_key in self._command_results:
            return self._command_results[cmd_key]

        # Handle get_property commands
        if command[0] == "get_property" and len(command) >= 2:
            prop_name = command[1]
            if prop_name in self._properties:
                return CommandResult(success=True, data=self._properties[prop_name])
            return CommandResult(success=False, error="property not found")

        # Handle set_property commands
        if command[0] == "set_property" and len(command) >= 3:
            prop_name = command[1]
            prop_value = command[2]
            self._properties[prop_name] = prop_value
            return CommandResult(success=True)

        # Handle other commands
        if command[0] == "quit":
            self._connected = False
            return CommandResult(success=True)

        if command[0] == "seek":
            return CommandResult(success=True)

        if command[0] == "add":
            # Handle chapter navigation
            if len(command) >= 3 and command[1] == "chapter":
                current = self._properties.get("chapter", 0)
                self._properties["chapter"] = current + command[2]
                return CommandResult(success=True)

        return CommandResult(success=True)

    def is_connected(self) -> bool:
        """Return the mock connection state."""
        return self._connected

    # Test helper methods

    def set_property(self, name: str, value) -> None:
        """Set a mock property value."""
        self._properties[name] = value

    def set_connected(self, connected: bool) -> None:
        """Set the mock connection state."""
        self._connected = connected

    def set_command_result(self, command: list, result: CommandResult) -> None:
        """Set a custom result for a specific command."""
        self._command_results[tuple(command)] = result

    def get_commands(self) -> list:
        """Get list of commands that were sent."""
        return self._commands.copy()

    def clear_commands(self) -> None:
        """Clear the command history."""
        self._commands.clear()


@pytest.fixture
def mock_backend():
    """Create a mock mpv backend for testing.

    Returns:
        MockBackend instance with default connected state.
    """
    return MockBackend()


@pytest.fixture
def mock_player(mock_backend):
    """Create a player with mocked backend.

    Args:
        mock_backend: The mock backend fixture.

    Returns:
        MpvPlayer instance using the mock backend.
    """
    return MpvPlayer(backend=mock_backend)


@pytest.fixture
def mock_controller(mock_player):
    """Create a controller with mocked player.

    Args:
        mock_player: The mock player fixture.

    Returns:
        DJController instance using the mock player.
    """
    return DJController(player=mock_player)


@pytest.fixture
def disconnected_backend():
    """Create a mock backend that simulates a disconnected state.

    Returns:
        MockBackend instance configured as disconnected.
    """
    backend = MockBackend()
    backend.set_connected(False)
    return backend


@pytest.fixture
def disconnected_player(disconnected_backend):
    """Create a player that simulates mpv not running.

    Args:
        disconnected_backend: The disconnected backend fixture.

    Returns:
        MpvPlayer instance with disconnected backend.
    """
    return MpvPlayer(backend=disconnected_backend)


@pytest.fixture
def disconnected_controller(disconnected_player):
    """Create a controller that simulates mpv not running.

    Args:
        disconnected_player: The disconnected player fixture.

    Returns:
        DJController instance with disconnected player.
    """
    return DJController(player=disconnected_player)
