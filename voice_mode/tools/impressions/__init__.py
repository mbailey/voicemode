"""Impressions voice profile CRUD tools.

Voice profile management (add/list/remove) for the impressions feature
(formerly "clone"). The underlying TTS *service* is mlx-audio -- see
:mod:`voice_mode.tools.mlx_audio` for service install/uninstall/status.

Function names ``clone_add`` / ``clone_list`` / ``clone_remove`` are
preserved for now; they describe the underlying mechanical operation.
A function-rename is out of scope for VM-1174.
"""

from voice_mode.tools.impressions.profiles import clone_add, clone_list, clone_remove

__all__ = [
    "clone_add",
    "clone_list",
    "clone_remove",
]
