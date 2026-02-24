"""
DEPRECATED: Use voice_mode.connect.client instead.

This module is retained for backward compatibility. The functionality has been
refactored into the voice_mode.connect package (types, config, users, messaging,
presence, client).

See: voice_mode/connect/client.py for the replacement ConnectClient class.
"""

import asyncio
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .config import CONNECT_ENABLED, CONNECT_WS_URL

logger = logging.getLogger("voicemode")


@dataclass
class DeviceInfo:
    """A remote device connected via VoiceMode Connect.

    Maps the ConnectionInfo interface from voicemode-connect's protocol.ts.
    """

    session_id: str
    device_id: Optional[str] = None
    platform: Optional[str] = None
    name: Optional[str] = None
    capabilities: dict = field(default_factory=dict)
    ready: bool = False
    connected_at: float = 0
    last_activity: float = 0

    @classmethod
    def from_connection_info(cls, data: dict) -> "DeviceInfo":
        """Create from a ConnectionInfo JSON object from the server."""
        return cls(
            session_id=data.get("sessionId", ""),
            device_id=data.get("deviceId"),
            platform=data.get("platform"),
            name=data.get("name"),
            capabilities=data.get("capabilities", {}),
            ready=data.get("ready", False),
            connected_at=data.get("connectedAt", 0),
            last_activity=data.get("lastActivity", 0),
        )

    def display_name(self) -> str:
        """Human-readable device name."""
        if self.name:
            return self.name
        if self.platform:
            return self.platform.capitalize()
        return f"Device {self.session_id[:8]}"

    def capabilities_str(self) -> str:
        """Short capabilities summary like 'TTS+STT'."""
        caps = []
        if self.capabilities.get("tts"):
            caps.append("TTS")
        if self.capabilities.get("stt"):
            caps.append("STT")
        if self.capabilities.get("mic"):
            caps.append("Mic")
        if self.capabilities.get("speaker"):
            caps.append("Speaker")
        return "+".join(caps) if caps else "none"

    def activity_ago(self) -> str:
        """How long ago the device was last active."""
        if not self.last_activity:
            return "unknown"
        seconds = time.time() - self.last_activity / 1000  # JS timestamps are ms
        if seconds < 60:
            return "just now"
        minutes = int(seconds / 60)
        if minutes < 60:
            return f"{minutes}m ago"
        hours = int(minutes / 60)
        if hours < 24:
            return f"{hours}h ago"
        return f"{int(hours / 24)}d ago"


