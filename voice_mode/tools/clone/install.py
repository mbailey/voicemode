"""Installation tool for clone TTS service (Qwen3-TTS via mlx-audio)."""

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Union

from voice_mode.config import CLONE_PORT, CLONE_MODEL, SERVICE_AUTO_ENABLE, BASE_DIR

logger = logging.getLogger("voicemode")

CLONE_SERVICE_DIR = BASE_DIR / "services" / "clone"


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon (M1/M2/M3/M4)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


async def install_clone_start_script(clone_dir: Path) -> Dict[str, Any]:
    """Install the clone TTS start script to the service directory."""
    bin_dir = clone_dir / "bin"
    start_script_path = bin_dir / "start-clone-server.sh"

    try:
        bin_dir.mkdir(parents=True, exist_ok=True)

        template_path = Path(__file__).parent.parent.parent / "templates" / "scripts" / "start-clone-server.sh"
        if not template_path.exists():
            return {"success": False, "error": f"Template not found: {template_path}"}

        shutil.copy2(template_path, start_script_path)
        os.chmod(start_script_path, 0o755)

        logger.info(f"Installed clone start script at {start_script_path}")
        return {"success": True, "start_script": str(start_script_path)}

    except Exception as e:
        logger.error(f"Error installing clone start script: {e}")
        return {"success": False, "error": str(e)}


async def install_clone_service_files(
    clone_dir: str,
    auto_enable: Optional[bool] = None
) -> Dict[str, Any]:
    """Install service files (plist/systemd) for clone TTS service.

    Uses create_service_file() from service.py as the single source of truth.
    """
    from voice_mode.tools.service import create_service_file, enable_service

    system = platform.system()
    result: Dict[str, Any] = {"success": False, "updated": False}

    try:
        service_path, content = create_service_file("clone")

        if system == "Darwin":
            try:
                subprocess.run(["launchctl", "unload", str(service_path)], capture_output=True)
            except Exception:
                pass

        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(content)

        result["success"] = True
        result["updated"] = True

        if system == "Darwin":
            result["plist_path"] = str(service_path)
        else:
            result["service_path"] = str(service_path)
            try:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to reload systemd: {e}")

        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            logger.info("Auto-enabling clone service...")
            enable_result = await enable_service("clone")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)

    return result


