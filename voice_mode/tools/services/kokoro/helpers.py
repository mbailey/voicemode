"""Helper functions for kokoro service management."""

import platform
from pathlib import Path
from typing import Optional


def find_kokoro_fastapi() -> Optional[str]:
    """Find the kokoro-fastapi installation directory."""
    # Check common installation paths
    paths_to_check = [
        Path.home() / ".voicemode" / "kokoro-fastapi",
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