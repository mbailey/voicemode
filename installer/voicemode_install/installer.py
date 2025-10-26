"""System package installation."""

import subprocess
from typing import List, Optional

from .checker import PackageInfo
from .system import PlatformInfo, get_package_manager


class PackageInstaller:
    """Install system packages using platform-specific package managers."""

    def __init__(self, platform_info: PlatformInfo, dry_run: bool = False, non_interactive: bool = False):
        self.platform = platform_info
        self.dry_run = dry_run
        self.non_interactive = non_interactive
        self.package_manager = get_package_manager(platform_info.distribution)

    def install_packages(self, packages: List[PackageInfo]) -> bool:
        """
        Install a list of packages.

        Returns True if all installations succeeded, False otherwise.
        """
        if not packages:
            return True

        package_names = [pkg.name for pkg in packages]

        if self.dry_run:
            print(f"[DRY RUN] Would install: {', '.join(package_names)}")
            return True

        try:
            if self.platform.distribution == 'darwin':
                return self._install_homebrew(package_names)
            elif self.platform.distribution == 'debian':
                return self._install_apt(package_names)
            elif self.platform.distribution == 'fedora':
                return self._install_dnf(package_names)
            else:
                print(f"Error: Unsupported distribution: {self.platform.distribution}")
                return False
        except Exception as e:
            print(f"Error installing packages: {e}")
            return False

    def _install_homebrew(self, packages: List[str]) -> bool:
        """Install packages using Homebrew.

        Note: Homebrew should already be installed by the time this is called.
        The CLI ensures Homebrew is present before dependency checking.
        """
        try:
            cmd = ['brew', 'install'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False  # Show output to user
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"Homebrew package installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: Homebrew not found. This should have been installed earlier.")
            print("Please report this as a bug.")
            return False

    def _install_apt(self, packages: List[str]) -> bool:
        """Install packages using apt."""
        try:
            # Update package lists first
            print("Updating package lists...")
            subprocess.run(
                ['sudo', 'apt', 'update'],
                check=True,
                capture_output=False
            )

            # Install packages
            cmd = ['sudo', 'apt', 'install', '-y'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"apt installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: apt not found")
            return False

    def _install_dnf(self, packages: List[str]) -> bool:
        """Install packages using dnf."""
        try:
            cmd = ['sudo', 'dnf', 'install', '-y'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"dnf installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: dnf not found")
            return False

    def install_voicemode(self, version: Optional[str] = None) -> bool:
        """
        Install or upgrade voice-mode using uv tool install --upgrade.

        Args:
            version: Optional version to install (e.g., "5.1.3")

        Returns:
            True if installation succeeded, False otherwise.
        """
        if self.dry_run:
            if version:
                print(f"[DRY RUN] Would install: uv tool install --upgrade voice-mode=={version}")
            else:
                print("[DRY RUN] Would install: uv tool install --upgrade voice-mode")
            return True

        try:
            # Always use --upgrade to ensure we get the latest/requested version
            # This also implies --refresh to check for new versions
            if version:
                cmd = ['uv', 'tool', 'install', '--upgrade', f'voice-mode=={version}']
            else:
                cmd = ['uv', 'tool', 'install', '--upgrade', 'voice-mode']

            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"VoiceMode installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: uv not found. Please install uv first:")
            print("  curl -LsSf https://astral.sh/uv/install.sh | sh")
            return False
