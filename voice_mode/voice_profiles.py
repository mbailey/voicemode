"""Voice profiles for clone-based TTS.

Voices come from two sources, layered:

1. **Directory-based** (preferred):
   ``$VOICEMODE_VOICES_DIR`` (default ``~/.voicemode/voices``).
   Each subdirectory is a voice. For ``<name>/`` we look for a
   ``default.wav`` (or the first ``*.wav``) plus a sidecar transcript
   ``default.txt`` (or matching basename). SuperDirt-style: drop a folder
   in, you get a voice. Symlink ``default.wav`` to swap which sample is
   active without renaming files.

2. **JSON-based** (legacy):
   ``~/.voicemode/voices.json``. Loaded after the directory; entries that
   already exist as directory profiles are not overridden, so dir wins.

Each profile maps a voice name to a reference audio file and transcript
on the TTS server, plus model and endpoint routing info.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("voicemode")

PROFILES_JSON = Path(os.path.expanduser("~/.voicemode/voices.json"))
VOICES_DIR = Path(os.path.expanduser(
    os.environ.get("VOICEMODE_VOICES_DIR", "~/.voicemode/voices")
))

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


def _resolve_default_wav(voice_dir: Path) -> Optional[Path]:
    """Pick the reference WAV inside a voice directory.

    Order of preference:
    1. ``default.wav`` (file or symlink) — the explicit default
    2. The single ``*.wav`` if there's only one — unambiguous

    Directories with multiple WAVs and no ``default.wav`` are treated as
    sample bins, not voices, and skipped. Add a ``default.wav`` symlink
    if you want such a directory to register as a voice.
    """
    default = voice_dir / "default.wav"
    if default.exists():
        return default

    wavs = sorted(voice_dir.glob("*.wav"))
    if not wavs:
        return None
    if len(wavs) == 1:
        return wavs[0]

    logger.debug(
        f"Skipping {voice_dir.name!r}: {len(wavs)} WAVs and no default.wav "
        f"(treat as a sample bin, not a voice; add default.wav symlink to "
        f"register)."
    )
    return None


def _resolve_transcript(wav_path: Path) -> str:
    """Read the matching transcript for a reference WAV.

    Looks for ``<basename>.txt`` first, then ``default.txt`` as a fallback.
    Returns empty string if no transcript is found (caller will warn).
    """
    same_name = wav_path.with_suffix(".txt")
    if same_name.exists():
        return same_name.read_text().strip()

    fallback = wav_path.parent / "default.txt"
    if fallback.exists():
        return fallback.read_text().strip()

    return ""


def _load_dir_profiles() -> Dict[str, VoiceProfile]:
    """Walk VOICES_DIR and build profiles from per-voice subdirectories."""
    profiles: Dict[str, VoiceProfile] = {}

    if not VOICES_DIR.exists() or not VOICES_DIR.is_dir():
        logger.debug(f"Voices directory not found at {VOICES_DIR}")
        return profiles

    for voice_dir in sorted(p for p in VOICES_DIR.iterdir() if p.is_dir()):
        wav = _resolve_default_wav(voice_dir)
        if wav is None:
            logger.debug(f"Skipping {voice_dir.name!r}: no .wav files")
            continue

        transcript = _resolve_transcript(wav)
        if not transcript:
            logger.warning(
                f"Voice {voice_dir.name!r}: no transcript found "
                f"(expected {wav.with_suffix('.txt').name} or default.txt). "
                f"ref_text will be empty."
            )

        profiles[voice_dir.name] = VoiceProfile(
            name=voice_dir.name,
            ref_audio=str(wav.resolve()),
            ref_text=transcript,
            model=DEFAULT_CLONE_MODEL,
            base_url=DEFAULT_CLONE_BASE_URL,
            description="",
        )

    if profiles:
        logger.info(
            f"Loaded {len(profiles)} dir profiles from {VOICES_DIR}: "
            f"{list(profiles.keys())}"
        )
    return profiles


def _load_json_profiles() -> Dict[str, VoiceProfile]:
    """Load profiles from the legacy voices.json registry."""
    profiles: Dict[str, VoiceProfile] = {}

    if not PROFILES_JSON.exists():
        logger.debug(f"No voice profiles file at {PROFILES_JSON}")
        return profiles

    try:
        with open(PROFILES_JSON) as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load voice profiles JSON: {e}")
        return profiles

    for name, pd in data.get("voices", {}).items():
        profiles[name] = VoiceProfile(
            name=name,
            ref_audio=pd["ref_audio"],
            ref_text=pd["ref_text"],
            model=pd.get("model", DEFAULT_CLONE_MODEL),
            base_url=pd.get("base_url", DEFAULT_CLONE_BASE_URL),
            description=pd.get("description", ""),
        )

    if profiles:
        logger.info(
            f"Loaded {len(profiles)} JSON profiles from {PROFILES_JSON}: "
            f"{list(profiles.keys())}"
        )
    return profiles


def load_profiles() -> Dict[str, VoiceProfile]:
    """Load voice profiles from both directory and JSON sources.

    Directory takes precedence — JSON only fills in voices not already
    defined by a directory profile.
    """
    global _profiles, _loaded

    dir_profiles = _load_dir_profiles()
    json_profiles = _load_json_profiles()

    # Layer JSON on top of dir, but only for keys dir didn't define
    merged = dict(dir_profiles)
    for name, prof in json_profiles.items():
        merged.setdefault(name, prof)

    _profiles = merged
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


def reload_profiles() -> Dict[str, VoiceProfile]:
    """Force a reload of voice profiles (clears the cache)."""
    global _loaded
    _loaded = False
    return load_profiles()
