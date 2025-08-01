"""Helper functions for kokoro service management."""

import platform
import subprocess
from pathlib import Path
from typing import Optional

from voice_mode.utils.gpu_detection import has_gpu_support as _has_gpu_support


def find_kokoro_fastapi() -> Optional[str]:
    """Find the kokoro-fastapi installation directory."""
    # Check common installation paths
    paths_to_check = [
        Path.home() / ".voicemode" / "services" / "kokoro",  # New location
        Path.home() / ".voicemode" / "kokoro-fastapi",  # Legacy location
        Path.home() / "kokoro-fastapi",
        Path("/opt/kokoro-fastapi"),
    ]
    
    for path in paths_to_check:
        if path.exists() and path.is_dir():
            # Look for start scripts
            if platform.system() == "Darwin":
                start_script = path / "start-gpu_mac.sh"
            else:
                start_script = path / "start.sh"
            
            if start_script.exists():
                return str(path)
    
    return None


def has_gpu_support() -> bool:
    """Check if the system has GPU support for Kokoro.
    
    This is a wrapper around the shared GPU detection utility.
    """
    return _has_gpu_support()