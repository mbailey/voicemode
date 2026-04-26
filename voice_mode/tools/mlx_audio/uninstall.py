"""Uninstall tool for the mlx-audio service.

Cleans up the launchd plist (or systemd unit), the ``uv tool``
installation, and -- on ``remove_all_data`` -- the log directory.
User-level model caches and voice profiles are intentionally preserved
unless ``remove_models`` is set.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Union

from voice_mode.server import mcp
from voice_mode.config import BASE_DIR, MLX_AUDIO_PORT
from voice_mode.utils.services.common import find_process_by_port

MLX_AUDIO_PIP_PACKAGE = "mlx-audio"

logger = logging.getLogger("voicemode")


def _coerce_bool(value: Union[bool, str, None]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y", "on")
    return False


@mcp.tool()
async def mlx_audio_uninstall(
    remove_models: Union[bool, str] = False,
    remove_all_data: Union[bool, str] = False,
) -> Dict[str, Any]:
    """Uninstall mlx-audio.

    Args:
        remove_models: Also remove cached MLX model weights at
            ``~/.cache/huggingface/hub`` -- default ``False``. Note: this
            cache is shared with other Hugging Face tools, so we only
            remove ``mlx-community/*`` subdirectories.
        remove_all_data: Remove logs and voice profiles tied to mlx-audio.
            User-cloned voice profiles in ``~/.voicemode/voices/`` are
            *preserved* regardless of this flag.

    Returns:
        Dict with ``success``, ``removed_items``, and ``errors``.
    """
    remove_models_bool = _coerce_bool(remove_models)
    remove_all_data_bool = _coerce_bool(remove_all_data)

    system = platform.system()
    removed_items: List[str] = []
    errors: List[str] = []

    # 1. Stop any running mlx-audio process.
    try:
        proc = find_process_by_port(MLX_AUDIO_PORT)
        if proc:
            logger.info("Stopping mlx-audio (PID %s)", proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=5)
                removed_items.append(f"Stopped mlx-audio (PID {proc.pid})")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to stop mlx-audio process: {exc}")
    except Exception as exc:  # noqa: BLE001 — port lookup is best-effort
        logger.debug("Port-lookup failed during uninstall: %s", exc)

    # 2. Remove service configuration.
    if system == "Darwin":
        plist_path = (
            Path.home() / "Library" / "LaunchAgents" / "com.voicemode.mlx-audio.plist"
        )
        if plist_path.exists():
            try:
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    capture_output=True,
                )
                plist_path.unlink()
                removed_items.append(f"Removed launchd plist: {plist_path}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to remove {plist_path}: {exc}")
    elif system == "Linux":
        unit_path = (
            Path.home()
            / ".config"
            / "systemd"
            / "user"
            / "voicemode-mlx-audio.service"
        )
        if unit_path.exists():
            try:
                subprocess.run(
                    ["systemctl", "--user", "stop", "voicemode-mlx-audio.service"],
                    capture_output=True,
                )
                subprocess.run(
                    ["systemctl", "--user", "disable", "voicemode-mlx-audio.service"],
                    capture_output=True,
                )
                unit_path.unlink()
                subprocess.run(
                    ["systemctl", "--user", "daemon-reload"],
                    capture_output=True,
                )
                removed_items.append(f"Removed systemd unit: {unit_path}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to remove {unit_path}: {exc}")

    # 3. Uninstall the uv-tool-managed package (drops ~/.local/bin entry
    #    points and the tool's isolated environment).
    if shutil.which("uv"):
        try:
            result = subprocess.run(
                ["uv", "tool", "uninstall", MLX_AUDIO_PIP_PACKAGE],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                removed_items.append(f"Uninstalled uv tool: {MLX_AUDIO_PIP_PACKAGE}")
            else:
                # ``uv tool uninstall`` returns nonzero when the tool is
                # not installed; treat that as a no-op rather than an error.
                stderr = (result.stderr or "").strip()
                if "is not installed" in stderr or "not found" in stderr.lower():
                    logger.debug("mlx-audio uv tool already absent: %s", stderr)
                else:
                    errors.append(f"`uv tool uninstall {MLX_AUDIO_PIP_PACKAGE}` failed: {stderr}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to run uv tool uninstall: {exc}")
    else:
        logger.debug("uv not on PATH; skipping `uv tool uninstall`")

    # 4. Remove the service install directory (logs/state under
    #    ``~/.voicemode/services/mlx-audio``). Logs themselves live under
    #    ``~/.voicemode/logs/mlx-audio`` and are gated by ``remove_all_data``.
    install_dir = BASE_DIR / "services" / "mlx-audio"
    if install_dir.exists():
        try:
            shutil.rmtree(install_dir)
            removed_items.append(f"Removed install dir: {install_dir}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to remove {install_dir}: {exc}")

    # 5. Optionally remove cached MLX models from the HF hub cache.
    if remove_models_bool:
        hf_hub_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_hub_cache.exists():
            for entry in hf_hub_cache.iterdir():
                # HF cache uses "models--<org>--<name>" directory naming.
                if entry.name.startswith("models--mlx-community--"):
                    try:
                        shutil.rmtree(entry)
                        removed_items.append(f"Removed model cache: {entry.name}")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"Failed to remove {entry}: {exc}")

    # 6. Optionally remove logs (voices/profiles are always preserved).
    if remove_all_data_bool:
        log_dir = BASE_DIR / "logs" / "mlx-audio"
        if log_dir.exists():
            try:
                shutil.rmtree(log_dir)
                removed_items.append(f"Removed log dir: {log_dir}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to remove {log_dir}: {exc}")

    success = not errors
    message = (
        "mlx-audio uninstalled cleanly"
        if success
        else "mlx-audio uninstall completed with errors"
    )
    if remove_models_bool:
        message += " (model cache cleared)"
    if remove_all_data_bool:
        message += " (logs cleared)"

    return {
        "success": success,
        "message": message,
        "removed_items": removed_items,
        "errors": errors,
        "summary": {
            "items_removed": len(removed_items),
            "errors_encountered": len(errors),
        },
    }
