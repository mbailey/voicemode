"""Parakeet model registry and utilities."""

import os
from pathlib import Path
from typing import Dict, TypedDict


class ParakeetModelInfo(TypedDict):
    """Information about a Parakeet model."""
    id: str  # HuggingFace model ID
    size_mb: int  # Approximate model size in MB
    languages: str  # Language support description
    description: str  # Brief description


# Registry of available Parakeet models
# Parakeet uses MLX versions from HuggingFace, auto-downloaded on first use
PARAKEET_MODEL_REGISTRY: Dict[str, ParakeetModelInfo] = {
    "parakeet-tdt-0.6b-v3": {
        "id": "mlx-community/parakeet-tdt-0.6b-v3",
        "size_mb": 600,
        "languages": "Multilingual (auto-detect)",
        "description": "Fast, accurate ASR with automatic language detection"
    },
}

# Default model
DEFAULT_PARAKEET_MODEL = "parakeet-tdt-0.6b-v3"

# Default port (different from Whisper's 2022)
PARAKEET_PORT = 2023


def get_parakeet_install_dir() -> Path:
    """Get the Parakeet service installation directory."""
    return Path.home() / ".voicemode" / "services" / "parakeet"


def is_parakeet_installed() -> bool:
    """Check if Parakeet service is installed."""
    install_dir = get_parakeet_install_dir()
    server_py = install_dir / "server.py"
    venv = install_dir / ".venv"
    return server_py.exists() and venv.exists()


def get_parakeet_venv_python() -> Path:
    """Get the path to the Parakeet venv's Python interpreter."""
    return get_parakeet_install_dir() / ".venv" / "bin" / "python"
