"""Uninstall tool for Kokoro TTS service."""

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
async def kokoro_uninstall(
    remove_models: Union[bool, str] = False,
    remove_all_data: Union[bool, str] = False
) -> Dict[str, Any]:
    """Uninstall kokoro-fastapi and optionally remove models and data.
    
    This tool will:
    1. Stop any running Kokoro service
    2. Remove service configurations (launchd/systemd)
    3. Remove the kokoro-fastapi installation
    4. Optionally remove downloaded Kokoro models
    5. Optionally remove all Kokoro-related data
    
    Args:
        remove_models: Also remove downloaded Kokoro models (default: False)
        remove_all_data: Remove all Kokoro data including logs and cache (default: False)
    
    Returns:
        Dictionary with uninstall status and details
    """
    system = platform.system()
    removed_items = []
    errors = []
    
    try:
        # 1. Stop any running Kokoro service
        logger.info("Checking for running Kokoro service...")
        proc = find_process_by_port(8880)
        if proc:
            try:
                logger.info(f"Stopping Kokoro service (PID: {proc.pid})...")
                proc.terminate()
                proc.wait(timeout=5)
                removed_items.append("Stopped running Kokoro service")
            except Exception as e:
                logger.warning(f"Failed to stop Kokoro service: {e}")
        
        # 2. Remove service configurations
        if system == "Darwin":
            # Remove launchd plist
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.kokoro.plist"
            if plist_path.exists():
                try:
                    # Unload if loaded
                    subprocess.run(
                        ["launchctl", "unload", str(plist_path)],
                        capture_output=True
                    )
                    # Remove file
                    plist_path.unlink()
                    removed_items.append("Removed launchd configuration")
                    logger.info(f"Removed {plist_path}")
                except Exception as e:
                    errors.append(f"Failed to remove {plist_path}: {e}")
            
            # Also check for any port-specific instances
            launchctl_result = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True
            )
            if launchctl_result.returncode == 0:
                for line in launchctl_result.stdout.splitlines():
                    if "com.voicemode.kokoro-" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            service_name = parts[2]
                            try:
                                subprocess.run(
                                    ["launchctl", "remove", service_name],
                                    capture_output=True
                                )
                                removed_items.append(f"Removed launchctl instance: {service_name}")
                            except Exception:
                                pass
        
        elif system == "Linux":
            # Remove systemd service
            service_path = Path.home() / ".config" / "systemd" / "user" / "voicemode-kokoro.service"
            if service_path.exists():
                try:
                    # Stop and disable service
                    subprocess.run(
                        ["systemctl", "--user", "stop", "voicemode-kokoro.service"],
                        capture_output=True
                    )
                    subprocess.run(
                        ["systemctl", "--user", "disable", "voicemode-kokoro.service"],
                        capture_output=True
                    )
                    # Remove file
                    service_path.unlink()
                    # Reload systemd
                    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                    removed_items.append("Removed systemd service")
                    logger.info(f"Removed {service_path}")
                except Exception as e:
                    errors.append(f"Failed to remove {service_path}: {e}")
        
        # 3. Remove kokoro-fastapi installation
        # Check new location first, then legacy location
        kokoro_dirs = [
            BASE_DIR / "services" / "kokoro",  # New location
            BASE_DIR / "kokoro-fastapi"  # Legacy location
        ]
        
        for kokoro_dir in kokoro_dirs:
            if kokoro_dir.exists():
                try:
                    shutil.rmtree(kokoro_dir)
                    removed_items.append(f"Removed kokoro-fastapi installation: {kokoro_dir}")
                    logger.info(f"Removed {kokoro_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {kokoro_dir}: {e}")
        
        # 4. Optionally remove models
        if remove_models:
            # Kokoro models directory
            models_dir = BASE_DIR / "models" / "kokoro"
            if models_dir.exists():
                try:
                    shutil.rmtree(models_dir)
                    removed_items.append(f"Removed Kokoro models: {models_dir}")
                    logger.info(f"Removed {models_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {models_dir}: {e}")
            
            # Also check for kokoro-models directory
            kokoro_models_dir = BASE_DIR / "kokoro-models"
            if kokoro_models_dir.exists():
                try:
                    shutil.rmtree(kokoro_models_dir)
                    removed_items.append(f"Removed Kokoro models: {kokoro_models_dir}")
                    logger.info(f"Removed {kokoro_models_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {kokoro_models_dir}: {e}")
        
        # 5. Optionally remove all data
        if remove_all_data:
            # Remove logs
            log_files = [
                BASE_DIR / "logs" / "kokoro.out.log",
                BASE_DIR / "logs" / "kokoro.err.log",
                BASE_DIR / "kokoro.log",
                BASE_DIR / "kokoro.stdout.log",
                BASE_DIR / "kokoro.stderr.log"
            ]
            
            for log_file in log_files:
                if log_file.exists():
                    try:
                        log_file.unlink()
                        removed_items.append(f"Removed log file: {log_file.name}")
                    except Exception as e:
                        errors.append(f"Failed to remove {log_file}: {e}")
            
            # Remove cache
            cache_dir = BASE_DIR / "cache" / "kokoro"
            if cache_dir.exists():
                try:
                    shutil.rmtree(cache_dir)
                    removed_items.append(f"Removed Kokoro cache: {cache_dir}")
                    logger.info(f"Removed {cache_dir}")
                except Exception as e:
                    errors.append(f"Failed to remove {cache_dir}: {e}")
            
            # Remove any kokoro-specific audio files
            audio_dir = BASE_DIR / "audio"
            if audio_dir.exists():
                for file in audio_dir.glob("kokoro_*.wav"):
                    try:
                        file.unlink()
                        removed_items.append(f"Removed audio file: {file.name}")
                    except Exception as e:
                        errors.append(f"Failed to remove {file}: {e}")
        
        # Prepare response
        success = len(errors) == 0
        
        if success:
            message = "Kokoro has been successfully uninstalled"
            if remove_models:
                message += " (including models)"
            if remove_all_data:
                message += " (including all data)"
        else:
            message = "Kokoro uninstall completed with some errors"
        
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
        logger.error(f"Unexpected error during Kokoro uninstall: {e}")
        return {
            "success": False,
            "message": f"Failed to uninstall Kokoro: {str(e)}",
            "removed_items": removed_items,
            "errors": errors + [str(e)],
            "summary": {
                "items_removed": len(removed_items),
                "errors_encountered": len(errors) + 1
            }
        }