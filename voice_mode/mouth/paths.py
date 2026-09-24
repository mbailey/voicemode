"""The mouth's directory: ``$VOICEMODE_MOUTH_DIR``, else ``<VOICEMODE_BASE_DIR>/mouth``."""

from __future__ import annotations

import os
from pathlib import Path


def mouth_dir() -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_DIR")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("VOICEMODE_BASE_DIR") or "~/.voicemode"
    return Path(base).expanduser() / "mouth"
