"""Voice profiles for clone-based TTS.

Voices live in ``$VOICEMODE_VOICES_DIR`` (default ``~/.voicemode/voices``).
Each subdirectory is a voice profile. For ``<name>/`` we look for a
``default.wav`` (or the first ``*.wav``) plus a sidecar transcript
``default.txt`` (or matching basename). SuperDirt-style: drop a folder in,
you get a voice. Symlink ``default.wav`` to swap which sample is active
without renaming files.

Each profile maps a voice name to a reference audio file and transcript,
plus model and endpoint routing info.

Voice expression syntax (``voice="<expr>"`` at converse time):

* ``samantha``           — the voice's ``default.wav``
* ``samantha[0]``        — the first ``*.wav`` in the dir (sorted)
* ``samantha[2]``        — the third ``*.wav`` (SuperDirt-style indexing)
* ``samantha/angry.wav`` — an explicit file inside the voice dir
* ``/abs/path.wav``      — absolute path passed straight to the TTS server

Remote TTS servers (e.g. mlx-audio on ms2) need the ref_audio path that
exists on *their* filesystem, not ours. Set ``VOICEMODE_REMOTE_VOICES_DIR``
to the path where the voices directory is mirrored on the TTS host; we
rewrite the prefix when sending the request. If unset, the local
absolute path is sent (only useful when the TTS server runs locally).
"""

import logging
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("voicemode")

VOICES_DIR = Path(os.path.expanduser(
    os.environ.get("VOICEMODE_VOICES_DIR", "~/.voicemode/voices")
))

# Path on the remote TTS server where VOICES_DIR is mirrored. When set,
# ref_audio paths sent to the server are rewritten with this prefix so
# the server can find the file on its own filesystem.
REMOTE_VOICES_DIR = os.environ.get("VOICEMODE_REMOTE_VOICES_DIR", "")

# Default mlx-audio endpoint for clone voices (Qwen3-TTS).
# Defaults to a local mlx-audio server. Override via env vars when you
# want to point at a different host (e.g. a remote ms2 box on the LAN).
DEFAULT_CLONE_BASE_URL = os.environ.get(
    "VOICEMODE_CLONE_BASE_URL", "http://127.0.0.1:8890/v1"
)
DEFAULT_CLONE_MODEL = os.environ.get(
    "VOICEMODE_CLONE_MODEL", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
)

# Matches ``name[0]``, ``name[12]``. Captures (name, index).
_INDEX_RE = re.compile(r"^([^/\[\]]+)\[(\d+)\]$")


@dataclass
class VoiceProfile:
    """A voice cloning profile."""
    name: str
    ref_audio: str       # Absolute path to reference audio (server-side)
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


def _read_description(voice_dir: Path) -> str:
    """Read the optional ``description.txt`` sidecar."""
    desc_path = voice_dir / "description.txt"
    if desc_path.exists():
        return desc_path.read_text().strip()
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
            ref_audio=_translate_path(wav),
            ref_text=transcript,
            model=DEFAULT_CLONE_MODEL,
            base_url=DEFAULT_CLONE_BASE_URL,
            description=_read_description(voice_dir),
        )

    if profiles:
        logger.info(
            f"Loaded {len(profiles)} voice profiles from {VOICES_DIR}: "
            f"{list(profiles.keys())}"
        )
    return profiles


def load_profiles() -> Dict[str, VoiceProfile]:
    """Load voice profiles by scanning VOICES_DIR."""
    global _profiles, _loaded
    _profiles = _load_dir_profiles()
    _loaded = True
    return _profiles


