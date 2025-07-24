"""Installation tool for kokoro-fastapi TTS service."""

import os
import sys
import platform
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
import aiohttp

from voice_mode.server import mcp

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def kokoro_install(
    install_dir: Optional[str] = None,
    models_dir: Optional[str] = None,
    port: int = 8880,
    auto_start: bool = True,
    install_models: bool = True,
    force_reinstall: bool = False
) -> Dict[str, Any]:
    """
    Install and setup remsky/kokoro-fastapi TTS service using the simple 3-step approach.
    
    1. Clones the repository to ~/.voicemode/kokoro-fastapi
    2. Uses the appropriate start script (start-gpu_mac.sh on macOS)
    3. Installs a launchagent on macOS for automatic startup
    
    Args:
        install_dir: Directory to install kokoro-fastapi (default: ~/.voicemode/kokoro-fastapi)
        models_dir: Directory for Kokoro models (default: ~/.voicemode/kokoro-models) - not currently used
        port: Port to configure for the service (default: 8880)
        auto_start: Start the service after installation (ignored on macOS, uses launchd instead)
        install_models: Download Kokoro models (not used - handled by start script)
        force_reinstall: Force reinstallation even if already installed
    
    Returns:
        Installation status with service configuration details
    """
    try:
        # Set default directories under ~/.voicemode
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "kokoro-fastapi")
        else:
            install_dir = os.path.expanduser(install_dir)
            
        if models_dir is None:
            models_dir = os.path.join(voicemode_dir, "kokoro-models")
        else:
            models_dir = os.path.expanduser(models_dir)
        
        # Check if already installed
        if os.path.exists(install_dir) and not force_reinstall:
            if os.path.exists(os.path.join(install_dir, "main.py")):
                return {
                    "success": True,
                    "install_path": install_dir,
                    "models_path": models_dir,
                    "already_installed": True,
                    "message": "kokoro-fastapi already installed. Use force_reinstall=True to reinstall."
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
            logger.info("Cloning kokoro-fastapi repository...")
            subprocess.run([
                "git", "clone", "https://github.com/remsky/kokoro-fastapi.git", install_dir
            ], check=True)
        else:
            logger.info("Using existing kokoro-fastapi directory...")
        
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
            
        result = {
            "success": True,
            "install_path": install_dir,
            "service_url": f"http://127.0.0.1:{port}",
            "start_command": f"cd {install_dir} && ./{os.path.basename(start_script_path)}",
            "start_script": start_script_path,
            "message": f"Kokoro-fastapi installed. Run: cd {install_dir} && ./{os.path.basename(start_script_path)}"
        }
        
        # Install launchagent on macOS
        if system == "Darwin":
            logger.info("Installing launchagent for automatic startup...")
            launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launchagents_dir, exist_ok=True)
            
            plist_name = f"com.voicemode.kokoro-{port}.plist"
            plist_path = os.path.join(launchagents_dir, plist_name)
            
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro-{port}</string>
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
    <string>{os.path.join(voicemode_dir, f'kokoro-{port}.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, f'kokoro-{port}.error.log')}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>"""
            
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            
            # Load the launchagent
            try:
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
            except:
                pass  # Ignore if not loaded
            
            subprocess.run(["launchctl", "load", plist_path], check=True)
            result["launchagent"] = plist_path
            result["message"] += f"\nLaunchAgent installed: {plist_name}"
        
        # Install systemd service on Linux
        elif system == "Linux":
            logger.info("Installing systemd user service for kokoro-fastapi...")
            systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(systemd_user_dir, exist_ok=True)
            
            service_name = f"kokoro-fastapi-{port}.service"
            service_path = os.path.join(systemd_user_dir, service_name)
            
            service_content = f"""[Unit]
Description=Kokoro FastAPI TTS Service on port {port}
After=network.target

[Service]
Type=simple
ExecStart={start_script_path}
Restart=on-failure
RestartSec=10
WorkingDirectory={install_dir}
StandardOutput=append:{os.path.join(voicemode_dir, f'kokoro-fastapi-{port}.log')}
StandardError=append:{os.path.join(voicemode_dir, f'kokoro-fastapi-{port}.error.log')}
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