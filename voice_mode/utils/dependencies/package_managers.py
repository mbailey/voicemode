"""Package manager abstraction for cross-platform dependency installation."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import os
import platform
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)


# dependencies.yaml lists Fedora RPM names. Homebrew formula names differ, so
# they must be translated before being handed to brew -- `brew install
# portaudio-devel` fails with "No available formula". Only names that exist in
# homebrew-core are listed; anything else is reported as unmappable.
RPM_TO_BREW = {
    'alsa-lib-devel': 'alsa-lib',
    'portaudio': 'portaudio',
    'portaudio-devel': 'portaudio',
    'SDL2-devel': 'sdl2',
    'ffmpeg': 'ffmpeg',
    'cmake': 'cmake',
    'make': 'make',
    'rust': 'rust',
    'cargo': 'rust',          # cargo ships inside the rust formula
    'gcc': 'gcc',
    'gcc-c++': 'gcc',
    'git': 'git',
}


# Homebrew had the shortest install timeout (300s) despite doing the heaviest
# work -- it downloads large bottles and falls back to building from source.
# The rust bottle alone is ~400MB, which exceeded 300s on an ordinary
# connection and killed the install partway through with no useful error.
BREW_INSTALL_TIMEOUT = 1800


def is_ostree_system() -> bool:
    """Detect an rpm-ostree / Fedora Atomic system (Silverblue, Bazzite, Bluefin).

    These have /etc/fedora-release but a read-only /usr and no working
    ``dnf install`` -- Bazzite ships a dnf shim that refuses install outright.
    """
    return os.path.exists("/run/ostree-booted") or os.path.isdir("/sysroot/ostree")


def get_homebrew_prefix() -> Optional[str]:
    """Return the Homebrew prefix if present, else None."""
    brew = shutil.which("brew")
    if brew:
        try:
            result = subprocess.run(
                [brew, "--prefix"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
    for candidate in ("/home/linuxbrew/.linuxbrew", os.path.expanduser("~/.linuxbrew")):
        if os.path.exists(os.path.join(candidate, "bin", "brew")):
            return candidate
    return None


def translate_to_brew(package_names: List[str]) -> Tuple[List[str], List[str]]:
    """Map Fedora RPM names to Homebrew formulae.

    Returns (formulae, unmappable). Formulae are de-duplicated because several
    RPMs collapse onto one formula (cargo and rust both -> rust).
    """
    formulae: List[str] = []
    unmappable: List[str] = []
    for name in package_names:
        formula = RPM_TO_BREW.get(name)
        if formula is None:
            unmappable.append(name)
        elif formula not in formulae:
            formulae.append(formula)
    return formulae, unmappable


class PackageManager(ABC):
    """Base class for package managers."""

    @abstractmethod
    def check_available(self) -> bool:
        """Check if this package manager is available."""
        pass

    @abstractmethod
    def check_package(self, package_name: str) -> bool:
        """Check if a package is installed."""
        pass

    @abstractmethod
    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        """Install packages. Returns (success, message)."""
        pass


class BrewManager(PackageManager):
    """Homebrew package manager (macOS)."""

    def check_available(self) -> bool:
        return shutil.which("brew") is not None

    def check_package(self, package_name: str) -> bool:
        try:
            result = subprocess.run(
                ["brew", "list", package_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Error checking package {package_name}: {e}")
            return False

    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        cmd = ["brew", "install"] + package_names
        try:
            if verbose:
                result = subprocess.run(cmd, text=True, timeout=BREW_INSTALL_TIMEOUT)
                return result.returncode == 0, ""
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=BREW_INSTALL_TIMEOUT)
                return result.returncode == 0, result.stderr or result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)


class AptManager(PackageManager):
    """APT package manager (Debian/Ubuntu)."""

    def check_available(self) -> bool:
        return shutil.which("apt-get") is not None

    def check_package(self, package_name: str) -> bool:
        try:
            result = subprocess.run(
                ["dpkg", "-l", package_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and "ii" in result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Error checking package {package_name}: {e}")
            return False

    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        # Need sudo for apt
        cmd = ["sudo", "apt-get", "install", "-y"] + package_names
        try:
            if verbose:
                result = subprocess.run(cmd, text=True, timeout=600)
                return result.returncode == 0, ""
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                return result.returncode == 0, result.stderr or result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)


class DnfManager(PackageManager):
    """DNF package manager (Fedora/RHEL)."""

    def check_available(self) -> bool:
        return shutil.which("dnf") is not None

    def check_package(self, package_name: str) -> bool:
        try:
            result = subprocess.run(
                ["rpm", "-q", package_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Error checking package {package_name}: {e}")
            return False

    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        # Need sudo for dnf
        cmd = ["sudo", "dnf", "install", "-y"] + package_names
        try:
            if verbose:
                result = subprocess.run(cmd, text=True, timeout=600)
                return result.returncode == 0, ""
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                return result.returncode == 0, result.stderr or result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)


class OstreeBrewManager(BrewManager):
    """Homebrew on Fedora Atomic, translating RPM names to formulae.

    dependencies.yaml supplies Fedora RPM names, which are not Homebrew formula
    names -- `brew install portaudio-devel` fails outright, and `cargo` has no
    formula at all because it ships inside `rust`.
    """

    def check_package(self, package_name: str) -> bool:
        formula = RPM_TO_BREW.get(package_name)
        return super().check_package(formula) if formula else False

    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        formulae, unmappable = translate_to_brew(package_names)

        if unmappable:
            msg = (
                f"No Homebrew formula for: {', '.join(unmappable)}.\n"
                f"Layer them onto the image instead:\n"
                f"  sudo rpm-ostree install {' '.join(unmappable)}\n"
                f"  systemctl reboot\n"
                f"Or build inside a container where dnf works:\n"
                f"  distrobox create --name dev --image fedora:latest && distrobox enter dev"
            )
            if not formulae:
                return False, msg
            logger.warning(msg)

        ok, output = super().install_packages(formulae, verbose=verbose)
        if unmappable:
            output = f"{output}\n{msg}"
            ok = False
        return ok, output


class RpmOstreeManager(PackageManager):
    """Fallback for Fedora Atomic with no Homebrew: explain, never run dnf."""

    def check_available(self) -> bool:
        return shutil.which("rpm-ostree") is not None

    def check_package(self, package_name: str) -> bool:
        try:
            result = subprocess.run(
                ["rpm", "-q", package_name], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def install_packages(self, package_names: List[str], verbose: bool = False) -> Tuple[bool, str]:
        return False, (
            "This is a Fedora Atomic system, where packages cannot be installed "
            "into the running root filesystem.\n"
            "Install Homebrew (no root, no reboot) -- recommended:\n"
            '  /bin/bash -c "$(curl -fsSL '
            'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n'
            "Or layer them, which requires a reboot:\n"
            f"  sudo rpm-ostree install {' '.join(package_names)}\n"
            "  systemctl reboot"
        )


def get_package_manager() -> PackageManager:
    """Detect and return appropriate package manager for current platform.

    Returns:
        PackageManager: The detected package manager instance

    Raises:
        RuntimeError: If no supported package manager is found
    """
    if platform.system() == "Darwin":
        return BrewManager()

    # Fedora Atomic: dnf install cannot work, so never select DnfManager here.
    if is_ostree_system():
        if get_homebrew_prefix():
            logger.debug("Detected package manager: OstreeBrewManager")
            return OstreeBrewManager()
        logger.debug("Detected package manager: RpmOstreeManager")
        return RpmOstreeManager()

    # Native package manager first. Homebrew is only a fallback: it is often
    # installed alongside dnf/apt, and dependencies.yaml gives distro package
    # names, so preferring brew would feed it names it cannot resolve.
    managers = [DnfManager(), AptManager(), BrewManager()]

    for manager in managers:
        if manager.check_available():
            logger.debug(f"Detected package manager: {manager.__class__.__name__}")
            return manager

    raise RuntimeError("No supported package manager found (tried dnf, apt-get, brew)")
