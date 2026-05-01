"""Installation tool for the mlx-audio service (Apple Silicon).

mlx-audio is a single Python server that exposes OpenAI-compatible
``/v1/audio/transcriptions`` and ``/v1/audio/speech`` endpoints, backed
by MLX models for Whisper STT, Kokoro TTS, and Qwen3-TTS clone-voice.

Install layout::

    ~/.local/bin/mlx_audio.server     # uv-tool-managed entry point
    ~/.local/share/uv/tools/mlx-audio/  # uv-managed isolated env

The install pipeline is:

1. Apple Silicon gate -- mlx-audio is MLX-native, no Intel/Linux fallback.
2. ``uv tool install mlx-audio>=0.4.3 --with <extras>`` -- the extras list
   is hardcoded in :data:`MLX_AUDIO_EXTRAS` and is the minimum surface
   needed to make the upstream server.py serve Kokoro TTS, Qwen3-TTS
   clone-voice, and Whisper STT under the OpenAI-compatible API. The
   ``>=0.4.3`` floor exists because earlier releases of mlx-audio needed
   a bundled patch for MLX Metal thread-safety + OpenAI-style STT
   ``response_format``; both fixes are upstream from 0.4.3 on, and
   voicemode no longer ships a patch.
3. Render the launchd plist calling ``~/.local/bin/mlx_audio.server``
   directly. (Apple-Silicon-only -- no systemd unit ships.)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from voice_mode.config import SERVICE_AUTO_ENABLE

logger = logging.getLogger("voicemode")


MLX_AUDIO_DEFAULT_PORT = 8890
# Pinned ``>=0.4.3`` because that's the first upstream release that absorbed
# the MLX Metal serialisation lock + OpenAI-compatible STT ``response_format``
# fixes voicemode previously shipped as a bundled patch. See VM-1126.
MLX_AUDIO_PIP_PACKAGE = "mlx-audio>=0.4.3"
MLX_AUDIO_ENTRY_POINT = "mlx_audio.server"

# Extras the bundled server.py + voicemode client need at runtime. These were
# captured from Mike's working install on 2026-04-27. Order matters only for
# reviewability -- ``uv tool install`` resolves them as a single set.
MLX_AUDIO_EXTRAS: List[str] = [
    "misaki[en]",          # Kokoro G2P (text -> phonemes)
    # spaCy English model used by misaki -- not on PyPI, install from GitHub release wheel.
    # When upgrading spaCy, also bump the en_core_web_sm version below to a compatible release.
    "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
    "uvicorn",             # ASGI server for the FastAPI app
    "fastapi",             # web framework -- mlx-audio doesn't pin it
    "webrtcvad",           # voice activity detection
    "python-multipart",    # multipart/form-data on /v1/audio/transcriptions
    "setuptools<81",       # pinned to keep pkg_resources available
    "sounddevice",         # audio device interface
    "soundfile",           # libsndfile bindings
    "librosa",             # audio analysis (Whisper preprocessing)
    "mlx",                 # core MLX runtime
    "mlx-lm",              # mlx_lm -- Qwen3-TTS path
]

def _is_apple_silicon() -> bool:
    """True when running on macOS arm64 (Apple Silicon)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _coerce_bool(value: Union[bool, str, None]) -> Optional[bool]:
    """Permissive bool coercion for MCP/CLI string args."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "y", "on"):
            return True
        if normalized in ("false", "0", "no", "n", "off"):
            return False
    return None


def _coerce_int(value: Union[int, str], default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            logger.warning("Invalid int value %r, using default %d", value, default)
    return default


def _ensure_uv_available() -> Optional[str]:
    """Ensure ``uv`` is on PATH; install via the official script if missing.

    Returns an error string on failure, ``None`` on success.
    """
    if shutil.which("uv"):
        return None

    logger.info("uv not found, installing via astral.sh installer...")
    try:
        subprocess.run(
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            shell=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to install uv: {exc}"

    cargo_bin = os.path.expanduser("~/.cargo/bin")
    local_bin = os.path.expanduser("~/.local/bin")
    os.environ["PATH"] = f"{cargo_bin}:{local_bin}:{os.environ.get('PATH', '')}"

    if not shutil.which("uv"):
        return "uv was installed but is not on PATH"
    return None


def _entry_point_path() -> Path:
    """Return the expected path of the ``mlx_audio.server`` entry point.

    ``uv tool install`` puts entry points in ``~/.local/bin`` on Linux/macOS.
    """
    return Path.home() / ".local" / "bin" / MLX_AUDIO_ENTRY_POINT


def _build_install_cmd(force_reinstall: bool) -> List[str]:
    """Build the ``uv tool install`` command, including all extras.

    Public-shape: ``["uv", "tool", "install", "mlx-audio", "--with", X, ...]``
    optionally followed by ``--reinstall``.
    """
    cmd: List[str] = ["uv", "tool", "install", MLX_AUDIO_PIP_PACKAGE]
    for extra in MLX_AUDIO_EXTRAS:
        cmd.extend(["--with", extra])
    if force_reinstall:
        cmd.append("--reinstall")
    return cmd


async def _update_mlx_audio_service_files(
    auto_enable: Optional[bool],
) -> Dict[str, Any]:
    """Render and install the launchd plist (Apple Silicon only)."""
    from voice_mode.tools.service import create_service_file, enable_service

    result: Dict[str, Any] = {"success": False, "updated": False}

    try:
        service_path, content = create_service_file("mlx_audio")

        # Best-effort unload; a stale entry is harmless to overwrite.
        # mlx-audio is Apple-Silicon-only so this is always launchctl.
        subprocess.run(
            ["launchctl", "unload", str(service_path)],
            capture_output=True,
        )

        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(content)

        result["success"] = True
        result["updated"] = True
        result["service_path"] = str(service_path)

        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            logger.info("Auto-enabling mlx-audio service...")
            enable_result = await enable_service("mlx_audio")
            result["enabled"] = "✅" in enable_result
            if not result["enabled"]:
                logger.warning("mlx-audio auto-enable failed: %s", enable_result)
    except Exception as exc:  # noqa: BLE001
        result["success"] = False
        result["error"] = str(exc)

    return result


async def mlx_audio_install(
    port: Union[int, str] = MLX_AUDIO_DEFAULT_PORT,
    bind_lan: Union[bool, str] = False,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
) -> Dict[str, Any]:
    """Install mlx-audio as an opt-in Apple Silicon voicemode service.

    Installs the ``mlx-audio`` package via ``uv tool install`` along with
    the runtime extras list (Kokoro G2P, FastAPI, sounddevice, mlx-lm,
    etc.). Console entry points (``mlx_audio.server`` and friends) land
    in ``~/.local/bin`` -- no service-local venv. The launchd plist is
    rendered to call ``mlx_audio.server`` directly with config sourced
    from ``~/.voicemode/voicemode.env``.

    No models are downloaded by this tool.

    Args:
        port: Local TCP port (default 8890 -- mlx-audio convention).
        bind_lan: Bind to ``0.0.0.0`` instead of ``127.0.0.1`` (default
            ``False``). LAN exposure is opt-in.
        force_reinstall: Pass ``--reinstall`` to ``uv tool install`` --
            forces a reinstall even if mlx-audio is already present.
        auto_enable: Enable the launchd service after install. ``None``
            falls back to ``VOICEMODE_SERVICE_AUTO_ENABLE``.

    Returns:
        Dict with ``success``, ``install_path``, ``service_url``, and
        ``service_path``.
    """
    if not _is_apple_silicon():
        return {
            "success": False,
            "error": (
                "mlx-audio requires Apple Silicon (macOS arm64). "
                "On Intel macOS or Linux, keep using whisper.cpp + kokoro-fastapi."
            ),
            "platform": f"{platform.system()} {platform.machine()}",
        }

    if sys.version_info < (3, 10):
        return {
            "success": False,
            "error": f"Python 3.10+ required. Current: {sys.version}",
        }

    port_int = _coerce_int(port, MLX_AUDIO_DEFAULT_PORT)
    bind_lan_bool = bool(_coerce_bool(bind_lan))
    force_bool = bool(_coerce_bool(force_reinstall))
    auto_enable_bool = _coerce_bool(auto_enable)

    voicemode_dir = Path(
        os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    )
    voicemode_dir.mkdir(parents=True, exist_ok=True)

    install_path = voicemode_dir / "services" / "mlx-audio"
    log_dir = voicemode_dir / "logs" / "mlx-audio"
    install_path.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    os.environ["VOICEMODE_MLX_AUDIO_PORT"] = str(port_int)
    os.environ["VOICEMODE_MLX_AUDIO_HOST"] = "0.0.0.0" if bind_lan_bool else "127.0.0.1"

    uv_error = _ensure_uv_available()
    if uv_error:
        return {"success": False, "error": uv_error}

    cmd = _build_install_cmd(force_bool)
    logger.info("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        return {
            "success": False,
            "error": f"`{' '.join(cmd)}` failed",
            "stderr": (exc.stderr or b"").decode(errors="replace"),
        }

    entry_point = _entry_point_path()
    if not entry_point.exists():
        return {
            "success": False,
            "error": (
                f"`uv tool install {MLX_AUDIO_PIP_PACKAGE}` succeeded but "
                f"{entry_point} is missing. Check `uv tool list`."
            ),
        }

    service_result = await _update_mlx_audio_service_files(auto_enable_bool)
    if not service_result.get("success"):
        return {
            "success": False,
            "error": f"service file update failed: {service_result.get('error')}",
            "install_path": str(install_path),
        }

    bind_host = "0.0.0.0" if bind_lan_bool else "127.0.0.1"
    return {
        "success": True,
        "install_path": str(install_path),
        "entry_point": str(entry_point),
        "service_path": service_result.get("service_path"),
        "service_url": f"http://{bind_host}:{port_int}",
        "host": bind_host,
        "port": port_int,
        "auto_enabled": service_result.get("enabled", False),
        "extras": list(MLX_AUDIO_EXTRAS),
        "message": (
            f"mlx-audio installed via uv tool install. "
            f"Entry point: {entry_point}. "
            f"Service URL: http://{bind_host}:{port_int}."
        ),
    }
