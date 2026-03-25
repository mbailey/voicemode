"""
WebSocket gateway client for VoiceMode Connect channel integration.

Connects to the voicemode.dev WebSocket gateway, authenticates with Auth0
tokens, and listens for inbound voice events. When events arrive, pushes
them as Claude Code channel notifications via the MCP session.

This is the Python equivalent of voicemode-channel's gateway.ts.
"""

import asyncio
import json
import logging
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger("voicemode.channel.gateway")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WS_URL = os.getenv("VOICEMODE_CONNECT_WS_URL", "wss://voicemode.dev/ws")
AUTH0_DOMAIN = "dev-2q681p5hobd1dtmm.us.auth0.com"
AUTH0_CLIENT_ID = "1uJR1Q4HMkLkhzOXTg5JFuqBCq0FBsXK"
CREDENTIALS_FILE = Path.home() / ".voicemode" / "credentials"
TOKEN_EXPIRY_BUFFER_SECONDS = 60

HEARTBEAT_INTERVAL_S = 25
HEARTBEAT_LIVENESS_TIMEOUT_S = 60
INITIAL_RETRY_DELAY_S = 1
MAX_RETRY_DELAY_S = 60
MAX_TRANSCRIPT_LENGTH = 10000


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def _load_credentials() -> dict[str, Any] | None:
    """Load Auth0 credentials from ~/.voicemode/credentials."""
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
        if not data.get("access_token"):
            return None
        return data
    except Exception:
        return None


def _save_credentials(creds: dict[str, Any]) -> None:
    """Save credentials back to disk."""
    try:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))
        CREDENTIALS_FILE.chmod(0o600)
    except Exception:
        pass


def _is_expired(creds: dict[str, Any]) -> bool:
    """Check if access token is expired (with buffer)."""
    import time
    return time.time() >= (creds.get("expires_at", 0) - TOKEN_EXPIRY_BUFFER_SECONDS)


async def _refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    """Refresh the access token via Auth0."""
    import time
    import httpx

    token_url = f"https://{AUTH0_DOMAIN}/oauth/token"
    body = {
        "grant_type": "refresh_token",
        "client_id": AUTH0_CLIENT_ID,
        "refresh_token": refresh_token,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=body)
            if resp.status_code != 200:
                return None
            data = resp.json()
            expires_in = data.get("expires_in", 3600)
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": time.time() + expires_in,
                "token_type": data.get("token_type", "Bearer"),
            }
    except Exception:
        return None


async def _get_valid_token() -> str | None:
    """Get a valid (non-expired) access token, refreshing if necessary."""
    creds = _load_credentials()
    if not creds:
        logger.warning("No credentials found at ~/.voicemode/credentials")
        logger.warning("Run: voicemode connect auth login")
        return None

    if not _is_expired(creds):
        return creds["access_token"]

    logger.info("Access token expired, attempting refresh...")
    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        logger.warning("No refresh token available -- please re-login")
        return None

    refreshed = await _refresh_access_token(refresh_token)
    if not refreshed:
        logger.warning("Token refresh failed -- please re-login")
        return None

    # Preserve user_info from original credentials
    refreshed["user_info"] = creds.get("user_info")
    _save_credentials(refreshed)
    logger.info("Token refreshed successfully")
    return refreshed["access_token"]


# ---------------------------------------------------------------------------
# Project context helper
# ---------------------------------------------------------------------------

