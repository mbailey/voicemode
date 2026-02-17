"""VoiceMode Connect — remote messaging and presence."""

from .client import ConnectClient, get_client
from .messaging import deliver_message, read_inbox
from .types import ConnectState, Presence, UserInfo
from .users import UserManager

__all__ = [
    "ConnectClient",
    "ConnectState",
    "Presence",
    "UserInfo",
    "UserManager",
    "deliver_message",
    "get_client",
    "read_inbox",
]