async def clone_install(
    port: Union[int, str] = 8890,
    model: Optional[str] = None,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
) -> Dict[str, Any]:
    """Install and set up clone TTS service (Qwen3-TTS via mlx-audio).

    Requires Apple Silicon (M1/M2/M3/M4) -- mlx-audio is MLX-native.

    1. Creates a virtual environment at ~/.voicemode/services/clone
    2. Installs mlx-audio in the venv
    3. Downloads the Qwen3-TTS model (~3.4GB)
    4. Installs a launchd agent (macOS) or systemd unit (Linux) for automatic startup

    Args:
        port: Port for the clone TTS server (default: 8890)
        model: Hugging Face model ID (default: mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16)
        force_reinstall: Force reinstallation even if already installed
        auto_enable: Enable service after install. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.

    Returns:
        Installation status with service configuration details
    """
    if not is_apple_silicon():
        return {
            "success": False,
            "error": "Clone TTS requires Apple Silicon (M1/M2/M3/M4). "
                     "mlx-audio is built on MLX which only supports Apple Silicon hardware.",
            "platform": platform.machine(),
            "system": platform.system(),
        }

    try:
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                logger.warning(f"Invalid port value '{port}', using default {CLONE_PORT}")
                port = CLONE_PORT

        if isinstance(force_reinstall, str):
            force_reinstall = force_reinstall.lower() in ("true", "1", "yes")

        resolved_auto_enable: Optional[bool] = None
        if isinstance(auto_enable, str):
            resolved_auto_enable = auto_enable.lower() in ("true", "1", "yes")
        elif isinstance(auto_enable, bool):
            resolved_auto_enable = auto_enable

        if model is None:
            model = CLONE_MODEL

        clone_dir = CLONE_SERVICE_DIR

        # Check if already installed
        venv_path = clone_dir / ".venv"
        if venv_path.exists() and not force_reinstall:
            # Verify mlx-audio is installed
            check = subprocess.run(
                [str(venv_path / "bin" / "python"), "-c", "import mlx_audio"],
                capture_output=True,
            )
            if check.returncode == 0:
                logger.info("Clone TTS already installed, updating service files...")

                # Install/update start script
                script_result = await install_clone_start_script(clone_dir)
                if not script_result["success"]:
                    return script_result

                # Install/update service files
                service_result = await install_clone_service_files(
                    str(clone_dir), auto_enable=resolved_auto_enable
                )

                message = "Clone TTS (Qwen3-TTS) already installed."
                if service_result.get("updated"):
                    message += " Service files updated."
                if service_result.get("enabled"):
                    message += " Service auto-enabled."

                return {
                    "success": True,
                    "install_path": str(clone_dir),
                    "already_installed": True,
                    "service_files_updated": service_result.get("updated", False),
                    "model": model,
                    "plist_path": service_result.get("plist_path"),
                    "service_path": service_result.get("service_path"),
                    "service_url": f"http://127.0.0.1:{port}",
                    "message": message,
                }

        # Check for uv
        if not shutil.which("uv"):
            return {
                "success": False,
                "error": "uv package manager is required. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh",
            }

        # Remove existing installation if force_reinstall
        if force_reinstall and clone_dir.exists():
            logger.info(f"Removing existing installation at {clone_dir}")
            shutil.rmtree(clone_dir)

        # Create install directory
        clone_dir.mkdir(parents=True, exist_ok=True)

        # Create virtual environment
        if not venv_path.exists():
            logger.info("Creating virtual environment for clone TTS...")
            subprocess.run(["uv", "venv"], cwd=str(clone_dir), check=True)

        # Install mlx-audio
        logger.info("Installing mlx-audio...")
        subprocess.run(
            ["uv", "pip", "install", "mlx-audio"],
            cwd=str(clone_dir),
            check=True,
        )

        # Pre-download the model so first request isn't slow
        logger.info(f"Downloading model: {model} (this may take a while)...")
        subprocess.run(
            [
                str(venv_path / "bin" / "python"), "-c",
                f"from huggingface_hub import snapshot_download; snapshot_download('{model}')"
            ],
            check=True,
        )

        # Install start script
        script_result = await install_clone_start_script(clone_dir)
        if not script_result["success"]:
            return {
                "success": False,
                "error": f"Failed to install start script: {script_result.get('error')}",
                "install_path": str(clone_dir),
            }

        # Install service files
        service_result = await install_clone_service_files(
            str(clone_dir), auto_enable=resolved_auto_enable
        )

        if not service_result.get("success"):
            return {
                "success": False,
                "error": f"Service file install failed: {service_result.get('error')}",
                "install_path": str(clone_dir),
            }

        result: Dict[str, Any] = {
            "success": True,
            "install_path": str(clone_dir),
            "model": model,
            "service_url": f"http://127.0.0.1:{port}",
            "start_script": script_result.get("start_script"),
            "message": f"Clone TTS (Qwen3-TTS) installed at {clone_dir}.",
        }

        system = platform.system()
        if system == "Darwin":
            if service_result.get("plist_path"):
                result["launchagent"] = service_result["plist_path"]
                result["message"] += f"\nLaunchAgent installed: {os.path.basename(service_result['plist_path'])}"
            if service_result.get("enabled"):
                result["message"] += " Service auto-enabled."
            result["service_status"] = "managed_by_launchd"
        elif system == "Linux":
            if service_result.get("service_path"):
                result["systemd_service"] = service_result["service_path"]
                result["message"] += f"\nSystemd service created: {os.path.basename(service_result['service_path'])}"
            if service_result.get("enabled"):
                result["message"] += " Service auto-enabled."
                result["service_status"] = "managed_by_systemd"
            else:
                result["service_status"] = "not_started"

        return result

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Command failed: {e.cmd}",
            "stderr": e.stderr.decode() if e.stderr else None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
