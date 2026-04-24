"""Uninstall tool for clone TTS service (Qwen3-TTS via mlx-audio)."""

import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Union

from voice_mode.server import mcp
from voice_mode.config import CLONE_PORT, BASE_DIR
from voice_mode.utils.services.common import find_process_by_port

logger = logging.getLogger("voicemode")


@mcp.tool()
async def clone_uninstall(
    remove_model: Union[bool, str] = False,
) -> Dict[str, Any]:
    """Uninstall the clone TTS service and optionally remove the model.

    This tool will:
    1. Stop any running clone TTS service
    2. Remove service configurations (launchd/systemd)
    3. Remove the clone TTS installation (venv + start script)
    4. Optionally remove the cached Qwen3-TTS model (~3.4GB)

    Args:
        remove_model: Also remove the cached Qwen3-TTS model (default: False)

    Returns:
        Dictionary with uninstall status and details
    """
    if isinstance(remove_model, str):
        remove_model = remove_model.lower() in ("true", "1", "yes")

    system = platform.system()
    removed_items = []
    errors = []

    try:
        # 1. Stop any running clone service
        logger.info("Checking for running clone TTS service...")
        proc = find_process_by_port(CLONE_PORT)
        if proc:
            try:
                logger.info(f"Stopping clone TTS service (PID: {proc.pid})...")
                proc.terminate()
                proc.wait(timeout=5)
                removed_items.append("Stopped running clone TTS service")
            except Exception as e:
                logger.warning(f"Failed to stop clone TTS service: {e}")

        # 2. Remove service configurations
        if system == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.clone.plist"
            if plist_path.exists():
                try:
                    subprocess.run(
                        ["launchctl", "unload", str(plist_path)],
                        capture_output=True,
                    )
                    plist_path.unlink()
                    removed_items.append("Removed launchd configuration")
                    logger.info(f"Removed {plist_path}")
                except Exception as e:
                    errors.append(f"Failed to remove {plist_path}: {e}")
        elif system == "Linux":
            service_path = Path.home() / ".config" / "systemd" / "user" / "voicemode-clone.service"
            if service_path.exists():
                try:
                    subprocess.run(
                        ["systemctl", "--user", "stop", "voicemode-clone.service"],
                        capture_output=True,
                    )
                    subprocess.run(
                        ["systemctl", "--user", "disable", "voicemode-clone.service"],
                        capture_output=True,
                    )
                    service_path.unlink()
                    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                    removed_items.append("Removed systemd service")
                    logger.info(f"Removed {service_path}")
                except Exception as e:
                    errors.append(f"Failed to remove {service_path}: {e}")

        # 3. Remove clone installation directory
        clone_dir = BASE_DIR / "services" / "clone"
        if clone_dir.exists():
            try:
                shutil.rmtree(clone_dir)
                removed_items.append(f"Removed clone installation: {clone_dir}")
                logger.info(f"Removed {clone_dir}")
            except Exception as e:
                errors.append(f"Failed to remove {clone_dir}: {e}")

        # 4. Remove logs
        log_dir = BASE_DIR / "logs" / "clone"
        if log_dir.exists():
            try:
                shutil.rmtree(log_dir)
                removed_items.append("Removed clone log files")
            except Exception as e:
                errors.append(f"Failed to remove {log_dir}: {e}")

        # 5. Optionally remove cached model
        if remove_model:
            # huggingface_hub caches models under ~/.cache/huggingface/hub/
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
            if cache_dir.exists():
                # Look for Qwen3-TTS model directories
                for item in cache_dir.iterdir():
                    if "Qwen3-TTS" in item.name:
                        try:
                            shutil.rmtree(item)
                            removed_items.append(f"Removed cached model: {item.name}")
                            logger.info(f"Removed {item}")
                        except Exception as e:
                            errors.append(f"Failed to remove {item}: {e}")

        success = len(errors) == 0

        if success:
            message = "Clone TTS service has been successfully uninstalled"
            if remove_model:
                message += " (including cached model)"
        else:
            message = "Clone TTS uninstall completed with some errors"

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

    except Exception as e:
        logger.error(f"Unexpected error during clone TTS uninstall: {e}")
        return {
            "success": False,
            "message": f"Failed to uninstall clone TTS: {e}",
            "removed_items": removed_items,
            "errors": errors + [str(e)],
            "summary": {
                "items_removed": len(removed_items),
                "errors_encountered": len(errors) + 1,
            },
        }
