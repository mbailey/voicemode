"""The mouth's default voice, and the voices it can speak.

Mike, voice 03:14 Sat 2026-09-26, in the Settings webxdc: "click on the
voice and then select a different voice. I'm assuming this is the default
voice, if a voice isn't specified."

A line's voice is the first of these that answers:

1. the line's own: ``say --voice``, or a mail's ``X-Mouth-Voice``;
2. ``voice`` in the settings file, which the phone's Settings app writes:
   ``$VOICEMODE_MOUTH_SETTINGS``, else ``<mouth dir>/settings.json``;
3. ``$VOICEMODE_MOUTH_VOICE``;
4. ``af_sky``, the founding voice (``~/.voicemode/voices/FAVORITES.md``).

The file is read for every line, so a pick applies to the next line queued.
A missing or unreadable file is not an error: it just doesn't answer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .paths import mouth_dir

BUILTIN = "af_sky"

# Kokoro-82M v1.0's English voices: what the mlx-audio service on 8890
# speaks. It has no /audio/voices to ask, so the list lives here.
KOKORO = [
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole",
    "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
    "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]


def settings_path(d: Optional[Path] = None) -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_SETTINGS")
    return Path(env).expanduser() if env else (d or mouth_dir()) / "settings.json"


def settings(d: Optional[Path] = None) -> dict:
    try:
        s = json.loads(settings_path(d).read_text())
    except (OSError, ValueError):
        return {}
    return s if isinstance(s, dict) else {}


def default_voice(d: Optional[Path] = None) -> tuple[str, str]:
    """(voice, where it came from: 'settings' | 'env' | 'builtin')."""
    v = settings(d).get("voice")
    if isinstance(v, str) and v.strip():
        return v.strip(), "settings"
    v = os.environ.get("VOICEMODE_MOUTH_VOICE", "").strip()
    if v:
        return v, "env"
    return BUILTIN, "builtin"


def clones() -> list[str]:
    """The clone voices under ~/.voicemode/voices, as converse resolves them."""
    from voice_mode.voice_profiles import load_profiles

    return sorted(load_profiles())


def voices(d: Optional[Path] = None) -> dict:
    """What `mouth voices` prints: the default, where it came from, and every voice."""
    v, src = default_voice(d)
    return {"default": v, "from": src, "settings": str(settings_path(d)),
            "kokoro": list(KOKORO), "clone": clones()}
