"""Enable tool for Kokoro text-to-speech service."""

import platform
import subprocess
import logging
from pathlib import Path

from voice_mode.server import mcp
from .helpers import find_kokoro_fastapi

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def kokoro_enable() -> str:
    """Enable Kokoro service to start automatically at system startup.
    
    On macOS: Creates and loads a LaunchAgent
    On Linux: Creates and enables a systemd user service
    
    Returns:
        Status message indicating success or failure
    """
    try:
        system = platform.system()
        
        # Find kokoro-fastapi installation
        kokoro_dir = find_kokoro_fastapi()
        if not kokoro_dir:
            return "❌ kokoro-fastapi not found. Please run kokoro_install first."
        
        if system == "Darwin":  # macOS
            # LaunchAgent configuration
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.kokoro.plist"
            start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
            
            if not start_script.exists():
                return f"❌ Start script not found: {start_script}"
            
            # Create plist content
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro</string>
    <key>ProgramArguments</key>
    <array>
        <string>{start_script}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{kokoro_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.voicemode/logs/kokoro.out.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.voicemode/logs/kokoro.err.log</string>
</dict>
</plist>"""
            
            # Create logs directory
            logs_dir = Path.home() / ".voicemode" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Write plist file
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_path.write_text(plist_content)
            
            # Load the LaunchAgent
            result = subprocess.run(
                ["launchctl", "load", "-w", str(plist_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return f"✅ Kokoro service enabled. It will start automatically at login.\nPlist: {plist_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable Kokoro service: {error}"
                
        elif system == "Linux":
            # systemd configuration
            service_path = Path.home() / ".config" / "systemd" / "user" / "kokoro.service"
            start_script = Path(kokoro_dir) / "start.sh"
            
            if not start_script.exists():
                return f"❌ Start script not found: {start_script}"
            
            # Create service content
            service_content = f"""[Unit]
Description=Kokoro Text-to-Speech Service
After=network.target

[Service]
Type=simple
WorkingDirectory={kokoro_dir}
ExecStart={start_script}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target"""
            
            # Write service file
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(service_content)
            
            # Reload systemd and enable service
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "enable", "kokoro.service"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Also start it now
                subprocess.run(["systemctl", "--user", "start", "kokoro.service"], check=True)
                return f"✅ Kokoro service enabled and started.\nService: {service_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable Kokoro service: {error}"
                
        else:
            return f"❌ Unsupported operating system: {system}"
            
    except Exception as e:
        logger.error(f"Error enabling Kokoro service: {e}")
        return f"❌ Error enabling Kokoro service: {str(e)}"