def parse_voice_expr(expr: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a voice expression into ``(voice_name, selector)``.

    Selector is either ``None`` (use default), a string like ``"[N]"``
    (indexed sample), or a relative file path inside the voice dir
    (e.g. ``"angry.wav"``). For absolute paths the voice_name is ``None``
    and the selector is the absolute path itself.

    Examples::

        parse_voice_expr("samantha")           == ("samantha", None)
        parse_voice_expr("samantha[0]")        == ("samantha", "[0]")
        parse_voice_expr("samantha/angry.wav") == ("samantha", "angry.wav")
        parse_voice_expr("/abs/path.wav")      == (None, "/abs/path.wav")
    """
    if not expr:
        return None, None
    if expr.startswith("/"):
        return None, expr

    m = _INDEX_RE.match(expr)
    if m:
        return m.group(1), f"[{m.group(2)}]"

    if "/" in expr:
        head, _, tail = expr.partition("/")
        return head, tail

    return expr, None


def _list_samples(voice_dir: Path) -> List[Path]:
    """Sorted list of ``*.wav`` files inside a voice directory."""
    return sorted(voice_dir.glob("*.wav"))


def _translate_path(local_path: Path) -> str:
    """Translate a local voices-dir path into the path the TTS server sees.

    If ``VOICEMODE_REMOTE_VOICES_DIR`` is set and ``local_path`` lives
    under ``VOICES_DIR``, replace the prefix. Otherwise return the local
    absolute path (correct when the TTS server is the local machine).
    """
    abs_local = local_path.resolve() if local_path.exists() else local_path
    if not REMOTE_VOICES_DIR:
        return str(abs_local)

    try:
        rel = abs_local.relative_to(VOICES_DIR.resolve())
    except ValueError:
        # Path isn't under VOICES_DIR — pass through untranslated
        return str(abs_local)

    return str(Path(REMOTE_VOICES_DIR) / rel)


def resolve_voice_expr(expr: str) -> Optional[VoiceProfile]:
    """Resolve a voice expression to a fully-populated ``VoiceProfile``.

    Returns a profile whose ``ref_audio`` is the path the TTS server
    should look up, and whose ``ref_text`` matches the chosen sample.
    Returns ``None`` if the expression doesn't refer to a clone voice.

    For the absolute-path escape hatch (``"/abs/path.wav"``), returns a
    minimal profile with the path passed through and an empty
    ``ref_text`` (caller may not have a transcript for arbitrary files).
    """
    if not _loaded:
        load_profiles()

    name, selector = parse_voice_expr(expr)

    # Absolute-path escape hatch: no profile lookup, no transcript.
    if name is None and selector and selector.startswith("/"):
        return VoiceProfile(
            name=expr,
            ref_audio=selector,
            ref_text="",
            model=DEFAULT_CLONE_MODEL,
            base_url=DEFAULT_CLONE_BASE_URL,
            description="(absolute path)",
        )

    if not name:
        return None

    profile = _profiles.get(name)
    if profile is None:
        return None

    # Bare name → use the profile as-is (already pointing at default.wav).
    if selector is None:
        return profile

    voice_dir = VOICES_DIR / name

    # Indexed sample: samantha[0]
    if selector.startswith("[") and selector.endswith("]"):
        try:
            idx = int(selector[1:-1])
        except ValueError:
            logger.error(f"Bad sample index in voice expr {expr!r}")
            return profile
        samples = _list_samples(voice_dir)
        if not samples:
            logger.warning(f"Voice {name!r}: no .wav samples for indexing")
            return profile
        if idx < 0 or idx >= len(samples):
            logger.error(
                f"Sample index {idx} out of range for {name!r} "
                f"({len(samples)} samples available)"
            )
            return profile
        wav = samples[idx]
        return replace(
            profile,
            ref_audio=_translate_path(wav),
            ref_text=_resolve_transcript(wav),
        )

    # Explicit relative file: samantha/angry.wav
    wav = voice_dir / selector
    if not wav.exists():
        logger.warning(
            f"Voice expr {expr!r}: {wav} does not exist locally — "
            f"sending path to server anyway in case it's mirrored."
        )
    return replace(
        profile,
        ref_audio=_translate_path(wav),
        ref_text=_resolve_transcript(wav) if wav.exists() else "",
    )


def get_profile(voice_expr: str) -> Optional[VoiceProfile]:
    """Get a voice profile resolved from a voice expression.

    Equivalent to :func:`resolve_voice_expr` — kept under the original
    name for back-compat with existing callers.
    """
    return resolve_voice_expr(voice_expr)


def is_clone_voice(voice_expr: str) -> bool:
    """Check if a voice expression refers to a clone profile.

    Recognises the selector syntax: ``samantha[0]`` and
    ``samantha/angry.wav`` are both clone voices if ``samantha`` is.
    Absolute paths always count as clone voices.
    """
    if not _loaded:
        load_profiles()
    if not voice_expr:
        return False
    name, selector = parse_voice_expr(voice_expr)
    if name is None and selector and selector.startswith("/"):
        return True
    return name in _profiles


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
