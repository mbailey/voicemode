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

logger = logging.getLogger("voice-mode")


async def update_kokoro_service_files(
    install_dir: str,
    voicemode_dir: str,
    port: int,
    start_script_path: str,
    auto_enable: Optional[bool] = None
) -> Dict[str, Any]:
    """Update service files (plist/systemd) for kokoro service.
    
    This function updates the service files without reinstalling kokoro itself.
    It ensures paths are properly expanded and templates are up to date.
    
    Returns:
        Dict with success status and details about what was updated
    """
    system = platform.system()
    result = {"success": False, "updated": False}
    
    # Create log directory
    log_dir = os.path.join(voicemode_dir, 'logs', 'kokoro')
    os.makedirs(log_dir, exist_ok=True)
    
    if system == "Darwin":
        logger.info("Updating launchagent for kokoro...")
        launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(launchagents_dir, exist_ok=True)
        
        plist_name = "com.voicemode.kokoro.plist"
        plist_path = os.path.join(launchagents_dir, plist_name)
        
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro</string>
    <key>ProgramArguments</key>
    <array>
        <string>{start_script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{install_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.error.log')}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.path.expanduser("~/.local/bin")}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>"""
        
        # Unload if already loaded (ignore errors)
        try:
            subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        except:
            pass
        
        # Write updated plist
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        result["success"] = True
        result["updated"] = True
        result["plist_path"] = plist_path
        
        # Handle auto_enable if specified
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        if auto_enable:
            logger.info("Auto-enabling kokoro service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("kokoro")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False
    
    elif system == "Linux":
        logger.info("Updating systemd user service for kokoro...")
        systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(systemd_user_dir, exist_ok=True)
        
        service_name = "voicemode-kokoro.service"
        service_path = os.path.join(systemd_user_dir, service_name)
        
        service_content = f"""[Unit]
Description=VoiceMode Kokoro TTS Service
After=network.target
[Service]
Type=simple
ExecStart={start_script_path}
Restart=on-failure
RestartSec=10
WorkingDirectory={install_dir}
StandardOutput=append:{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.log')}
StandardError=append:{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.error.log')}
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/home/m/.local/bin"
[Install]
WantedBy=default.target
"""
        
        with open(service_path, 'w') as f:
            f.write(service_content)
        
        # Reload systemd
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            result["success"] = True
            result["updated"] = True
            result["service_path"] = service_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to reload systemd: {e}")
            result["success"] = True  # Still consider it success if file was written
            result["updated"] = True
            result["service_path"] = service_path
        
        # Handle auto_enable if specified
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        if auto_enable:
            logger.info("Auto-enabling kokoro service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("kokoro")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False
    
    else:
        result["success"] = False
        result["error"] = f"Unsupported platform: {system}"
    
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
    version: str = "latest"
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
        
        # Install/update service files
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
        
        # Update result with service file information based on platform
        if system == "Darwin":
            logger.info("Installing launchagent for automatic startup...")
            launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launchagents_dir, exist_ok=True)
            
            # Create log directory
            log_dir = os.path.join(voicemode_dir, 'logs', 'kokoro')
            os.makedirs(log_dir, exist_ok=True)
            
            plist_name = "com.voicemode.kokoro.plist"
            plist_path = os.path.join(launchagents_dir, plist_name)
            
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro</string>
    <key>ProgramArguments</key>
    <array>
        <string>{start_script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{install_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.error.log')}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.path.expanduser("~/.local/bin")}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>"""
            
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            
            # Unload if already loaded (ignore errors)
            try:
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
            except:
                pass  # Ignore if not loaded
            
            # Don't load here - let enable_service handle it with the -w flag
            # This prevents the "already loaded" error when enable_service runs
            result["launchagent"] = plist_path
            result["message"] += f"\nLaunchAgent installed: {plist_name}"
            
            # Handle auto_enable
            enable_message = ""
            if auto_enable is None:
                auto_enable = SERVICE_AUTO_ENABLE
            
            if auto_enable:
                logger.info("Auto-enabling kokoro service...")
                from voice_mode.tools.service import enable_service
                enable_result = await enable_service("kokoro")
                if "✅" in enable_result:
                    enable_message = " Service auto-enabled."
                else:
                    logger.warning(f"Auto-enable failed: {enable_result}")
                result["message"] += enable_message
        
        # Install systemd service on Linux
        elif system == "Linux":
            logger.info("Installing systemd user service for kokoro-fastapi...")
            systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(systemd_user_dir, exist_ok=True)
            
            # Create log directory
            log_dir = os.path.join(voicemode_dir, 'logs', 'kokoro')
            os.makedirs(log_dir, exist_ok=True)
            
            service_name = "voicemode-kokoro.service"
            service_path = os.path.join(systemd_user_dir, service_name)
            
            service_content = f"""[Unit]
Description=VoiceMode Kokoro TTS Service
After=network.target

[Service]
Type=simple
ExecStart={start_script_path}
Restart=on-failure
RestartSec=10
WorkingDirectory={install_dir}
StandardOutput=append:{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.log')}
StandardError=append:{os.path.join(voicemode_dir, 'logs', 'kokoro', 'kokoro.error.log')}
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/home/m/.local/bin"

[Install]
WantedBy=default.target
"""
            
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd and enable service
            try:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
                subprocess.run(["systemctl", "--user", "start", service_name], check=True)
                
                result["systemd_service"] = service_path
                result["systemd_enabled"] = True
                result["message"] += f"\nSystemd service installed and started: {service_name}"
                result["service_status"] = "managed_by_systemd"
            except subprocess.CalledProcessError as e:
                result["systemd_service"] = service_path
                result["systemd_enabled"] = False
                result["message"] += f"\nSystemd service created but not started: {e}"
                logger.warning(f"Systemd service error: {e}")
            
            # Handle auto_enable
            enable_message = ""
            if auto_enable is None:
                auto_enable = SERVICE_AUTO_ENABLE
            
            if auto_enable:
                logger.info("Auto-enabling kokoro service...")
                from voice_mode.tools.service import enable_service
                enable_result = await enable_service("kokoro")
                if "✅" in enable_result:
                    enable_message = " Service auto-enabled."
                else:
                    logger.warning(f"Auto-enable failed: {enable_result}")
                result["message"] += enable_message
        
        # Start service if requested (skip if launchagent or systemd was installed)
        if auto_start and system not in ["Darwin", "Linux"]:
            logger.info("Starting kokoro-fastapi service...")
            # Start in background
            process = subprocess.Popen(
                ["bash", start_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait a moment for service to start
            await asyncio.sleep(3)
            
            # Check if service is running
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{port}/health") as response:
                        if response.status == 200:
                            result["service_status"] = "running"
                            result["service_pid"] = process.pid
                        else:
                            result["service_status"] = "failed"
                            result["error"] = "Health check failed"
            except:
                result["service_status"] = "failed"
                result["error"] = "Could not connect to service"
        elif system == "Darwin" and "launchagent" in result:
            result["service_status"] = "managed_by_launchd"
        elif system == "Linux" and "systemd_enabled" in result and result["systemd_enabled"]:
            # Service status already set to "managed_by_systemd" in the systemd section
            pass
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