"""Enable tool for Whisper speech-to-text service."""

import platform
import subprocess
import logging
from pathlib import Path

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT
from .helpers import find_whisper_server, find_whisper_model

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_enable() -> str:
    """Enable Whisper service to start automatically at system startup.
    
    On macOS: Creates and loads a LaunchAgent
    On Linux: Creates and enables a systemd user service
    
    Returns:
        Status message indicating success or failure
    """
    try:
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # LaunchAgent configuration
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.whisper.plist"
            
            # Find whisper-server binary
            whisper_bin = find_whisper_server()
            if not whisper_bin:
                return "❌ whisper-server not found. Please run whisper_install first."
            
            # Find model
            model_file = find_whisper_model()
            if not model_file:
                return "❌ No Whisper model found. Please run whisper_install first."
            
            # Create plist content
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.whisper</string>
    <key>ProgramArguments</key>
    <array>
        <string>{whisper_bin}</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>{WHISPER_PORT}</string>
        <string>--model</string>
        <string>{model_file}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.voicemode/logs/whisper.out.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.voicemode/logs/whisper.err.log</string>
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
                return f"✅ Whisper service enabled. It will start automatically at login.\nPlist: {plist_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable Whisper service: {error}"
                
        elif system == "Linux":
            # systemd configuration
            service_path = Path.home() / ".config" / "systemd" / "user" / "whisper.service"
            
            # Find whisper-server binary
            whisper_bin = find_whisper_server()
            if not whisper_bin:
                return "❌ whisper-server not found. Please run whisper_install first."
            
            # Find model
            model_file = find_whisper_model()
            if not model_file:
                return "❌ No Whisper model found. Please run whisper_install first."
            
            # Create service content
            service_content = f"""[Unit]
Description=Whisper Speech-to-Text Service
After=network.target

[Service]
Type=simple
ExecStart={whisper_bin} --host 0.0.0.0 --port {WHISPER_PORT} --model {model_file}
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
                ["systemctl", "--user", "enable", "whisper.service"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Also start it now
                subprocess.run(["systemctl", "--user", "start", "whisper.service"], check=True)
                return f"✅ Whisper service enabled and started.\nService: {service_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable Whisper service: {error}"
                
        else:
            return f"❌ Unsupported operating system: {system}"
            
    except Exception as e:
        logger.error(f"Error enabling Whisper service: {e}")
        return f"❌ Error enabling Whisper service: {str(e)}"