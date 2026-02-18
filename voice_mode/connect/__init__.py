"""VoiceMode Connect — remote messaging and presence."""

from .client import ConnectClient, get_client
from .messaging import deliver_message, read_inbox
from .types import ConnectState, Presence, UserInfo
from .users import UserManager
from .watcher import diff_user_state, watch_user_changes

__all__ = [
    "ConnectClient",
    "ConnectState",
    "Presence",
    "UserInfo",
    "UserManager",
    "deliver_message",
    "diff_user_state",
    "get_client",
    "read_inbox",
    "watch_user_changes",
]
