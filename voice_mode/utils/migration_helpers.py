"""Helper functions for migrating old service installations."""

import os
import subprocess
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("voice-mode")


def check_old_whisper_installations() -> List[Path]:
    """Check for old whisper service installations."""
    old_files = []
    
    if os.uname().sysname == "Darwin":
        launchd_dir = Path.home() / "Library" / "LaunchAgents"
        old_names = [
            "com.voicemode.whisper-server.plist",
            "com.whisper.server.plist"
        ]
        for name in old_names:
            path = launchd_dir / name
            if path.exists():
                old_files.append(path)
    
    elif os.uname().sysname == "Linux":
        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        old_names = ["whisper-server.service"]
        for name in old_names:
            path = systemd_dir / name
            if path.exists():
                old_files.append(path)
    
    return old_files


def check_old_kokoro_installations() -> List[Path]:
    """Check for old kokoro service installations."""
    old_files = []
    
    if os.uname().sysname == "Darwin":
        launchd_dir = Path.home() / "Library" / "LaunchAgents"
        # Check for any kokoro plist with port numbers
        for plist in launchd_dir.glob("com.voicemode.kokoro-*.plist"):
            old_files.append(plist)
    
    elif os.uname().sysname == "Linux":
        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        old_names = ["kokoro-fastapi.service"]
        for name in old_names:
            path = systemd_dir / name
            if path.exists():
                old_files.append(path)
    
    return old_files


def auto_migrate_if_needed(service_name: str) -> Optional[str]:
    """
    Automatically migrate old service files if found.
    
    Returns:
        Migration message if migration was performed, None otherwise
    """
    if service_name == "whisper":
        old_files = check_old_whisper_installations()
    elif service_name == "kokoro":
        old_files = check_old_kokoro_installations()
    else:
        return None
    
    if not old_files:
        return None
    
    logger.info(f"Found old {service_name} service files, migrating automatically...")
    
    migrated = []
    removed = []
    errors = []
    
    system = os.uname().sysname
    
    for old_path in old_files:
        try:
            if system == "Darwin":
                # Handle macOS launchd files
                if service_name == "whisper" and old_path.name in ["com.voicemode.whisper-server.plist", "com.whisper.server.plist"]:
                    # Unload old service
                    subprocess.run(["launchctl", "unload", str(old_path)], capture_output=True)
                    # Remove file
                    old_path.unlink()
                    removed.append(str(old_path))
                    logger.info(f"Removed old plist: {old_path}")
                    
                elif service_name == "kokoro" and "kokoro-" in old_path.name:
                    # Remove extra kokoro instances
                    subprocess.run(["launchctl", "unload", str(old_path)], capture_output=True)
                    old_path.unlink()
                    removed.append(str(old_path))
                    logger.info(f"Removed old plist: {old_path}")
                    
            elif system == "Linux":
                # Handle Linux systemd files
                old_name = old_path.name
                
                # Stop and disable old service
                subprocess.run(["systemctl", "--user", "stop", old_name], capture_output=True)
                subprocess.run(["systemctl", "--user", "disable", old_name], capture_output=True)
                
                # Remove file
                old_path.unlink()
                removed.append(str(old_path))
                logger.info(f"Removed old service: {old_path}")
                
                # Reload systemd
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
                
        except Exception as e:
            errors.append(f"Failed to migrate {old_path}: {e}")
            logger.warning(f"Failed to migrate {old_path}: {e}")
    
    if migrated or removed:
        migration_msg = f"Cleaned up old {service_name} service files: "
        if removed:
            migration_msg += f"{len(removed)} removed"
        if errors:
            migration_msg += f" ({len(errors)} errors)"
        return migration_msg
    
    return None