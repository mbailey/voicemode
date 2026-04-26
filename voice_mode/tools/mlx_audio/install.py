"""Installation tool for the mlx-audio service (Apple Silicon).

mlx-audio is a single Python server that exposes OpenAI-compatible
``/v1/audio/transcriptions`` and ``/v1/audio/speech`` endpoints, backed
by MLX models for Whisper STT, Kokoro TTS, and Qwen3-TTS clone-voice.

Install layout::

    ~/.voicemode/services/mlx-audio/
        venv/                # uv venv
        bin/start-mlx-audio.sh
        logs/                # served by launchd

This is the *scaffolding only*. Model downloads are handled by VM-1082;
provider discovery integration is VM-1084.
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


MLX_AUDIO_DEFAULT_PORT = 8891
MLX_AUDIO_PIP_PACKAGE = "mlx-audio"


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


def _install_start_script(install_dir: Path) -> Path:
    """Copy the start-mlx-audio.sh template into the install dir's bin/."""
    template_path = (
        Path(__file__).parent.parent.parent
        / "templates"
        / "scripts"
        / "start-mlx-audio.sh"
    )
    if not template_path.exists():
        raise FileNotFoundError(f"start-mlx-audio.sh template not found: {template_path}")

    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    dest = bin_dir / "start-mlx-audio.sh"
    dest.write_text(template_path.read_text())
    dest.chmod(0o755)
    return dest


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
    install_dir: Optional[str] = None,
    port: Union[int, str] = MLX_AUDIO_DEFAULT_PORT,
    bind_lan: Union[bool, str] = False,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
    version: str = "latest",
) -> Dict[str, Any]:
    """Install mlx-audio as an opt-in Apple Silicon voicemode service.

    Creates a uv-managed venv at ``~/.voicemode/services/mlx-audio/venv`` and
    installs ``mlx-audio`` from PyPI. Mirrors the kokoro install pattern --
    one launchd plist, one start script, one process serving Whisper STT +
    Kokoro TTS + Qwen3-TTS clone-voice.

    No models are downloaded by this tool. Use ``mlx_audio_model_install``
    (VM-1082) to download specific models on demand.

    Args:
        install_dir: Override install location
            (default: ``~/.voicemode/services/mlx-audio``).
        port: Local TCP port (default 8891 -- avoids the ms2:8890 SSH
            tunnel collision).
        bind_lan: Bind to ``0.0.0.0`` instead of ``127.0.0.1`` (default
            ``False``). LAN exposure is opt-in -- see VM-1076 Q2.
        force_reinstall: Wipe the existing venv and reinstall from scratch.
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

    install_path = (
        Path(install_dir).expanduser()
        if install_dir
        else voicemode_dir / "services" / "mlx-audio"
    )
    venv_path = install_path / "venv"

    # Apply the bind/port choices to this process's env so the start script,
    # rendered immediately below, picks them up via voicemode.env semantics.
    os.environ["VOICEMODE_MLX_AUDIO_PORT"] = str(port_int)
    os.environ["VOICEMODE_MLX_AUDIO_HOST"] = "0.0.0.0" if bind_lan_bool else "127.0.0.1"

    # uv must be present before we touch anything else.
    uv_error = _ensure_uv_available()
    if uv_error:
        return {"success": False, "error": uv_error}

    if force_bool and venv_path.exists():
        logger.info("force_reinstall: removing existing venv at %s", venv_path)
        shutil.rmtree(venv_path)

    install_path.mkdir(parents=True, exist_ok=True)

    # Create venv if missing.
    if not venv_path.exists():
        logger.info("Creating mlx-audio venv at %s", venv_path)
        try:
            subprocess.run(
                ["uv", "venv", str(venv_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "error": "uv venv failed",
                "stderr": (exc.stderr or b"").decode(errors="replace"),
            }

    # Install mlx-audio into the venv. uv pip install --python <python> is the
    # recommended way to target an external venv from a different cwd.
    pip_target = f"{MLX_AUDIO_PIP_PACKAGE}" if version == "latest" else f"{MLX_AUDIO_PIP_PACKAGE}=={version}"
    venv_python = venv_path / "bin" / "python"
    logger.info("Installing %s into %s", pip_target, venv_path)
    try:
        subprocess.run(
            ["uv", "pip", "install", "--python", str(venv_python), pip_target],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "success": False,
            "error": f"uv pip install {pip_target} failed",
            "stderr": (exc.stderr or b"").decode(errors="replace"),
        }

    # Install start script.
    try:
        start_script_path = _install_start_script(install_path)
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

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
        "venv_path": str(venv_path),
        "start_script": str(start_script_path),
        "service_path": service_result.get("service_path"),
        "service_url": f"http://{bind_host}:{port_int}",
        "host": bind_host,
        "port": port_int,
        "auto_enabled": service_result.get("enabled", False),
        "message": (
            f"mlx-audio installed at {install_path}. "
            f"Service URL: http://{bind_host}:{port_int}. "
            "Use mlx_audio_model_install to download Whisper / Kokoro / Qwen3-TTS models."
        ),
    }
