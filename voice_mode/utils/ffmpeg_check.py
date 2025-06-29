"""FFmpeg detection and installation helper for voice-mode."""

import os
import platform
import shutil
import subprocess
import sys
from typing import Optional, Tuple


def check_ffmpeg() -> Tuple[bool, Optional[str]]:
    """Check if FFmpeg is installed and accessible.
    
    Returns:
        Tuple of (is_installed, path_to_ffmpeg)
    """
    ffmpeg_path = shutil.which('ffmpeg')
    return (ffmpeg_path is not None, ffmpeg_path)


def check_ffprobe() -> Tuple[bool, Optional[str]]:
    """Check if ffprobe is installed and accessible.
    
    Returns:
        Tuple of (is_installed, path_to_ffprobe)
    """
    ffprobe_path = shutil.which('ffprobe')
    return (ffprobe_path is not None, ffprobe_path)


def get_ffmpeg_version() -> Optional[str]:
    """Get FFmpeg version if installed.
    
    Returns:
        Version string or None if not installed
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Extract version from first line
            first_line = result.stdout.split('\n')[0]
            if 'ffmpeg version' in first_line:
                return first_line.split('ffmpeg version')[1].split()[0]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def get_install_instructions() -> str:
    """Get platform-specific FFmpeg installation instructions.
    
    Returns:
        Installation instructions for the current platform
    """
    system = platform.system().lower()
    
    if system == 'darwin':  # macOS
        return """FFmpeg is required for audio processing but was not found.

To install FFmpeg on macOS:

1. Using Homebrew (recommended):
   brew install ffmpeg

2. Using MacPorts:
   sudo port install ffmpeg

If you don't have Homebrew, install it first:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

After installation, restart your terminal or reload your shell configuration."""
    
    elif system == 'linux':
        # Try to detect the Linux distribution
        distro_info = {}
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        distro_info[key] = value.strip('"')
        except FileNotFoundError:
            pass
        
        distro_id = distro_info.get('ID', '').lower()
        
        if distro_id in ['ubuntu', 'debian']:
            return """FFmpeg is required for audio processing but was not found.

To install FFmpeg on Ubuntu/Debian:

   sudo apt update
   sudo apt install ffmpeg

After installation, verify with: ffmpeg -version"""
        
        elif distro_id in ['fedora', 'rhel', 'centos']:
            return """FFmpeg is required for audio processing but was not found.

To install FFmpeg on Fedora/RHEL:

   sudo dnf install ffmpeg

For older versions using yum:
   sudo yum install ffmpeg

After installation, verify with: ffmpeg -version"""
        
        elif distro_id in ['arch', 'manjaro']:
            return """FFmpeg is required for audio processing but was not found.

To install FFmpeg on Arch Linux:

   sudo pacman -S ffmpeg

After installation, verify with: ffmpeg -version"""
        
        else:
            return """FFmpeg is required for audio processing but was not found.

To install FFmpeg on Linux, use your distribution's package manager:

- Ubuntu/Debian: sudo apt install ffmpeg
- Fedora/RHEL: sudo dnf install ffmpeg
- Arch Linux: sudo pacman -S ffmpeg
- OpenSUSE: sudo zypper install ffmpeg

After installation, verify with: ffmpeg -version"""
    
    elif system == 'windows':
        return """FFmpeg is required for audio processing but was not found.

For Windows users, we recommend using WSL2 (Windows Subsystem for Linux):

1. Install WSL2 if not already installed
2. Follow the Ubuntu/Debian instructions above

Alternatively, for native Windows:
1. Download FFmpeg from: https://www.ffmpeg.org/download.html
2. Extract the archive
3. Add the bin folder to your system PATH
4. Restart your terminal

Note: Voice Mode works best in WSL2 on Windows."""
    
    else:
        return f"""FFmpeg is required for audio processing but was not found.

Platform: {system}
Please install FFmpeg using your system's package manager or download from:
https://www.ffmpeg.org/download.html"""


def check_and_report_ffmpeg() -> bool:
    """Check FFmpeg installation and report status.
    
    Returns:
        True if FFmpeg is properly installed, False otherwise
    """
    ffmpeg_installed, ffmpeg_path = check_ffmpeg()
    ffprobe_installed, ffprobe_path = check_ffprobe()
    
    if not ffmpeg_installed or not ffprobe_installed:
        print("\n" + "="*60)
        print("⚠️  FFmpeg Installation Required")
        print("="*60)
        print(get_install_instructions())
        print("="*60 + "\n")
        return False
    
    # Both are installed, optionally report version
    version = get_ffmpeg_version()
    if version:
        # Only log this in debug mode
        import logging
        logger = logging.getLogger("voicemode")
        logger.debug(f"FFmpeg version {version} found at {ffmpeg_path}")
    
    return True


def ensure_ffmpeg_or_exit():
    """Ensure FFmpeg is installed or exit with helpful message."""
    if not check_and_report_ffmpeg():
        print("\n❌ Voice Mode cannot start without FFmpeg.")
        print("Please install FFmpeg and try again.\n")
        sys.exit(1)