"""
Low-level mpv IPC communication layer.

This module provides the MpvPlayer class for communicating with mpv
via its JSON IPC protocol over Unix sockets. The design uses dependency
injection for testability - a mock backend can be provided for unit tests.

Protocol documentation: https://mpv.io/manual/stable/#json-ipc
"""

import json
import socket
from typing import Any, Protocol

from .models import CommandResult


class MpvBackend(Protocol):
    """Protocol for mpv communication backends.

    This protocol defines the interface for communicating with mpv.
    The default implementation uses Unix sockets, but a mock can be
    injected for testing without requiring a running mpv instance.
    """

    def send_command(self, command: list) -> CommandResult:
        """Send a command to mpv and return the result.

        Args:
            command: Command as a list, e.g., ["set_property", "pause", True]

        Returns:
            CommandResult with success status and any returned data.
        """
        ...

    def is_connected(self) -> bool:
        """Check if mpv is responding.

        Returns:
            True if mpv is running and accepting commands.
        """
        ...


class SocketBackend:
    """Default mpv backend using Unix socket IPC.

    This implementation connects to mpv's JSON IPC socket to send
    commands and receive responses. Each command creates a new
    socket connection (mpv's socket doesn't require persistent connections).
    """

    def __init__(self, socket_path: str):
        """Initialize the socket backend.

        Args:
            socket_path: Path to mpv's IPC socket (e.g., /tmp/voicemode-mpv.sock)
        """
        self.socket_path = socket_path

    def send_command(self, command: list) -> CommandResult:
        """Send a command to mpv via the IPC socket.

        Args:
            command: Command as a list, e.g., ["set_property", "pause", True]

        Returns:
            CommandResult with the response from mpv.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)
                sock.connect(self.socket_path)

                # Send the command as JSON with newline terminator
                msg = json.dumps({"command": command}) + "\n"
                sock.sendall(msg.encode())

                # Read the response (may contain multiple lines for events)
                response_data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    # Check if we have a complete response (ends with newline)
                    if response_data.endswith(b"\n"):
                        break

                # Parse the first line (our command response)
                # Subsequent lines may be events which we ignore
                first_line = response_data.decode().split("\n")[0]
                response = json.loads(first_line)

                if response.get("error") == "success":
                    return CommandResult(success=True, data=response.get("data"))
                else:
                    return CommandResult(
                        success=False, error=response.get("error", "Unknown error")
                    )

        except FileNotFoundError:
            return CommandResult(success=False, error="Socket not found")
        except ConnectionRefusedError:
            return CommandResult(success=False, error="Connection refused")
        except socket.timeout:
            return CommandResult(success=False, error="Connection timeout")
        except json.JSONDecodeError as e:
            return CommandResult(success=False, error=f"Invalid JSON response: {e}")
        except OSError as e:
            return CommandResult(success=False, error=f"Socket error: {e}")

    def is_connected(self) -> bool:
        """Check if mpv is responding by querying its PID."""
        result = self.send_command(["get_property", "pid"])
        return result.success


class MpvPlayer:
    """Low-level mpv IPC wrapper.

    This class provides a clean Python interface to mpv's IPC commands.
    It handles connection management and provides methods for common
    operations like pause, resume, stop, and property access.

    The backend can be injected for testing purposes.
    """

    DEFAULT_SOCKET_PATH = "/tmp/voicemode-mpv.sock"

    def __init__(
        self,
        socket_path: str | None = None,
        backend: MpvBackend | None = None,
    ):
        """Initialize the player.

        Args:
            socket_path: Path to mpv's IPC socket. Defaults to /tmp/voicemode-mpv.sock
            backend: Optional backend for testing. If None, uses SocketBackend.
        """
        self.socket_path = socket_path or self.DEFAULT_SOCKET_PATH
        self._backend = backend or SocketBackend(self.socket_path)

    # Connection status

    def is_running(self) -> bool:
        """Check if mpv is running and responding.

        Returns:
            True if mpv is active and accepting commands.
        """
        return self._backend.is_connected()

    # Property access

    def get_property(self, name: str) -> Any:
        """Get an mpv property value.

        Args:
            name: Property name (e.g., "volume", "time-pos", "pause")

        Returns:
            The property value, or None if the property couldn't be read.
        """
        result = self._backend.send_command(["get_property", name])
        return result.data if result.success else None

    def set_property(self, name: str, value: Any) -> bool:
        """Set an mpv property value.

        Args:
            name: Property name (e.g., "volume", "pause")
            value: Value to set

        Returns:
            True if the property was set successfully.
        """
        result = self._backend.send_command(["set_property", name, value])
        return result.success

    # Playback control

    def pause(self) -> bool:
        """Pause playback.

        Returns:
            True if the command succeeded.
        """
        return self.set_property("pause", True)

    def resume(self) -> bool:
        """Resume playback.

        Returns:
            True if the command succeeded.
        """
        return self.set_property("pause", False)

    def stop(self) -> bool:
        """Stop playback and quit mpv.

        Returns:
            True if the command was sent successfully.
        """
        result = self._backend.send_command(["quit"])
        return result.success

    # Navigation

    def seek(self, position: float, mode: str = "absolute") -> bool:
        """Seek to a position.

        Args:
            position: Position in seconds (absolute) or offset (relative)
            mode: "absolute" or "relative"

        Returns:
            True if the seek succeeded.
        """
        result = self._backend.send_command(["seek", position, mode])
        return result.success

    def next_chapter(self) -> bool:
        """Skip to the next chapter.

        Returns:
            True if the command succeeded.
        """
        result = self._backend.send_command(["add", "chapter", 1])
        return result.success

    def prev_chapter(self) -> bool:
        """Go to the previous chapter.

        Returns:
            True if the command succeeded.
        """
        result = self._backend.send_command(["add", "chapter", -1])
        return result.success

    # Volume

    def get_volume(self) -> float | None:
        """Get the current volume level.

        Returns:
            Volume level (0-100), or None if unavailable.
        """
        value = self.get_property("volume")
        return float(value) if value is not None else None

    def set_volume(self, level: float) -> bool:
        """Set the volume level.

        Args:
            level: Volume level (0-100)

        Returns:
            True if the volume was set successfully.
        """
        # Clamp to valid range
        level = max(0, min(100, level))
        return self.set_property("volume", level)

    # Status information

    def get_position(self) -> float | None:
        """Get current playback position in seconds."""
        value = self.get_property("time-pos")
        return float(value) if value is not None else None

    def get_duration(self) -> float | None:
        """Get total duration in seconds."""
        value = self.get_property("duration")
        return float(value) if value is not None else None

    def get_path(self) -> str | None:
        """Get the path/URL of the current track."""
        return self.get_property("path")

    def get_title(self) -> str | None:
        """Get the track title from metadata."""
        return self.get_property("media-title")

    def is_paused(self) -> bool:
        """Check if playback is paused."""
        value = self.get_property("pause")
        return bool(value) if value is not None else False

    def get_chapter_metadata(self) -> dict | None:
        """Get metadata for the current chapter."""
        return self.get_property("chapter-metadata")

    def get_chapter_index(self) -> int | None:
        """Get the current chapter index (0-based)."""
        value = self.get_property("chapter")
        return int(value) if value is not None else None

    def get_chapter_count(self) -> int | None:
        """Get the total number of chapters."""
        value = self.get_property("chapter-list/count")
        return int(value) if value is not None else None
