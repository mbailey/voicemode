"""Installation tool for the mlx-audio service (Apple Silicon).

mlx-audio is a single Python server that exposes OpenAI-compatible
``/v1/audio/transcriptions`` and ``/v1/audio/speech`` endpoints, backed
by MLX models for Whisper STT, Kokoro TTS, and Qwen3-TTS clone-voice.

Install layout::

    ~/.local/bin/mlx_audio.server     # uv-tool-managed entry point
    ~/.voicemode/services/mlx-audio/  # logs (and any future on-disk state)

Models are not downloaded by this tool -- VM-1082 owns
``mlx_audio_model_install``. Provider discovery is VM-1084.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

from voice_mode.server import mcp
from voice_mode.config import SERVICE_AUTO_ENABLE

logger = logging.getLogger("voicemode")


MLX_AUDIO_DEFAULT_PORT = 8890
MLX_AUDIO_PIP_PACKAGE = "mlx-audio"
MLX_AUDIO_ENTRY_POINT = "mlx_audio.server"


def _is_apple_silicon() -> bool:
    """True when running on macOS arm64 (Apple Silicon)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _coerce_bool(value: Union[bool, str, None]) -> Optional[bool]:
    """Permissive bool coercion for MCP string args."""
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

    # Refresh PATH so this process can see the freshly installed uv.
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


async def _update_mlx_audio_service_files(
    auto_enable: Optional[bool],
) -> Dict[str, Any]:
    """Render and install the launchd plist (or systemd unit, when ported)."""
    from voice_mode.tools.service import create_service_file, enable_service

    result: Dict[str, Any] = {"success": False, "updated": False}

    try:
        service_path, content = create_service_file("mlx_audio")

        if platform.system() == "Darwin":
            # Best-effort unload; a stale entry is harmless to overwrite.
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
    except Exception as exc:  # noqa: BLE001 — surface details to caller
        result["success"] = False
        result["error"] = str(exc)

    return result


@mcp.tool()
async def mlx_audio_install(
    port: Union[int, str] = MLX_AUDIO_DEFAULT_PORT,
    bind_lan: Union[bool, str] = False,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
    version: str = "latest",
) -> Dict[str, Any]:
    """Install mlx-audio as an opt-in Apple Silicon voicemode service.

    Installs the ``mlx-audio`` package as a uv-managed tool. Console entry
    points (``mlx_audio.server`` and friends) land in ``~/.local/bin``,
    which means there is no service-local venv to manage. The launchd
    plist (or systemd unit) is rendered to call ``mlx_audio.server``
    directly with config sourced from ``~/.voicemode/voicemode.env``.

    No models are downloaded by this tool. Use ``mlx_audio_model_install``
    (VM-1082) to download specific models on demand.

    Args:
        port: Local TCP port (default 8890 -- the upstream mlx-audio
            convention, mirroring kokoro-fastapi's 8880 default).
        bind_lan: Bind to ``0.0.0.0`` instead of ``127.0.0.1`` (default
            ``False``). LAN exposure is opt-in -- see VM-1076 Q2.
        force_reinstall: ``uv tool install --force`` -- reinstall even if
            already present.
        auto_enable: Enable the launchd service after install. ``None``
            falls back to ``VOICEMODE_SERVICE_AUTO_ENABLE``.
        version: ``mlx-audio`` PyPI version, or ``"latest"`` for the
            current release.

    Returns:
        Dict with ``success``, ``install_path``, ``service_url``, and
        ``service_path`` (plist or systemd unit).
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

    # Logs and any future on-disk state for the service live here. The
    # uv-tool-managed binary itself lives in ``~/.local/bin``.
    install_path = voicemode_dir / "services" / "mlx-audio"
    log_dir = voicemode_dir / "logs" / "mlx-audio"
    install_path.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Apply the bind/port choices to this process's env so any tools
    # invoked downstream (status checks, etc.) see the same values.
    os.environ["VOICEMODE_MLX_AUDIO_PORT"] = str(port_int)
    os.environ["VOICEMODE_MLX_AUDIO_HOST"] = "0.0.0.0" if bind_lan_bool else "127.0.0.1"

    # uv must be present before we touch anything else.
    uv_error = _ensure_uv_available()
    if uv_error:
        return {"success": False, "error": uv_error}

    # Build the ``uv tool install`` command. ``--force`` reinstalls even
    # when already present; without it, uv is a no-op on existing installs
    # which is what we want for idempotent runs.
    pip_target = (
        MLX_AUDIO_PIP_PACKAGE
        if version == "latest"
        else f"{MLX_AUDIO_PIP_PACKAGE}=={version}"
    )
    cmd = ["uv", "tool", "install", pip_target]
    if force_bool:
        cmd.append("--force")

    logger.info("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        return {
            "success": False,
            "error": f"`{' '.join(cmd)}` failed",
            "stderr": (exc.stderr or b"").decode(errors="replace"),
        }

    # Verify the entry point landed where we expect.
    entry_point = _entry_point_path()
    if not entry_point.exists():
        return {
            "success": False,
            "error": (
                f"`uv tool install {pip_target}` succeeded but "
                f"{entry_point} is missing. Check `uv tool list`."
            ),
        }

    # Install/update the launchd plist (or systemd unit if/when supported).
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
        "message": (
            f"mlx-audio installed via uv tool install. "
            f"Entry point: {entry_point}. "
            f"Service URL: http://{bind_host}:{port_int}. "
            "Use mlx_audio_model_install to download Whisper / Kokoro / Qwen3-TTS models."
        ),
    }
