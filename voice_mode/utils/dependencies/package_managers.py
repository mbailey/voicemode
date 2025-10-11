"""Package manager abstraction for cross-platform dependency installation."""

from abc import ABC, abstractmethod
from typing import List, Tuple
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)


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
    def install_packages(self, package_names: List[str]) -> Tuple[bool, str]:
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

    def install_packages(self, package_names: List[str]) -> Tuple[bool, str]:
        cmd = ["brew", "install"] + package_names
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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

    def install_packages(self, package_names: List[str]) -> Tuple[bool, str]:
        # Need sudo for apt
        cmd = ["sudo", "apt-get", "install", "-y"] + package_names
        try:
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

    def install_packages(self, package_names: List[str]) -> Tuple[bool, str]:
        # Need sudo for dnf
        cmd = ["sudo", "dnf", "install", "-y"] + package_names
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return result.returncode == 0, result.stderr or result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)


def get_package_manager() -> PackageManager:
    """Detect and return appropriate package manager for current platform.

    Returns:
        PackageManager: The detected package manager instance

    Raises:
        RuntimeError: If no supported package manager is found
    """
    managers = [BrewManager(), DnfManager(), AptManager()]

    for manager in managers:
        if manager.check_available():
            logger.debug(f"Detected package manager: {manager.__class__.__name__}")
            return manager

    raise RuntimeError("No supported package manager found (tried brew, dnf, apt-get)")
