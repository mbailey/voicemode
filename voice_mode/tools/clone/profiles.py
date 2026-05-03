"""Voice profile CRUD operations for clone-based TTS.

Manages voice profiles in ~/.voicemode/voices.json. Each profile maps a voice
name to a reference audio file and transcript, used by the clone TTS service.

This module handles writes (add/remove). The read-only voice_profiles.py module
on the cora/clone-voices branch handles loading and lookup.
"""

import json
import logging
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from voice_mode.config import BASE_DIR, CLONE_MODEL

logger = logging.getLogger("voicemode")

VOICES_DIR = BASE_DIR / "voices"
VOICES_JSON = BASE_DIR / "voices.json"

MIN_CLIP_SECONDS = 3.0
MAX_CLIP_SECONDS = 9.0
TRIM_HINT = "ffmpeg -i in.wav -ss 0 -t 8 out.wav"

# Default clone TTS settings
DEFAULT_CLONE_BASE_URL = "http://ms2:8890/v1"
DEFAULT_CLONE_MODEL = CLONE_MODEL

# Whisper STT endpoint for auto-transcription
WHISPER_STT_URL = "http://localhost:2022/v1/audio/transcriptions"


def _load_voices_json() -> Dict[str, Any]:
    """Load voices.json, returning empty structure if missing."""
    if not VOICES_JSON.exists():
        return {"voices": {}}
    try:
        with open(VOICES_JSON) as f:
            data = json.load(f)
        if "voices" not in data:
            data["voices"] = {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read {VOICES_JSON}: {e}")
        return {"voices": {}}


def _save_voices_json(data: Dict[str, Any]) -> None:
    """Write voices.json atomically (write to tmp then rename)."""
    VOICES_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = VOICES_JSON.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        tmp_path.replace(VOICES_JSON)
    except OSError:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise


def _transcribe_audio(audio_path: Path) -> str:
    """Transcribe audio via the local Whisper STT endpoint.

    Posts the audio file as multipart/form-data to the Whisper service
    at http://localhost:2022/v1/audio/transcriptions.

    Args:
        audio_path: Path to the audio file to transcribe.

    Returns:
        Transcribed text.

    Raises:
        ConnectionError: If the Whisper service is not reachable.
        RuntimeError: If transcription fails.
    """
    import mimetypes
    import uuid

    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"

    # Build multipart/form-data body
    body_parts = []

    # File field
    body_parts.append(f"--{boundary}".encode())
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"'.encode()
    )
    body_parts.append(f"Content-Type: {content_type}".encode())
    body_parts.append(b"")
    body_parts.append(audio_path.read_bytes())

    # Model field
    body_parts.append(f"--{boundary}".encode())
    body_parts.append(b'Content-Disposition: form-data; name="model"')
    body_parts.append(b"")
    body_parts.append(b"whisper-1")

    # Closing boundary
    body_parts.append(f"--{boundary}--".encode())
    body_parts.append(b"")

    body = b"\r\n".join(body_parts)

    req = urllib.request.Request(
        WHISPER_STT_URL,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            text = result.get("text", "").strip()
            if not text:
                raise RuntimeError("Whisper returned empty transcription")
            return text
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Cannot reach Whisper STT at {WHISPER_STT_URL}. "
            f"Is the Whisper service running? Error: {e}"
        ) from e
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Invalid response from Whisper STT: {e}") from e


def _probe_duration_seconds(path: Path) -> float:
    """Return the duration of an audio file in seconds.

    Uses ffprobe when available. Falls back to ``wave`` for WAV inputs when
    ffprobe is missing. For non-WAV inputs without ffprobe, raises RuntimeError.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except FileNotFoundError:
        if path.suffix.lower() != ".wav":
            raise RuntimeError(
                "ffmpeg/ffprobe required for non-WAV inputs "
                "(install via: brew install ffmpeg)"
            )
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0:
                raise RuntimeError(f"Invalid sample rate in WAV: {path}")
            return frames / float(rate)
    except (subprocess.CalledProcessError, ValueError) as e:
        raise RuntimeError(f"Failed to probe duration of {path}: {e}") from e


def _normalise_audio(src: Path, dest: Path) -> None:
    """Normalise ``src`` to mono 24 kHz 16-bit PCM with loudnorm at ``dest``.

    Shells out to ffmpeg with the voice-lab clip-prep spec:
    ``-ac 1 -ar 24000 -sample_fmt s16 -af loudnorm=I=-16:TP=-1.5:LRA=11``.
    Single-pass loudnorm; matches the upstream voice-lab pipeline.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-sample_fmt",
        "s16",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(dest),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "ffmpeg required for clone add (install via: brew install ffmpeg)"
        ) from e

    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-20:])
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode}) while normalising {src}:\n{tail}"
        )


def _validate_clip_length(path: Path) -> float:
    """Reject clips outside the 3-9s window. Returns measured duration."""
    duration = _probe_duration_seconds(path)
    if duration < MIN_CLIP_SECONDS or duration > MAX_CLIP_SECONDS:
        raise ValueError(
            f"Reference clip is {duration:.1f}s; accepted window is 3-9s. "
            f"Voice cloning works best with short clean speech. "
            f"Trim with: {TRIM_HINT}"
        )
    return duration


