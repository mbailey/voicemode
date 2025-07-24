"""Disable tool for Whisper speech-to-text service."""

import platform
import subprocess
import logging
from pathlib import Path

from voice_mode.server import mcp

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_disable() -> str:
    """Disable Whisper service from starting automatically at system startup.
    
    On macOS: Unloads and removes the LaunchAgent
    On Linux: Disables and stops the systemd service
    
    Returns:
        Status message indicating success or failure
    """
    try:
        system = platform.system()
        
        if system == "Darwin":  # macOS
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.whisper.plist"
            
            if not plist_path.exists():
                return "Whisper service is not enabled (no LaunchAgent found)"
            
            # Unload the LaunchAgent
            result = subprocess.run(
                ["launchctl", "unload", "-w", str(plist_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Remove the plist file
                plist_path.unlink()
                return "✅ Whisper service disabled. It will not start automatically."
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to disable Whisper service: {error}"
                
        elif system == "Linux":
            # Stop and disable systemd service
            subprocess.run(["systemctl", "--user", "stop", "whisper.service"], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "disable", "whisper.service"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                service_path = Path.home() / ".config" / "systemd" / "user" / "whisper.service"
                if service_path.exists():
                    service_path.unlink()
                return "✅ Whisper service stopped and disabled."
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to disable Whisper service: {error}"
                
        else:
            return f"❌ Unsupported operating system: {system}"
            
    except Exception as e:
        logger.error(f"Error disabling Whisper service: {e}")
        return f"❌ Error disabling Whisper service: {str(e)}"