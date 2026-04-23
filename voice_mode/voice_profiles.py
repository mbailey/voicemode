"""Voice profiles for clone-based TTS.

Loads voice profiles from ~/.voicemode/voices.json. Each profile maps a voice
name to a reference audio file and transcript on the TTS server, plus model
and endpoint routing info.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("voicemode")

PROFILES_PATH = Path(os.path.expanduser("~/.voicemode/voices.json"))

# Default mlx-audio endpoint (Qwen3-TTS on ms2)
DEFAULT_CLONE_BASE_URL = "http://ms2:8890/v1"
DEFAULT_CLONE_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


@dataclass
class VoiceProfile:
    """A voice cloning profile."""
    name: str
    ref_audio: str       # Path to reference audio on TTS server
    ref_text: str        # Transcript of reference audio
    model: str           # TTS model to use
    base_url: str        # TTS endpoint URL
    description: str = ""


_profiles: Dict[str, VoiceProfile] = {}
_loaded = False


def load_profiles() -> Dict[str, VoiceProfile]:
    """Load voice profiles from disk."""
    global _profiles, _loaded

    if not PROFILES_PATH.exists():
        logger.debug(f"No voice profiles file at {PROFILES_PATH}")
        _loaded = True
        return _profiles

    try:
        with open(PROFILES_PATH) as f:
            data = json.load(f)

        _profiles = {}
        for name, profile_data in data.get("voices", {}).items():
            _profiles[name] = VoiceProfile(
                name=name,
                ref_audio=profile_data["ref_audio"],
                ref_text=profile_data["ref_text"],
                model=profile_data.get("model", DEFAULT_CLONE_MODEL),
                base_url=profile_data.get("base_url", DEFAULT_CLONE_BASE_URL),
                description=profile_data.get("description", ""),
            )
        _loaded = True
        logger.info(f"Loaded {len(_profiles)} voice profiles: {list(_profiles.keys())}")
    except Exception as e:
        logger.error(f"Failed to load voice profiles: {e}")
        _loaded = True

    return _profiles


def get_profile(voice_name: str) -> Optional[VoiceProfile]:
    """Get a voice profile by name. Returns None if not a clone voice."""
    if not _loaded:
        load_profiles()
    return _profiles.get(voice_name)


def is_clone_voice(voice_name: str) -> bool:
    """Check if a voice name refers to a clone profile."""
    if not _loaded:
        load_profiles()
    return voice_name in _profiles


def list_profiles() -> Dict[str, VoiceProfile]:
    """List all available voice profiles."""
    if not _loaded:
        load_profiles()
    return _profiles
