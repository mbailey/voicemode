"""Shared types for VoiceMode Connect."""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Optional


class Presence(Enum):
    """Entity presence state."""
    AVAILABLE = "available"    # Green — reachable and will respond
    ONLINE = "online"          # Amber — connected but not accepting messages
    OFFLINE = "offline"        # Grey — not connected


class ConnectState(Enum):
    """WebSocket connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class UserInfo:
    """A registered Connect user/mailbox."""
    name: str                                  # Mailbox name (e.g., "voicemode")
    display_name: str = ""                     # Human-readable (e.g., "Cora 7")
    host: str = ""                             # Host part of address
    presence: Presence = Presence.OFFLINE
    subscribed_team: Optional[str] = None      # Claude team name if subscribed
    created: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    @property
    def address(self) -> str:
        """Full mailbox@host address."""
        return f"{self.name}@{self.host}" if self.host else self.name


@dataclass
class InboxMessage:
    """A message in a user's inbox."""
    id: str
    sender: str                    # "user", "agent:cora", etc.
    text: str
    timestamp: datetime
    source: str = "dashboard"      # "dashboard", "api", "agent"
    delivered: bool = False         # Whether live delivery succeeded