def _get_project_context() -> str | None:
    """Derive project context from the working directory."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            repo_name = Path(result.stdout.strip()).stem
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            return repo_name
    except Exception:
        pass
    return Path.cwd().name or None


# ---------------------------------------------------------------------------
# Gateway client
# ---------------------------------------------------------------------------

class ChannelGateway:
    """WebSocket gateway client for VoiceMode Connect.

    Connects to the gateway, authenticates, and dispatches inbound voice
    events to a callback function (which sends channel notifications).
    """

    def __init__(
        self,
        on_voice_event: Callable[[str, str, str | None], Awaitable[None]],
    ):
        """
        Args:
            on_voice_event: Async callback(caller, transcript, device_id)
                called when an inbound voice event arrives.
        """
        self._on_voice_event = on_voice_event
        self._ws: ClientConnection | None = None
        self._state = "disconnected"
        self._shutting_down = False
        self._task: asyncio.Task | None = None
        self._retry_delay = INITIAL_RETRY_DELAY_S
        self._agent_session_id = os.getenv("CLAUDE_SESSION_ID", "")

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> None:
        """Start the gateway connection loop as a background task."""
        if self._task and not self._task.done():
            logger.warning("Gateway already running")
            return
        self._shutting_down = False
        self._task = asyncio.create_task(self._connection_loop())
        logger.info("Gateway connection loop started")

    async def shutdown(self) -> None:
        """Cleanly shut down the gateway connection."""
        self._shutting_down = True
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._state = "disconnected"
        logger.info("Gateway shut down")

    async def _connection_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        while not self._shutting_down:
            try:
                await self._connect_once()
            except Exception as e:
                logger.error("Gateway connection error: %s", e)

            if self._shutting_down:
                break

            self._state = "reconnecting"
            logger.info("Reconnecting in %ds...", self._retry_delay)
            await asyncio.sleep(self._retry_delay)
            self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY_S)

    async def _connect_once(self) -> None:
        """Establish a single WebSocket connection and handle messages."""
        self._state = "connecting"

        token = await _get_valid_token()
        if not token:
            logger.warning("Cannot connect: no valid access token")
            return

        logger.info("Connecting to %s...", WS_URL)

        try:
            async with websockets.connect(
                WS_URL,
                additional_headers={"Authorization": f"Bearer {token}"},
                max_size=1_048_576,
            ) as ws:
                self._ws = ws
                logger.info("WebSocket connection opened")

                authenticated = False
                last_pong = asyncio.get_event_loop().time()

                # Start heartbeat task
                heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(ws, lambda: last_pong)
                )

                try:
                    async for raw_msg in ws:
                        msg_str = raw_msg if isinstance(raw_msg, str) else raw_msg.decode()

                        # Handle pong
                        if msg_str == "pong":
                            last_pong = asyncio.get_event_loop().time()
                            continue

                        try:
                            msg = json.loads(msg_str)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON from gateway")
                            continue

                        msg_type = msg.get("type")

                        if msg_type == "connected" and not authenticated:
                            authenticated = True
                            session_id = str(msg.get("sessionId", ""))[:12]
                            logger.info("Authenticated (session: %s)", session_id)

                            # Send ready + capabilities
                            await self._send_ready(ws)
                            await self._send_capabilities_update(ws)

                            # Reset backoff
                            self._retry_delay = INITIAL_RETRY_DELAY_S
                            self._state = "connected"

                        elif msg_type in ("heartbeat_ack", "heartbeat"):
                            last_pong = asyncio.get_event_loop().time()

                        elif msg_type == "error":
                            logger.error(
                                "Server error: %s (%s)",
                                msg.get("message", "Unknown"),
                                msg.get("code", ""),
                            )

                        elif msg_type == "user_message_delivery":
                            await self._handle_voice_event(msg)

                        elif msg_type in ("ack", "users", "devices"):
                            pass  # Silently ignore

                        else:
                            logger.debug("Ignoring message type: %s", msg_type)

                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            logger.error("WebSocket error: %s", e)
        finally:
            self._ws = None
            self._state = "disconnected"

    async def _handle_voice_event(self, msg: dict) -> None:
        """Process a user_message_delivery event."""
        text = msg.get("text", "")
        if not isinstance(text, str) or not text.strip():
            logger.warning("Dropping voice event: missing or empty text")
            return

        # Truncate long transcripts
        if len(text) > MAX_TRANSCRIPT_LENGTH:
            logger.warning("Truncating transcript from %d to %d chars", len(text), MAX_TRANSCRIPT_LENGTH)
            text = text[:MAX_TRANSCRIPT_LENGTH]

        # Determine caller identity
        from_field = msg.get("from", "")
        user_id = msg.get("userId", "")
        caller = from_field if from_field else (user_id if user_id else "unknown")
        device_id = user_id if user_id else None

        logger.info('Received voice event: from="%s" text="%s"', caller, text[:80])

        try:
            await self._on_voice_event(caller, text.strip(), device_id)
        except Exception as e:
            logger.error("Error pushing voice event to channel: %s", e)

    async def _send_ready(self, ws: ClientConnection) -> None:
        """Send ready message to gateway."""
        ready_msg = {
            "type": "ready",
            "device": {
                "platform": "channel-server",
                "appVersion": "0.1.0-python",
                "name": f"channel@{socket.gethostname()}",
            },
        }
        await ws.send(json.dumps(ready_msg))
        logger.info("Sent ready message")

    async def _send_capabilities_update(self, ws: ClientConnection) -> None:
        """Send capabilities_update to register as a callable agent."""
        agent_name = os.getenv("VOICEMODE_AGENT_NAME", "voicemode")
        display_name = os.getenv("VOICEMODE_AGENT_DISPLAY_NAME", "Claude Code")
        host = socket.gethostname()
        context = _get_project_context()

        caps_msg = {
            "type": "capabilities_update",
            "platform": "claude-code",
            "session_id": self._agent_session_id,
            "users": [{
                "name": agent_name,
                "host": host,
                "display_name": display_name,
                "presence": "available",
                **({"context": context} if context else {}),
            }],
        }
        await ws.send(json.dumps(caps_msg))
        logger.info(
            'Sent capabilities_update: agent="%s" display="%s" host="%s" context="%s"',
            agent_name, display_name, host, context,
        )

    async def _heartbeat_loop(
        self,
        ws: ClientConnection,
        get_last_pong: Callable[[], float],
    ) -> None:
        """Send periodic pings and check liveness."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            try:
                # Check liveness
                now = asyncio.get_event_loop().time()
                silent = now - get_last_pong()
                if silent > HEARTBEAT_LIVENESS_TIMEOUT_S:
                    logger.warning(
                        "No heartbeat response in %ds -- force-closing",
                        int(silent),
                    )
                    await ws.close()
                    return

                # Send ping (literal text, auto-responded by DO runtime)
                await ws.send("ping")
            except Exception:
                return

    def send_message(self, msg: dict) -> bool:
        """Send a message through the gateway (for reply tool)."""
        if not self._ws:
            return False
        try:
            asyncio.create_task(self._ws.send(json.dumps(msg)))
            return True
        except Exception:
            return False