async def clone_add(
    name: str,
    audio_file: str,
    description: str = "",
    ref_text: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a new voice profile from a reference audio clip.

    Copies the audio file to ~/.voicemode/voices/<name>.wav and
    auto-transcribes it via the local Whisper STT service unless
    ref_text is provided explicitly.

    Args:
        name: Voice profile name (lowercase, no spaces recommended).
        audio_file: Path to the reference audio file (WAV preferred).
        description: Human-readable description of the voice.
        ref_text: Transcript of the reference audio. If None, auto-transcribes via Whisper.
        model: TTS model override. Defaults to CLONE_MODEL from config.
        base_url: TTS endpoint override. Defaults to DEFAULT_CLONE_BASE_URL.

    Returns:
        Dict with success status, profile details, or error info.
    """
    # Validate name
    if not name or not name.strip():
        return {"success": False, "error": "Voice name cannot be empty."}
    name = name.strip().lower()

    # Validate audio file
    source_path = Path(audio_file).expanduser().resolve()
    if not source_path.exists():
        return {"success": False, "error": f"Audio file not found: {audio_file}"}
    if not source_path.is_file():
        return {"success": False, "error": f"Not a file: {audio_file}"}

    # Check for duplicates
    data = _load_voices_json()
    if name in data["voices"]:
        return {
            "success": False,
            "error": f"Voice profile '{name}' already exists. Remove it first or choose a different name.",
        }

    # Gate: reject clips outside 3-9s before any expensive work.
    try:
        _validate_clip_length(source_path)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    # Normalise audio to ~/.voicemode/voices/<name>.wav (mono 24kHz s16, loudnorm)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = VOICES_DIR / f"{name}.wav"
    try:
        _normalise_audio(source_path, dest_path)
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    try:
        normalised_duration = _probe_duration_seconds(dest_path)
        logger.info(
            f"Normalised: {normalised_duration:.1f}s mono 24kHz 16-bit PCM"
        )
    except RuntimeError as e:
        logger.warning(f"Could not probe normalised file {dest_path}: {e}")

    # Auto-transcribe if ref_text not provided
    if ref_text is None:
        try:
            ref_text = _transcribe_audio(dest_path)
            logger.info(f"Auto-transcribed '{name}': {ref_text[:80]}...")
        except ConnectionError as e:
            # Clean up copied file since we can't complete the profile
            dest_path.unlink(missing_ok=True)
            return {
                "success": False,
                "error": str(e),
                "hint": "Start Whisper with: voicemode whisper service install",
            }
        except RuntimeError as e:
            dest_path.unlink(missing_ok=True)
            return {"success": False, "error": f"Transcription failed: {e}"}

    # Build profile entry
    profile: Dict[str, str] = {
        "ref_audio": str(dest_path),
        "ref_text": ref_text,
        "description": description,
    }
    if model:
        profile["model"] = model
    if base_url:
        profile["base_url"] = base_url

    # Save to voices.json
    data["voices"][name] = profile
    try:
        _save_voices_json(data)
    except OSError as e:
        dest_path.unlink(missing_ok=True)
        return {"success": False, "error": f"Failed to save voices.json: {e}"}

    return {
        "success": True,
        "name": name,
        "ref_audio": str(dest_path),
        "ref_text": ref_text,
        "description": description,
        "message": f"Voice profile '{name}' added successfully.",
    }


async def clone_list() -> Dict[str, Any]:
    """List all available clone voice profiles.

    Reads voices.json and returns all profile names with descriptions.

    Returns:
        Dict with success status and list of voice profiles.
    """
    data = _load_voices_json()
    voices = data.get("voices", {})

    profiles: List[Dict[str, str]] = []
    for name in sorted(voices.keys()):
        entry = voices[name]
        profiles.append({
            "name": name,
            "description": entry.get("description", ""),
            "ref_audio": entry.get("ref_audio", ""),
        })

    return {
        "success": True,
        "count": len(profiles),
        "voices": profiles,
    }


async def clone_remove(
    name: str,
    remove_audio: Union[bool, str] = True,
) -> Dict[str, Any]:
    """Remove a voice profile from voices.json.

    Optionally removes the reference audio file from ~/.voicemode/voices/.

    Args:
        name: Name of the voice profile to remove.
        remove_audio: Whether to also delete the reference audio file.

    Returns:
        Dict with success status and details of what was removed.
    """
    if not name or not name.strip():
        return {"success": False, "error": "Voice name cannot be empty."}
    name = name.strip().lower()

    if isinstance(remove_audio, str):
        remove_audio = remove_audio.lower() in ("true", "1", "yes")

    data = _load_voices_json()
    if name not in data["voices"]:
        return {
            "success": False,
            "error": f"Voice profile '{name}' not found.",
        }

    profile = data["voices"].pop(name)
    removed_items = [f"Profile '{name}' from voices.json"]

    # Optionally remove the audio file
    audio_removed = False
    if remove_audio:
        ref_audio_path = Path(profile.get("ref_audio", ""))
        if ref_audio_path.exists() and ref_audio_path.is_file():
            try:
                ref_audio_path.unlink()
                removed_items.append(f"Audio file: {ref_audio_path}")
                audio_removed = True
                logger.info(f"Removed reference audio: {ref_audio_path}")
            except OSError as e:
                logger.warning(f"Could not remove audio file {ref_audio_path}: {e}")
                removed_items.append(f"Audio file NOT removed (error: {e})")

    try:
        _save_voices_json(data)
    except OSError as e:
        return {"success": False, "error": f"Failed to save voices.json: {e}"}

    return {
        "success": True,
        "name": name,
        "audio_removed": audio_removed,
        "removed_items": removed_items,
        "message": f"Voice profile '{name}' removed.",
    }
