"""Presence management for VoiceMode Connect."""

from .types import Presence, UserInfo


def compute_presence(user: UserInfo, client_connected: bool) -> Presence:
    """Compute the presence state for a user.

    Available = client connected + user subscribed (inbox-live valid)
    Online = client connected + user exists but not subscribed
    Offline = client not connected
    """
    if not client_connected:
        return Presence.OFFLINE
    if user.subscribed_team:
        return Presence.AVAILABLE
    return Presence.ONLINE
