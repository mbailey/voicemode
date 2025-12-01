"""Installation tool for kokoro-fastapi TTS service."""

import os
import sys
import platform
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
import asyncio
import aiohttp

from voice_mode.server import mcp
from voice_mode.config import SERVICE_AUTO_ENABLE
from voice_mode.utils.version_helpers import (
    get_git_tags, get_latest_stable_tag, get_current_version,
    checkout_version, is_version_installed
)
from voice_mode.utils.migration_helpers import auto_migrate_if_needed

logger = logging.getLogger("voicemode")


async def update_kokoro_service_files(
    install_dir: str,
    voicemode_dir: str,
    port: int,
    start_script_path: str,
    auto_enable: Optional[bool] = None
) -> Dict[str, Any]:
    """Update service files (plist/systemd) for kokoro service.

    Uses create_service_file() from service.py as the single source of truth.
    The parameters are kept for backwards compatibility but install_dir, port,
    and start_script_path are now derived from templates and config.

    Returns:
        Dict with success status and details about what was updated
    """
    from voice_mode.tools.service import create_service_file, enable_service

    system = platform.system()
    result = {"success": False, "updated": False}

    try:
        # Create service file using the unified function
        service_path, content = create_service_file("kokoro")

        # Unload if already loaded (macOS only, ignore errors)
        if system == "Darwin":
            try:
                subprocess.run(["launchctl", "unload", str(service_path)], capture_output=True)
            except Exception:
                pass

        # Write service file
        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(content)

        result["success"] = True
        result["updated"] = True

        if system == "Darwin":
            result["plist_path"] = str(service_path)
        else:
            result["service_path"] = str(service_path)
            # Reload systemd
            try:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to reload systemd: {e}")

        # Handle auto_enable if specified
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            logger.info("Auto-enabling kokoro service...")
            enable_result = await enable_service("kokoro")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)

    return result


