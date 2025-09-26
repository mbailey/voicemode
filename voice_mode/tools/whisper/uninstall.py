"""Uninstall tool for Whisper STT service."""

import os
import shutil
import subprocess
import platform
import logging
from pathlib import Path
from typing import Dict, Any, Union

from voice_mode.server import mcp
from voice_mode.config import BASE_DIR
from voice_mode.utils.services.common import find_process_by_port

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_uninstall(
    remove_models: Union[bool, str] = False,
    remove_all_data: Union[bool, str] = False
) -> Dict[str, Any]:
    """Uninstall whisper.cpp and optionally remove models and data.
    
    This tool will:
    1. Stop any running Whisper service
    2. Remove service configurations (launchd/systemd)
    3. Remove the whisper.cpp installation
    4. Optionally remove downloaded models
    5. Optionally remove all Whisper-related data
    
    Args:
        remove_models: Also remove downloaded Whisper models (default: False)
        remove_all_data: Remove all Whisper data including logs and transcriptions (default: False)
    
    Returns:
        Dictionary with uninstall status and details
    """
    system = platform.system()
    removed_items = []
    errors = []
    
    try:
        # 1. Stop any running Whisper service
        logger.info("Checking for running Whisper service...")
        proc = find_process_by_port(2022)
        if proc:
            try:
                logger.info(f"Stopping Whisper service (PID: {proc.pid})...")
                proc.terminate()
                proc.wait(timeout=5)
                removed_items.append("Stopped running Whisper service")
            except Exception as e:
                logger.warning(f"Failed to stop Whisper service: {e}")
        
        # 2. Remove service configurations
        if system == "Darwin":
            # Remove launchd plist files (check both old and new names)
            plist_names = [
                "com.voicemode.whisper.plist",
                "com.voicemode.whisper-server.plist"  # Old name for compatibility
            ]
            
            for plist_name in plist_names:
                plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name
                if plist_path.exists():
                    try:
                        # Unload if loaded
                        subprocess.run(
                            ["launchctl", "unload", str(plist_path)],
                            capture_output=True
                        )
                        # Remove file
                        plist_path.unlink()
                        removed_items.append(f"Removed launchd configuration: {plist_name}")
                        logger.info(f"Removed {plist_path}")
                    except Exception as e:
                        errors.append(f"Failed to remove {plist_path}: {e}")
        
        elif system == "Linux":
            # Remove systemd service files
            service_names = [
                "voicemode-whisper.service",
                "whisper-server.service"  # Old name for compatibility
            ]
            
            systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
            for service_name in service_names:
                service_path = systemd_user_dir / service_name
                if service_path.exists():
                    try:
                        # Stop and disable service
                        subprocess.run(
                            ["systemctl", "--user", "stop", service_name],
                            capture_output=True,
                            stderr=subprocess.DEVNULL
                        )
                        subprocess.run(
                            ["systemctl", "--user", "disable", service_name],
                            capture_output=True,
                            stderr=subprocess.DEVNULL
                        )
                        # Remove file
                        service_path.unlink()
                        # Reload systemd
                        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                        removed_items.append(f"Removed systemd service: {service_name}")
                        logger.info(f"Removed {service_path}")
                    except Exception as e:
                        errors.append(f"Failed to remove {service_path}: {e}")
        
        # 3. Remove whisper.cpp installation
        # Check new location first, then legacy location
        whisper_dirs = [
            BASE_DIR / "services" / "whisper",  # New location
            BASE_DIR / "whisper.cpp"  # Legacy location
        ]
        
        for whisper_dir in whisper_dirs:
            if whisper_dir.exists():
                try:
                    shutil.rmtree(whisper_dir)
                    removed_items.append(f"Removed whisper.cpp installation: {whisper_dir}")
                    logger.info(f"Removed {whisper_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {whisper_dir}: {e}")
        
        # 4. Optionally remove models
        if remove_models:
            models_dir = BASE_DIR / "models" / "whisper"
            if models_dir.exists():
                try:
                    shutil.rmtree(models_dir)
                    removed_items.append(f"Removed Whisper models: {models_dir}")
                    logger.info(f"Removed {models_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {models_dir}: {e}")
        
        # 5. Optionally remove all data
        if remove_all_data:
            # Remove logs
            log_files = [
                BASE_DIR / "logs" / "whisper" / "whisper.out.log",  # New location
                BASE_DIR / "logs" / "whisper" / "whisper.err.log",  # New location
                BASE_DIR / "logs" / "whisper.out.log",  # Legacy location
                BASE_DIR / "logs" / "whisper.err.log",  # Legacy location
                BASE_DIR / "whisper-server.log",
                BASE_DIR / "whisper-server.stdout.log",
                BASE_DIR / "whisper-server.stderr.log",
                BASE_DIR / "whisper-server.error.log"
            ]
            
            # Also remove the whisper logs directory if empty
            whisper_log_dir = BASE_DIR / "logs" / "whisper"
            
            for log_file in log_files:
                if log_file.exists():
                    try:
                        log_file.unlink()
                        removed_items.append(f"Removed log file: {log_file.name}")
                    except Exception as e:
                        errors.append(f"Failed to remove {log_file}: {e}")
            
            # Remove any whisper-specific transcriptions
            transcriptions_dir = BASE_DIR / "transcriptions"
            if transcriptions_dir.exists():
                for file in transcriptions_dir.glob("whisper_*.txt"):
                    try:
                        file.unlink()
                        removed_items.append(f"Removed transcription: {file.name}")
                    except Exception as e:
                        errors.append(f"Failed to remove {file}: {e}")
        
        # Prepare response
        success = len(errors) == 0
        
        if success:
            message = "Whisper has been successfully uninstalled"
            if remove_models:
                message += " (including models)"
            if remove_all_data:
                message += " (including all data)"
        else:
            message = "Whisper uninstall completed with some errors"
        
        return {
            "success": success,
            "message": message,
            "removed_items": removed_items,
            "errors": errors,
            "summary": {
                "items_removed": len(removed_items),
                "errors_encountered": len(errors)
            }
        }
        
    except Exception as e:
        logger.error(f"Unexpected error during Whisper uninstall: {e}")
        return {
            "success": False,
            "message": f"Failed to uninstall Whisper: {str(e)}",
            "removed_items": removed_items,
            "errors": errors + [str(e)],
            "summary": {
                "items_removed": len(removed_items),
                "errors_encountered": len(errors) + 1
            }
        }