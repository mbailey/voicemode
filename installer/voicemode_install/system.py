"""System detection and platform utilities."""

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PlatformInfo:
    """Information about the current platform."""

    os_type: str  # darwin, linux, windows
    os_name: str  # macOS, Ubuntu, Fedora, etc.
    distribution: str  # debian, fedora, darwin, etc. (for yaml lookup)
    architecture: str  # arm64, x86_64
    is_wsl: bool = False
    is_ostree: bool = False  # Fedora Atomic: Silverblue, Kinoite, Bazzite, Bluefin...


def is_ostree_system() -> bool:
    """Detect an rpm-ostree / Fedora Atomic system (Silverblue, Bazzite, Bluefin...).

    These report ID=fedora in /etc/os-release but have a read-only /usr and no
    working ``dnf install`` -- Bazzite ships a dnf shim that refuses install
    outright. Packages are layered with ``rpm-ostree install`` (requires a
    reboot) or, preferably, installed with Homebrew or in a distrobox.

    /run/ostree-booted is created by ostree at boot and is the canonical marker.
    """
    return Path('/run/ostree-booted').exists() or Path('/sysroot/ostree').is_dir()


def get_homebrew_prefix() -> Optional[Path]:
    """Return the Homebrew prefix if Homebrew is installed, else None.

    Homebrew on Linux is a first-class way to get development headers on an
    immutable OS, since it installs under $HOME or /home/linuxbrew and needs
    neither root nor a reboot.
    """
    brew = shutil.which('brew')
    if not brew:
        for candidate in (Path('/home/linuxbrew/.linuxbrew'), Path.home() / '.linuxbrew'):
            if (candidate / 'bin' / 'brew').exists():
                return candidate
        return None
    try:
        result = subprocess.run(
            [brew, '--prefix'], capture_output=True, text=True, check=True, timeout=10
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def detect_platform() -> PlatformInfo:
    """Detect the current platform and return platform information."""
    os_type = platform.system().lower()
    architecture = platform.machine().lower()

    # Normalize architecture names
    if architecture in ('amd64', 'x86_64', 'x64'):
        architecture = 'x86_64'
    elif architecture in ('aarch64', 'arm64'):
        architecture = 'arm64'

    # Detect WSL
    is_wsl = False
    if os_type == 'linux':
        try:
            with open('/proc/version', 'r') as f:
                is_wsl = 'microsoft' in f.read().lower() or 'wsl' in f.read().lower()
        except FileNotFoundError:
            pass

    if os_type == 'darwin':
        return PlatformInfo(
            os_type='darwin',
            os_name='macOS',
            distribution='darwin',
            architecture=architecture,
            is_wsl=False
        )
    elif os_type == 'linux':
        # Detect Linux distribution
        distro_info = _detect_linux_distro()
        return PlatformInfo(
            os_type='linux',
            os_name=distro_info['name'],
            distribution=distro_info['family'],
            architecture=architecture,
            is_wsl=is_wsl,
            is_ostree=is_ostree_system()
        )
    else:
        raise RuntimeError(f"Unsupported operating system: {os_type}")


def _detect_linux_distro() -> dict:
    """Detect Linux distribution and family."""
    # Try /etc/os-release first (most modern distros)
    if Path('/etc/os-release').exists():
        os_release = {}
        with open('/etc/os-release') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os_release[key] = value.strip('"')

        distro_id = os_release.get('ID', '').lower()
        distro_id_like = os_release.get('ID_LIKE', '').lower()
        distro_name = os_release.get('NAME', 'Linux')

        # Determine family for yaml lookup
        if distro_id in ('ubuntu', 'debian') or 'debian' in distro_id_like or 'ubuntu' in distro_id_like:
            return {'name': distro_name, 'family': 'debian'}
        elif distro_id in ('fedora', 'rhel', 'centos', 'rocky', 'alma') or 'fedora' in distro_id_like or 'rhel' in distro_id_like:
            return {'name': distro_name, 'family': 'fedora'}
        elif distro_id == 'arch' or 'arch' in distro_id_like:
            return {'name': distro_name, 'family': 'arch'}
        elif distro_id == 'alpine':
            return {'name': distro_name, 'family': 'alpine'}
        elif distro_id in ('opensuse', 'suse') or 'suse' in distro_id_like:
            return {'name': distro_name, 'family': 'suse'}
        else:
            # Try to infer from ID_LIKE
            if 'debian' in distro_id_like:
                return {'name': distro_name, 'family': 'debian'}
            elif 'fedora' in distro_id_like or 'rhel' in distro_id_like:
                return {'name': distro_name, 'family': 'fedora'}

    # Fallback: check for package managers
    if Path('/usr/bin/apt').exists() or Path('/usr/bin/apt-get').exists():
        return {'name': 'Debian-based Linux', 'family': 'debian'}
    elif Path('/usr/bin/dnf').exists() or Path('/usr/bin/yum').exists():
        return {'name': 'Fedora-based Linux', 'family': 'fedora'}

    raise RuntimeError("Unable to detect Linux distribution")


def get_package_manager(distribution: str, is_ostree: bool = False) -> str:
    """Get the package manager command for the distribution.

    On Fedora Atomic (ostree) the answer is never ``dnf`` -- prefer Homebrew,
    which needs no root and no reboot, and fall back to ``rpm-ostree``.
    """
    if distribution == 'fedora' and is_ostree:
        return 'brew' if get_homebrew_prefix() else 'rpm-ostree'

    if distribution == 'darwin':
        return 'brew'
    elif distribution == 'debian':
        return 'apt'
    elif distribution == 'fedora':
        return 'dnf'
    elif distribution == 'arch':
        return 'pacman'
    elif distribution == 'alpine':
        return 'apk'
    elif distribution == 'suse':
        return 'zypper'
    else:
        raise ValueError(f"Unknown distribution: {distribution}")


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None


def check_homebrew_installed() -> bool:
    """Check if Homebrew is installed (macOS only)."""
    return check_command_exists('brew')


def get_system_info() -> dict:
    """Get comprehensive system information for logging."""
    platform_info = detect_platform()

    return {
        'os_type': platform_info.os_type,
        'os_name': platform_info.os_name,
        'distribution': platform_info.distribution,
        'architecture': platform_info.architecture,
        'is_wsl': platform_info.is_wsl,
        'is_ostree': platform_info.is_ostree,
        'homebrew_prefix': str(get_homebrew_prefix() or ''),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
    }
