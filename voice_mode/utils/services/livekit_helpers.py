"""Helper functions for LiveKit service management."""

import os
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voicemode")


def find_livekit_server() -> Optional[Path]:
    """Find LiveKit server binary in common locations.
    
    Returns:
        Path to livekit-server binary if found, None otherwise
    """
    # Check standard installation path first
    voicemode_dir = Path.home() / ".voicemode"
    livekit_bin = voicemode_dir / "services" / "livekit" / "livekit-server"
    if livekit_bin.exists() and livekit_bin.is_file():
        return livekit_bin
    
    # Check if installed via homebrew (macOS)
    brew_bin = shutil.which("livekit-server")
    if brew_bin:
        return Path(brew_bin)
    
    # Check system PATH
    system_bin = shutil.which("livekit-server")
    if system_bin:
        return Path(system_bin)
    
    # Check common installation locations
    common_paths = [
        Path("/usr/local/bin/livekit-server"),
        Path("/usr/bin/livekit-server"),
        Path("/opt/livekit/livekit-server"),
    ]
    
    for path in common_paths:
        if path.exists() and path.is_file():
            return path
    
    return None


def find_livekit_config() -> Optional[Path]:
    """Find LiveKit configuration file.
    
    Returns:
        Path to livekit.yaml if found, None otherwise
    """
    # Check standard location
    voicemode_dir = Path.home() / ".voicemode"
    config_file = voicemode_dir / "services" / "livekit" / "livekit.yaml"
    if config_file.exists():
        return config_file
    
    # Check common config locations
    common_paths = [
        Path("/etc/livekit/livekit.yaml"),
        Path.home() / ".livekit" / "livekit.yaml",
        Path.home() / ".config" / "livekit" / "livekit.yaml",
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    return None


def check_livekit_health(port: int = 7880) -> bool:
    """Check if LiveKit server is healthy.
    
    Args:
        port: LiveKit server port (default: 7880)
        
    Returns:
        True if server is healthy, False otherwise
    """
    try:
        import requests
        # LiveKit health endpoint
        response = requests.get(f"http://localhost:{port}/", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def get_livekit_version(binary_path: Optional[Path] = None) -> Optional[str]:
    """Get LiveKit server version.
    
    Args:
        binary_path: Path to livekit-server binary, will search if not provided
        
    Returns:
        Version string if available, None otherwise
    """
    if binary_path is None:
        binary_path = find_livekit_server()
    
    if not binary_path or not binary_path.exists():
        return None
    
    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # LiveKit outputs version like "livekit-server version 1.7.2"
            output = result.stdout.strip()
            if "version" in output:
                return output.split("version")[-1].strip()
            return output
    except Exception as e:
        logger.debug(f"Error getting LiveKit version: {e}")
    
    return None


def is_livekit_installed() -> bool:
    """Check if LiveKit is installed.
    
    Returns:
        True if LiveKit is installed, False otherwise
    """
    return find_livekit_server() is not None