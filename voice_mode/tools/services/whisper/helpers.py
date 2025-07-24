"""Helper functions for whisper service management."""

import subprocess
from pathlib import Path
from typing import Optional

def find_whisper_server() -> Optional[str]:
    """Find the whisper-server binary."""
    # Check common installation paths
    paths_to_check = [
        Path.home() / ".voicemode" / "whisper.cpp" / "whisper-server",
        Path.home() / ".voicemode" / "whisper.cpp" / "server",
        Path("/usr/local/bin/whisper-server"),
        Path("/opt/homebrew/bin/whisper-server"),
    ]
    
    for path in paths_to_check:
        if path.exists() and path.is_file():
            return str(path)
    
    # Try to find in PATH
    result = subprocess.run(["which", "whisper-server"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    
    return None


def find_whisper_model() -> Optional[str]:
    """Find a whisper model file."""
    from voice_mode.config import WHISPER_MODEL_PATH
    
    # Check configured model path
    model_dir = Path(WHISPER_MODEL_PATH)
    if model_dir.exists():
        # Look for ggml model files
        for model_file in model_dir.glob("ggml-*.bin"):
            return str(model_file)
    
    # Check default installation path
    default_path = Path.home() / ".voicemode" / "whisper.cpp" / "models"
    if default_path.exists():
        for model_file in default_path.glob("ggml-*.bin"):
            return str(model_file)
    
    return None