class ConnectRegistry:
    """Singleton registry for VoiceMode Connect WebSocket connection.

    Lazily connects to voicemode.dev on first use. Maintains a background
    asyncio.Task for the WebSocket connection with auto-reconnect.
    """

    def __init__(self):
        self._initialized = False
        self._devices: List[DeviceInfo] = []
        self._connected = False
        self._session_id: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._ws = None  # Active WebSocket connection reference
        self._status_message: Optional[str] = None
        self._reconnect_count = 0
        # Available agent state
        self._available_team_name: Optional[str] = None
        self._available_agent_name: Optional[str] = None
        self._available_agent_platform: Optional[str] = None

    @property
    def devices(self) -> List[DeviceInfo]:
        return list(self._devices)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_connecting(self) -> bool:
        """True if a connection attempt is in progress (task running but not yet connected)."""
        return self._task is not None and not self._task.done() and not self._connected

    @property
    def status_message(self) -> str:
        """Current status message for diagnostics."""
        return self._status_message or ("Connected" if self._connected else "Not initialized")

    async def initialize(self):
        """Start the WebSocket connection if not already running.

        Idempotent - safe to call multiple times. Checks config and
        credentials before attempting to connect.
        """
        if self._initialized:
            return

        self._initialized = True

        if not CONNECT_ENABLED:
            self._status_message = "Disabled (VOICEMODE_CONNECT_ENABLED=false)"
            logger.debug("Connect registry disabled by config")
            return

        # Check credentials (synchronous call, run in thread)
        try:
            from .auth import get_valid_credentials
            creds = await asyncio.to_thread(get_valid_credentials, auto_refresh=True)
        except Exception as e:
            self._status_message = f"Auth error: {e}"
            logger.warning(f"Connect registry: could not load credentials: {e}")
            return

        if creds is None:
            self._status_message = "Not connected (no credentials - run: voicemode connect login)"
            logger.debug("Connect registry: no credentials available")
            return

        # Spawn background connection task
        self._task = asyncio.create_task(self._connection_loop())

    async def _connection_loop(self):
        """Main WebSocket connection loop with auto-reconnect."""
        try:
            import websockets
        except ImportError:
            self._status_message = "websockets package not installed"
            logger.error("Connect registry: websockets package not available")
            return

        retry_delay = 1
        max_retry_delay = 60

        while True:
            try:
                # Get fresh credentials for each connection attempt
                from .auth import get_valid_credentials
                creds = await asyncio.to_thread(get_valid_credentials, auto_refresh=True)
                if creds is None:
                    self._status_message = "Not connected (credentials expired)"
                    self._connected = False
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue

                ws_url = CONNECT_WS_URL

                self._status_message = "Connecting..."

                async with websockets.connect(
                    ws_url,
                    additional_headers={"Authorization": f"Bearer {creds.access_token}"},
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    retry_delay = 1  # Reset on successful connection
                    self._reconnect_count = 0

                    # Wait for 'connected' message
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if msg.get("type") == "connected":
                        self._session_id = msg.get("sessionId", "")[:12]
                        self._status_message = "Connected"
                        logger.info(f"Connect registry: connected (session: {self._session_id})")
                    else:
                        logger.warning(f"Connect registry: unexpected first message: {msg.get('type')}")

                    # Send ready message
                    from .version import __version__
                    ready_msg = {
                        "type": "ready",
                        "device": {
                            "platform": "mcp-server",
                            "appVersion": __version__,
                        },
                        "capabilities": {
                            "tts": True,
                            "stt": True,
                        },
                    }
                    await ws.send(json.dumps(ready_msg))

                    # Re-register as available if previously registered
                    if self._available_team_name:
                        await self._send_available_registration(ws)

                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

                    try:
                        # Receive loop
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                                await self._handle_message(msg)
                            except json.JSONDecodeError:
                                logger.warning(f"Connect registry: invalid JSON: {raw[:100]}")
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.info("Connect registry: shutting down")
                self._connected = False
                self._ws = None
                self._status_message = "Shut down"
                return
            except Exception as e:
                self._connected = False
                self._ws = None
                self._devices = []
                self._reconnect_count += 1
                self._status_message = f"Reconnecting (attempt {self._reconnect_count})"
                logger.debug(f"Connect registry: connection error: {e}, retrying in {retry_delay}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _heartbeat_loop(self, ws):
        """Send periodic heartbeats to keep the connection alive."""
        while True:
            await asyncio.sleep(25)
            try:
                await ws.send(json.dumps({
                    "type": "heartbeat",
                    "timestamp": int(time.time() * 1000),
                }))
            except Exception:
                return  # Connection closed

    async def _handle_message(self, msg: dict):
        """Handle a message from the WebSocket server."""
        msg_type = msg.get("type")

        if msg_type == "devices":
            # Replace device list with current devices
            devices = msg.get("devices", [])
            self._devices = [
                DeviceInfo.from_connection_info(d) for d in devices
            ]
            logger.debug(f"Connect registry: {len(self._devices)} device(s) connected")

        elif msg_type == "heartbeat_ack" or msg_type == "heartbeat":
            pass  # Expected, no action needed

        elif msg_type == "error":
            error_msg = msg.get("message", "Unknown error")
            error_code = msg.get("code", "")
            logger.warning(f"Connect registry: server error: {error_msg} ({error_code})")

        elif msg_type == "ack":
            pass  # Acknowledgment, no action needed

        elif msg_type == "user_message_delivery":
            # A user sent a message to this available user via the dashboard
            text = msg.get("text", "")
            sender = msg.get("from", "user")
            await self._handle_user_message_delivery(text, sender)

        else:
            logger.debug(f"Connect registry: unhandled message type: {msg_type}")

    async def _handle_user_message_delivery(self, text: str, sender: str):
        """Handle an incoming user_message_delivery by calling send-message to inject into team inbox."""
        team_name = self._available_team_name
        if not team_name:
            logger.warning("Connect registry: received user_message_delivery but not registered as available")
            return

        if not text.strip():
            logger.warning("Connect registry: received empty user_message_delivery, ignoring")
            return

        # Check send-message is available
        send_message_path = shutil.which("send-message")
        if not send_message_path:
            logger.error("Connect registry: send-message not found on PATH")
            return

        try:
            cmd = [send_message_path, team_name, "--from", sender, text]
            logger.info(f"Connect registry: delivering message to team '{team_name}' from '{sender}'")
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                logger.error(f"Connect registry: send-message failed: {result.stderr.strip()}")
            else:
                logger.info(f"Connect registry: message delivered: {result.stdout.strip()}")
        except subprocess.TimeoutExpired:
            logger.error("Connect registry: send-message timed out")
        except Exception as e:
            logger.error(f"Connect registry: failed to deliver message: {e}")

    async def register_available(self, team_name: str, agent_name: str, agent_platform: str = "claude-code"):
        """Register this MCP server as an available agent.

        Sends a capabilities_update to the gateway.
        After registration, users can send messages to this agent from the dashboard.

        Args:
            team_name: Claude Code team name (used by send-message for inbox injection)
            agent_name: Display name shown in the VoiceMode dashboard
            agent_platform: Platform identifier (default: claude-code)
        """
        self._available_team_name = team_name
        self._available_agent_name = agent_name
        self._available_agent_platform = agent_platform

        if self._ws and self._connected:
            await self._send_available_registration(self._ws)
        else:
            logger.info("Connect registry: available registration queued (will send on connect)")

    async def unregister_available(self):
        """Unregister this MCP server as an available agent.

        Sends a capabilities_update removing availability to the gateway.
        """
        self._available_team_name = None
        self._available_agent_name = None
        self._available_agent_platform = None

        if self._ws and self._connected:
            try:
                msg = {
                    "type": "capabilities_update",
                    "users": [],
                }
                await self._ws.send(json.dumps(msg))
                logger.info("Connect registry: unregistered as available")
            except Exception as e:
                logger.warning(f"Connect registry: failed to send unregistration: {e}")

    async def _send_available_registration(self, ws):
        """Send the available registration message over a WebSocket connection."""
        try:
            msg = {
                "type": "capabilities_update",
                "teamName": self._available_team_name,
                "platform": self._available_agent_platform or "claude-code",
            }
            await ws.send(json.dumps(msg))
            logger.info(
                f"Connect registry: registered as available "
                f"(agent: {self._available_agent_name}, team: {self._available_team_name})"
            )
        except Exception as e:
            logger.warning(f"Connect registry: failed to send available registration: {e}")

    def get_status_text(self) -> str:
        """Formatted status text for the service tool."""
        lines = ["VoiceMode Connect (voicemode.dev):"]

        status = self._status_message or ("Connected" if self._connected else "Not initialized")
        lines.append(f"  Status: {status}")

        if self._connected and self._devices:
            # Filter out our own MCP server connection
            remote_devices = [d for d in self._devices if d.platform != "mcp-server"]
            if remote_devices:
                lines.append("  Remote Devices:")
                for d in remote_devices:
                    ready_str = "ready" if d.ready else "not ready"
                    caps = d.capabilities_str()
                    activity = d.activity_ago()
                    platform_str = f" ({d.platform})" if d.platform else ""
                    lines.append(f"    {d.display_name()}{platform_str} - {ready_str}, {caps} - {activity}")
            else:
                lines.append("  Remote Devices: none")
        elif self._connected:
            lines.append("  Remote Devices: none")

        # Show available agent status
        if self._available_team_name:
            lines.append(f"  Available: {self._available_agent_name} (team: {self._available_team_name})")

        return "\n".join(lines)

    async def shutdown(self):
        """Cancel the background WebSocket task."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        self._devices = []
        self._initialized = False


# Global singleton
connect_registry = ConnectRegistry()
