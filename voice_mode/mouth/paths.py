"""The mouth's directory: ``$VOICEMODE_MOUTH_DIR``, else ``<VOICEMODE_BASE_DIR>/mouth``."""

from __future__ import annotations

import os
from pathlib import Path


def default_mouth_dir() -> Path:
    """``<VOICEMODE_BASE_DIR>/mouth``: the live mouth's, whatever $VOICEMODE_MOUTH_DIR says."""
    base = os.environ.get("VOICEMODE_BASE_DIR") or "~/.voicemode"
    return Path(base).expanduser() / "mouth"


def mouth_dir() -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_DIR")
    if env:
        return Path(env).expanduser()
    return default_mouth_dir()
