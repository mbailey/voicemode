"""Uninstallation tool for LiveKit server"""

import os
import sys
import platform
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Union
import asyncio

from voice_mode.server import mcp
from voice_mode.tools.service import stop_service, disable_service, uninstall_service

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def livekit_uninstall(
    remove_config: Union[bool, str] = False,
    remove_all_data: Union[bool, str] = False
) -> Dict[str, Any]:
    """
    Uninstall LiveKit server and optionally remove configuration and data.
    
    This tool will:
    1. Stop any running LiveKit service
    2. Remove service configurations (launchd/systemd)
    3. Remove the LiveKit installation
    4. Optionally remove configuration files
    5. Optionally remove all LiveKit-related data
    
    Args:
        remove_config: Also remove LiveKit configuration files (default: False)
        remove_all_data: Remove all LiveKit data including logs (default: False)
    
    Returns:
        Dictionary with uninstall status and details
    """
    try:
        # Handle string boolean conversions
        if isinstance(remove_config, str):
            remove_config = remove_config.lower() in ("true", "1", "yes", "on")
        if isinstance(remove_all_data, str):
            remove_all_data = remove_all_data.lower() in ("true", "1", "yes", "on")
        
        removed_items = []
        warnings = []
        
        # Base directories
        voicemode_dir = Path.home() / ".voicemode"
        install_dir = voicemode_dir / "services" / "livekit"
        
        # Stop the service first
        logger.info("Stopping LiveKit service...")
        stop_result = await stop_service("livekit")
        if stop_result["success"]:
            removed_items.append("Stopped LiveKit service")
        else:
            warnings.append(f"Could not stop service: {stop_result.get('message', 'Unknown error')}")
        
        # Disable service
        logger.info("Disabling LiveKit service...")
        disable_result = await disable_service("livekit")
        if disable_result["success"]:
            removed_items.append("Disabled LiveKit service")
        
        # Uninstall service files
        logger.info("Removing service files...")
        uninstall_result = await uninstall_service("livekit")
        if uninstall_result["success"]:
            removed_items.append("Removed service files")
        else:
            warnings.append(f"Could not remove service files: {uninstall_result.get('message', 'Unknown error')}")
        
        # Remove installation directory
        if install_dir.exists():
            logger.info(f"Removing LiveKit installation from {install_dir}")
            shutil.rmtree(install_dir)
            removed_items.append(f"Removed installation directory: {install_dir}")
        
        # Handle Homebrew installation on macOS
        system = platform.system()
        if system == "Darwin" and shutil.which("brew"):
            # Check if LiveKit was installed via Homebrew
            try:
                result = subprocess.run(
                    ["brew", "list", "livekit"],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    logger.info("LiveKit was installed via Homebrew")
                    warnings.append("LiveKit installed via Homebrew - run 'brew uninstall livekit' to fully remove")
            except Exception:
                pass
        
        # Remove logs if requested
        if remove_all_data:
            log_dir = voicemode_dir / "logs" / "livekit"
            if log_dir.exists():
                logger.info(f"Removing LiveKit logs from {log_dir}")
                shutil.rmtree(log_dir)
                removed_items.append(f"Removed log directory: {log_dir}")
        
        # Remove any LiveKit-related environment files
        if remove_config:
            # Check for .env files
            env_file = voicemode_dir / ".livekit.env"
            if env_file.exists():
                env_file.unlink()
                removed_items.append(f"Removed environment file: {env_file}")
        
        # Summary
        success = len(removed_items) > 0
        
        if success:
            message = "LiveKit uninstallation completed"
            if warnings:
                message += f" with {len(warnings)} warning(s)"
        else:
            message = "No LiveKit installation found"
        
        return {
            "success": success,
            "message": message,
            "removed_items": removed_items,
            "warnings": warnings,
            "remove_config": remove_config,
            "remove_all_data": remove_all_data
        }
        
    except Exception as e:
        logger.error(f"LiveKit uninstallation failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Uninstallation failed: {str(e)}",
            "removed_items": removed_items if 'removed_items' in locals() else [],
            "warnings": warnings if 'warnings' in locals() else []
        }


# CLI entry point
async def main():
    """CLI entry point for testing"""
    import sys
    
    # Parse command line arguments
    remove_config = "--remove-config" in sys.argv
    remove_all = "--remove-all" in sys.argv
    
    result = await livekit_uninstall(
        remove_config=remove_config or remove_all,
        remove_all_data=remove_all
    )
    
    print("\nLiveKit Uninstallation Results:")
    print("=" * 40)
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    
    if result.get('removed_items'):
        print("\nRemoved items:")
        for item in result['removed_items']:
            print(f"  ✓ {item}")
    
    if result.get('warnings'):
        print("\nWarnings:")
        for warning in result['warnings']:
            print(f"  ⚠ {warning}")
    
    if result.get('error'):
        print(f"\nError: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())