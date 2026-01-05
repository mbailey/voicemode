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
                # Check for appropriate start script
                if has_gpu_support():
                    # Prefer GPU script, fallback to general start
                    possible_scripts = [
                        path / "start-gpu.sh"
                    ]
                else:
                    # Prefer CPU script, fallback to general start
                    possible_scripts = [
                        path / "start-cpu.sh"
                    ]
                
                # Find first existing script
                start_script = next((script for script in possible_scripts if script.exists()), None)
            
            if start_script and start_script.exists():
                return str(path)
    
    return None


def has_gpu_support() -> bool:
    """Check if the system has GPU support for Kokoro.

    This is a wrapper around the shared GPU detection utility.
    """
    return _has_gpu_support()


def is_kokoro_starting_up() -> Optional[str]:
    """Check if Kokoro is in the process of starting up (downloading models, etc).

    Returns a status message if Kokoro is starting, None otherwise.
    """
    import psutil

    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.cmdline()
                if not cmdline:
                    continue
                cmdline_str = ' '.join(cmdline).lower()

                # Check for model download script
                if 'download_model' in cmdline_str and 'kokoro' in cmdline_str:
                    return "downloading models (this may take a few minutes)"

                # Check for Kokoro uvicorn startup
                if 'uvicorn' in cmdline_str and 'kokoro' in cmdline_str:
                    # Process exists but port not listening - still loading
                    return "loading models (please wait)"

                # Check for start script running
                if 'start-gpu_mac.sh' in cmdline_str or 'start-cpu.sh' in cmdline_str or 'start-gpu.sh' in cmdline_str:
                    if 'kokoro' in cmdline_str:
                        return "starting up"

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    return None