@mcp.tool()
async def kokoro_install(
    install_dir: Optional[str] = None,
    models_dir: Optional[str] = None,
    port: Union[int, str] = 8880,
    auto_start: Union[bool, str] = True,
    install_models: Union[bool, str] = True,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
    version: str = "latest",
    skip_deps: Union[bool, str] = False
) -> Dict[str, Any]:
    """
    Install and setup remsky/kokoro-fastapi TTS service using the simple 3-step approach.

    1. Clones the repository to ~/.voicemode/services/kokoro
    2. Uses the appropriate start script (start-gpu_mac.sh on macOS)
    3. Installs a launchagent on macOS for automatic startup

    Args:
        install_dir: Directory to install kokoro-fastapi (default: ~/.voicemode/services/kokoro)
        models_dir: Directory for Kokoro models (default: ~/.voicemode/kokoro-models) - not currently used
        port: Port to configure for the service (default: 8880)
        auto_start: Start the service after installation (ignored on macOS, uses launchd instead)
        install_models: Download Kokoro models (not used - handled by start script)
        force_reinstall: Force reinstallation even if already installed
        auto_enable: Enable service after install. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.
        version: Version to install (default: "latest" for latest stable release)
        skip_deps: Skip dependency checks (for advanced users, default: False)

    Returns:
        Installation status with service configuration details
    """
    try:
        # Convert port to integer if provided as string
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                logger.warning(f"Invalid port value '{port}', using default 8880")
                port = 8880

        # Check for and migrate old installations
        migration_msg = auto_migrate_if_needed("kokoro")

        # Check kokoro dependencies (unless skipped)
        if not skip_deps:
            from voice_mode.utils.dependencies.checker import (
                check_component_dependencies,
                install_missing_dependencies
            )

            results = check_component_dependencies('kokoro')
            missing = [pkg for pkg, installed in results.items() if not installed]

            if missing:
                logger.info(f"Missing kokoro dependencies: {', '.join(missing)}")
                # Check if we're in an interactive terminal (not MCP context)
                is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False
                success, output = install_missing_dependencies(missing, interactive=is_interactive)
                if not success:
                    return {
                        "success": False,
                        "error": "Required dependencies not installed",
                        "missing_dependencies": missing
                    }
        else:
            logger.info("Skipping dependency checks (--skip-deps specified)")

        # Set default directories under ~/.voicemode
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "services", "kokoro")
        else:
            install_dir = os.path.expanduser(install_dir)
            
        if models_dir is None:
            models_dir = os.path.join(voicemode_dir, "kokoro-models")
        else:
            models_dir = os.path.expanduser(models_dir)
        
        # Resolve version if "latest" is specified
        if version == "latest":
            tags = get_git_tags("https://github.com/remsky/kokoro-fastapi")
            if not tags:
                return {
                    "success": False,
                    "error": "Failed to fetch available versions"
                }
            version = get_latest_stable_tag(tags)
            if not version:
                return {
                    "success": False,
                    "error": "No stable versions found"
                }
            logger.info(f"Using latest stable version: {version}")
        
        # Check if already installed
        if os.path.exists(install_dir) and not force_reinstall:
            if os.path.exists(os.path.join(install_dir, "main.py")):
                # Check if the requested version is already installed
                if is_version_installed(Path(install_dir), version):
                    current_version = get_current_version(Path(install_dir))
                    
                    # Determine which start script to use
                    system = platform.system()
                    if system == "Darwin":
                        start_script_name = "start-gpu_mac.sh"
                    else:
                        start_script_name = "start-gpu.sh"  # Default to GPU version
                    
                    start_script_path = os.path.join(install_dir, start_script_name)
                    
                    # If a custom port is requested, create custom start script
                    if port != 8880 and os.path.exists(start_script_path):
                        logger.info(f"Creating custom start script for port {port}")
                        with open(start_script_path, 'r') as f:
                            script_content = f.read()
                        modified_script = script_content.replace("--port 8880", f"--port {port}")
                        custom_script_name = f"start-custom-{port}.sh"
                        custom_script_path = os.path.join(install_dir, custom_script_name)
                        with open(custom_script_path, 'w') as f:
                            f.write(modified_script)
                        os.chmod(custom_script_path, 0o755)
                        start_script_path = custom_script_path
                    
                    # Always update service files even if kokoro is already installed
                    logger.info("Kokoro is already installed, updating service files...")
                    service_update_result = await update_kokoro_service_files(
                        install_dir=install_dir,
                        voicemode_dir=voicemode_dir,
                        port=port,
                        start_script_path=start_script_path,
                        auto_enable=auto_enable
                    )
                    
                    # Build response message
                    message = f"kokoro-fastapi version {current_version} already installed."
                    if service_update_result.get("updated"):
                        message += " Service files updated."
                    if service_update_result.get("enabled"):
                        message += " Service auto-enabled."
                    
                    return {
                        "success": True,
                        "install_path": install_dir,
                        "models_path": models_dir,
                        "already_installed": True,
                        "service_files_updated": service_update_result.get("updated", False),
                        "version": current_version,
                        "plist_path": service_update_result.get("plist_path"),
                        "service_path": service_update_result.get("service_path"),
                        "start_script": start_script_path,
                        "service_url": f"http://127.0.0.1:{port}",
                        "message": message
                    }
        
        # Check Python version
        if sys.version_info < (3, 10):
            return {
                "success": False,
                "error": f"Python 3.10+ required. Current version: {sys.version}"
            }
        
        # Check for git
        if not shutil.which("git"):
            return {
                "success": False,
                "error": "Git is required. Please install git and try again."
            }
        
        # Install UV if not present
        if not shutil.which("uv"):
            logger.info("Installing UV package manager...")
            subprocess.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True,
                check=True
            )
            # Add UV to PATH for this session
            os.environ["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{os.environ['PATH']}"
        
        # Remove existing installation if force_reinstall
        if force_reinstall and os.path.exists(install_dir):
            logger.info(f"Removing existing installation at {install_dir}")
            shutil.rmtree(install_dir)
        
        # Clone repository if not exists
        if not os.path.exists(install_dir):
            logger.info(f"Cloning kokoro-fastapi repository (version {version})...")
            subprocess.run([
                "git", "clone", "https://github.com/remsky/kokoro-fastapi.git", install_dir
            ], check=True)
            # Checkout the specific version
            if not checkout_version(Path(install_dir), version):
                shutil.rmtree(install_dir)
                return {
                    "success": False,
                    "error": f"Failed to checkout version {version}"
                }
        else:
            logger.info(f"Using existing kokoro-fastapi directory, switching to version {version}...")
            # Clean any local changes and checkout the version
            subprocess.run(["git", "reset", "--hard"], cwd=install_dir, check=True)
            subprocess.run(["git", "clean", "-fd"], cwd=install_dir, check=True)
            if not checkout_version(Path(install_dir), version):
                return {
                    "success": False,
                    "error": f"Failed to checkout version {version}"
                }
        
        # Determine system and select appropriate start script
        system = platform.system()
        if system == "Darwin":
            start_script_name = "start-gpu_mac.sh"
        elif system == "Linux":
            # Check if GPU available
            if shutil.which("nvidia-smi"):
                start_script_name = "start-gpu.sh"
            else:
                start_script_name = "start-cpu.sh"
        else:
            start_script_name = "start-cpu.ps1"  # Windows
        
        start_script_path = os.path.join(install_dir, start_script_name)
        
        # Check if the start script exists
        if not os.path.exists(start_script_path):
            return {
                "success": False,
                "error": f"Start script not found: {start_script_path}",
                "message": "The repository seems incomplete. Try force_reinstall=True"
            }
        
        # If a custom port is requested, we need to modify the start script
        if port != 8880:
            logger.info(f"Creating custom start script for port {port}")
            with open(start_script_path, 'r') as f:
                script_content = f.read()
            
            # Replace the port in the script
            modified_script = script_content.replace("--port 8880", f"--port {port}")
            
            # Create a custom start script
            custom_script_name = f"start-custom-{port}.sh"
            custom_script_path = os.path.join(install_dir, custom_script_name)
            with open(custom_script_path, 'w') as f:
                f.write(modified_script)
            os.chmod(custom_script_path, 0o755)
            start_script_path = custom_script_path
            
        current_version = get_current_version(Path(install_dir))
        result = {
            "success": True,
            "install_path": install_dir,
            "service_url": f"http://127.0.0.1:{port}",
            "start_command": f"cd {install_dir} && ./{os.path.basename(start_script_path)}",
            "start_script": start_script_path,
            "version": current_version,
            "message": f"Kokoro-fastapi {current_version} installed. Run: cd {install_dir} && ./{os.path.basename(start_script_path)}{' (' + migration_msg + ')' if migration_msg else ''}"
        }
        
        # Install/update service files using centralized function
        # This uses templates from service.py for consistency
        service_update_result = await update_kokoro_service_files(
            install_dir=install_dir,
            voicemode_dir=voicemode_dir,
            port=port,
            start_script_path=start_script_path,
            auto_enable=auto_enable
        )

        if not service_update_result.get("success"):
            logger.error(f"Failed to update service files: {service_update_result.get('error', 'Unknown error')}")
            result["error"] = f"Service file update failed: {service_update_result.get('error', 'Unknown error')}"
            return result

        # Update result with service file information
        if system == "Darwin":
            if service_update_result.get("plist_path"):
                result["launchagent"] = service_update_result["plist_path"]
                result["message"] += f"\nLaunchAgent installed: {os.path.basename(service_update_result['plist_path'])}"
            if service_update_result.get("enabled"):
                result["message"] += " Service auto-enabled."
            result["service_status"] = "managed_by_launchd"
        elif system == "Linux":
            if service_update_result.get("service_path"):
                result["systemd_service"] = service_update_result["service_path"]
                result["message"] += f"\nSystemd service created: {os.path.basename(service_update_result['service_path'])}"
            if service_update_result.get("enabled"):
                result["message"] += " Service auto-enabled."
                result["service_status"] = "managed_by_systemd"
            else:
                result["service_status"] = "not_started"
        else:
            result["service_status"] = "not_started"

        return result
    
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Command failed: {e.cmd}",
            "stderr": e.stderr.decode() if e.stderr else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }