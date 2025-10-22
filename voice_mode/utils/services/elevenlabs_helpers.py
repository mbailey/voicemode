"""Helper functions for elevenlabs service management.

The ElevenLabs proxy is expected to be installed separately from:
https://github.com/dotCipher/elevenlabs-openai-proxy

This module helps locate and manage the externally installed proxy.
"""

import subprocess
from pathlib import Path
from typing import Optional


def find_elevenlabs_proxy() -> Optional[str]:
    """Find the elevenlabs-openai-proxy installation directory.

    Installation instructions:
    1. Clone: git clone https://github.com/dotCipher/elevenlabs-openai-proxy.git ~/.voicemode/services/elevenlabs
    2. Install: cd ~/.voicemode/services/elevenlabs && make install
    3. Configure: Edit ~/.voicemode/services/elevenlabs/.env with your ELEVENLABS_API_KEY
    """
    # Check common installation paths
    paths_to_check = [
        Path.home() / ".voicemode" / "services" / "elevenlabs",  # Recommended location
        Path.home() / "elevenlabs-openai-proxy",  # Standalone installation
        Path("/opt/elevenlabs-openai-proxy"),  # System-wide installation
    ]

    for path in paths_to_check:
        if path.exists() and path.is_dir():
            # Check for server.py and venv
            server_file = path / "server.py"
            venv_exists = (path / "venv" / "bin" / "python").exists()

            if server_file.exists() and venv_exists:
                return str(path)

    return None
