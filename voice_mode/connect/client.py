"""WebSocket client for VoiceMode Connect gateway.

Maintains a persistent connection to the Connect gateway (voicemode.dev)
with auto-reconnect, heartbeat, and message routing to user inboxes.

Replaces the monolithic connect_registry.py with a client that uses
the modular connect subsystem (types, config, users, messaging).
"""

import asyncio
import json
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from . import config as connect_config
from .messaging import deliver_message
from .types import ConnectState
from .users import UserManager

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


class ConnectClient:
    """WebSocket client for VoiceMode Connect gateway.

    Manages the WebSocket lifecycle (auth, connect, heartbeat, receive)
    with auto-reconnect and exponential backoff. Routes incoming messages
    to user inboxes via the messaging module.
    """

    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager
        self.state = ConnectState.DISCONNECTED
        self._ws = None
        self._session_id: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._devices: list[DeviceInfo] = []
        self._status_message: Optional[str] = None
        self._reconnect_count = 0
        self._primary_user = None  # User registered by THIS process

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectState.CONNECTED

    @property
    def is_connecting(self) -> bool:
        return self.state == ConnectState.CONNECTING

    @property
    def devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    @property
    def status_message(self) -> str:
        return self._status_message or (
            "Connected" if self.is_connected else "Not initialized"
        )

    async def connect(self) -> None:
        """Start background connection task.

        Idempotent — safe to call multiple times. Checks config and
        credentials before attempting to connect.
        """
        if self._task is not None and not self._task.done():
            return

        if not connect_config.is_enabled():
            self._status_message = "Disabled (VOICEMODE_CONNECT_ENABLED=false)"
            logger.debug("Connect client disabled by config")
            return

        # Check credentials (synchronous call, run in thread)
        try:
            from voice_mode.auth import get_valid_credentials

            creds = await asyncio.to_thread(get_valid_credentials, auto_refresh=True)
        except Exception as e:
            self._status_message = f"Auth error: {e}"
            logger.warning(f"Connect client: could not load credentials: {e}")
            return

        if creds is None:
            self._status_message = (
                "Not connected (no credentials - run: voicemode connect login)"
            )
            logger.debug("Connect client: no credentials available")
            return

        self._task = asyncio.create_task(self._connection_loop())

    async def disconnect(self) -> None:
        """Cancel background task and close WebSocket."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state = ConnectState.DISCONNECTED
        self._devices = []
        self._ws = None
        self._status_message = "Disconnected"

    async def register_user(self, user) -> None:
        """Register a user with the gateway via capabilities_update."""
        self._primary_user = user  # Track user registered by THIS process
        if self._ws and self.is_connected:
            await self.send_capabilities_update()
        else:
            logger.info("Connect client: user registration queued (will send on connect)")

    async def unregister_user(self, name: str) -> None:
        """Unregister a user from the gateway."""
        if self._ws and self.is_connected:
            users = self.user_manager.list()
            if users:
                await self.send_capabilities_update()
            else:
                try:
                    msg = {
                        "type": "capabilities_update",
                        "users": [],
                    }
                    await self._ws.send(json.dumps(msg))
                    logger.info("Connect client: all users unregistered")
                except Exception as e:
                    logger.warning(f"Connect client: failed to send unregistration: {e}")

    async def send_capabilities_update(self) -> None:
        """Send capabilities_update to the gateway.

        Scoped to this process's primary user when set (MCP server mode).
        Falls back to preconfigured users, then all users (standalone connect up).
        """
        if not self._ws or not self.is_connected:
            return

        # Scope to this agent's user(s)
        if self._primary_user:
            user = self.user_manager.get(self._primary_user.name)
            users = [user] if user else []
        else:
            # Preconfigured users from env, or all users for standalone process
            configured = connect_config.get_preconfigured_users()
            if configured:
                users = [u for name in configured if (u := self.user_manager.get(name))]
            else:
                users = self.user_manager.list()

        # Build user list for the new protocol
        user_entries = []
        for user in users:
            presence = self.user_manager.get_presence(user.name)
            user_entries.append({
                "name": user.name,
                "host": user.host,
                "display_name": user.display_name,
                "presence": presence.value,
            })

        msg = {
            "type": "capabilities_update",
            "users": user_entries,
            "platform": "claude-code",
        }

        try:
            await self._ws.send(json.dumps(msg))
            logger.info(
                f"Connect client: capabilities_update sent "
                f"({len(user_entries)} user(s))"
            )
        except Exception as e:
            logger.warning(f"Connect client: failed to send capabilities_update: {e}")

    async def _connection_loop(self):
        """Main WebSocket connection loop with auto-reconnect."""
        try:
            import websockets
        except ImportError:
            self._status_message = "websockets package not installed"
            logger.error("Connect client: websockets package not available")
            return

        retry_delay = 1
        max_retry_delay = 60

        while True:
            try:
                # Get fresh credentials for each connection attempt
                from voice_mode.auth import get_valid_credentials

                self.state = ConnectState.CONNECTING
                creds = await asyncio.to_thread(
                    get_valid_credentials, auto_refresh=True
                )
                if creds is None:
                    self._status_message = "Not connected (credentials expired)"
                    self.state = ConnectState.DISCONNECTED
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue

                # Build WebSocket URL with auth token
                ws_url = connect_config.get_ws_url()
                token = urllib.parse.quote(creds.access_token)
                separator = "&" if "?" in ws_url else "?"
                ws_url = f"{ws_url}{separator}token={token}"

                self._status_message = "Connecting..."

                async with websockets.connect(ws_url) as ws:
                    self._ws = ws
                    self.state = ConnectState.CONNECTED
                    retry_delay = 1
                    self._reconnect_count = 0

                    # Wait for 'connected' message
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if msg.get("type") == "connected":
                        self._session_id = msg.get("sessionId", "")[:12]
                        self._status_message = "Connected"
                        logger.info(
                            f"Connect client: connected (session: {self._session_id})"
                        )
                    else:
                        logger.warning(
                            f"Connect client: unexpected first message: {msg.get('type')}"
                        )

                    # Send ready message
                    from voice_mode.version import __version__

                    ready_msg = {
                        "type": "ready",
                        "device": {
                            "platform": "mcp-server",
                            "appVersion": __version__,
                            "deviceId": connect_config.get_device_id(),
                            "name": connect_config.get_device_name(),
                        },
                        "capabilities": {
                            "tts": True,
                            "stt": True,
                        },
                    }
                    await ws.send(json.dumps(ready_msg))

                    # Re-register users if any are registered
                    users = self.user_manager.list()
                    if users:
                        await self.send_capabilities_update()

                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

                    try:
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                                await self._handle_message(msg)
                            except json.JSONDecodeError:
                                logger.warning(
                                    f"Connect client: invalid JSON: {raw[:100]}"
                                )
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.info("Connect client: shutting down")
                self.state = ConnectState.DISCONNECTED
                self._ws = None
                self._status_message = "Shut down"
                return
            except Exception as e:
                self.state = ConnectState.RECONNECTING
                self._ws = None
                self._devices = []
                self._reconnect_count += 1
                self._status_message = (
                    f"Reconnecting (attempt {self._reconnect_count})"
                )
                logger.debug(
                    f"Connect client: connection error: {e}, retrying in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _heartbeat_loop(self, ws):
        """Send periodic heartbeats to keep the connection alive."""
        while True:
            await asyncio.sleep(25)
            try:
                await ws.send(
                    json.dumps({
                        "type": "heartbeat",
                        "timestamp": int(time.time() * 1000),
                    })
                )
            except Exception:
                return  # Connection closed

    async def _handle_message(self, msg: dict):
        """Handle a message from the WebSocket server."""
        msg_type = msg.get("type")

        if msg_type == "devices":
            devices = msg.get("devices", [])
            self._devices = [
                DeviceInfo.from_connection_info(d) for d in devices
            ]
            logger.debug(
                f"Connect client: {len(self._devices)} device(s) connected"
            )

        elif msg_type in ("heartbeat_ack", "heartbeat"):
            pass

        elif msg_type == "error":
            error_msg = msg.get("message", "Unknown error")
            error_code = msg.get("code", "")
            logger.warning(
                f"Connect client: server error: {error_msg} ({error_code})"
            )

        elif msg_type == "ack":
            pass

        elif msg_type == "user_message_delivery":
            await self._handle_user_message_delivery(msg)

        else:
            logger.debug(f"Connect client: unhandled message type: {msg_type}")

    async def _handle_user_message_delivery(self, data: dict):
        """Route incoming user_message_delivery to correct user inbox."""
        text = data.get("text", "")
        sender = data.get("from", "user")
        target_user = data.get("target_user", "")

        if not text.strip():
            logger.warning("Connect client: received empty user_message_delivery, ignoring")
            return

        # Find the target user by name, then by display_name as fallback
        user = None
        if target_user:
            user = self.user_manager.get(target_user)
            if not user:
                # Try matching by display_name (gateway may send display name)
                for u in self.user_manager.list():
                    if u.display_name == target_user:
                        user = u
                        break
        if not user:
            # Fall back to first registered user
            users = self.user_manager.list()
            user = users[0] if users else None

        if not user:
            logger.warning(f"Connect client: no user found for message target: {target_user}")
            return

        user_dir = self.user_manager._user_dir(user.name)
        result = deliver_message(user_dir, text, sender=sender, source="gateway")
        logger.info(
            f"Connect client: delivered message to {user.name} from {sender}"
        )

        # Send delivery confirmation back to the gateway (routes to sender)
        if self._ws and result.get("delivered"):
            try:
                await self._ws.send(json.dumps({
                    "type": "delivery_confirmation",
                    "message_id": result["id"],
                    "target_user": sender,
                    "delivered": True,
                }))
            except Exception as e:
                logger.warning(f"Connect client: failed to send delivery confirmation: {e}")

    def get_status_text(self) -> str:
        """Formatted status text for the service tool."""
        lines = ["VoiceMode Connect (voicemode.dev):"]

        status = self._status_message or (
            "Connected" if self.is_connected else "Not initialized"
        )
        lines.append(f"  Status: {status}")

        if self.is_connected and self._devices:
            remote_devices = [
                d for d in self._devices if d.platform != "mcp-server"
            ]
            if remote_devices:
                lines.append("  Remote Devices:")
                for d in remote_devices:
                    ready_str = "ready" if d.ready else "not ready"
                    caps = d.capabilities_str()
                    activity = d.activity_ago()
                    platform_str = f" ({d.platform})" if d.platform else ""
                    lines.append(
                        f"    {d.display_name()}{platform_str}"
                        f" - {ready_str}, {caps} - {activity}"
                    )
            else:
                lines.append("  Remote Devices: none")
        elif self.is_connected:
            lines.append("  Remote Devices: none")

        # Show registered users
        users = self.user_manager.list()
        if users:
            for user in users:
                presence = self.user_manager.get_presence(user.name)
                lines.append(
                    f"  User: {user.display_name or user.name} "
                    f"({presence.value})"
                )

        return "\n".join(lines)


# Singleton
_client: Optional[ConnectClient] = None


def get_client() -> ConnectClient:
    """Get or create the singleton ConnectClient."""
    global _client
    if _client is None:
        host = connect_config.get_host()
        user_manager = UserManager(host)
        _client = ConnectClient(user_manager)
    return _client
