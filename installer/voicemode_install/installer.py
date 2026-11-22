"""System package installation."""

import subprocess
from typing import List, Optional

from .checker import PackageInfo, RPM_TO_BREW
from .system import PlatformInfo, get_package_manager, get_homebrew_prefix

# Packages that need no action on Fedora Atomic, with the reason shown to the
# user. python3-devel only ever supplies build headers, and voice-mode is
# installed with `uv tool install`, which builds against uv's own managed
# CPython -- that ships its headers with it.
OSTREE_SATISFIED = {
    'python3-devel': 'uv-managed CPython provides the Python headers',
}


class PackageInstaller:
    """Install system packages using platform-specific package managers."""

    def __init__(self, platform_info: PlatformInfo, dry_run: bool = False, non_interactive: bool = False):
        self.platform = platform_info
        self.dry_run = dry_run
        self.non_interactive = non_interactive
        self.package_manager = get_package_manager(
            platform_info.distribution, platform_info.is_ostree
        )

    def install_packages(self, packages: List[PackageInfo]) -> bool:
        """
        Install a list of packages.

        Returns True if all installations succeeded, False otherwise.
        """
        if not packages:
            return True

        package_names = [pkg.name for pkg in packages]

        # On Atomic the interesting part of a dry run is *how* each package
        # would be obtained -- brew, rpm-ostree, or skipped entirely -- so let
        # _install_ostree report that itself rather than printing a flat list
        # that hides the routing.
        if self.dry_run and not self.platform.is_ostree:
            print(f"[DRY RUN] Would install: {', '.join(package_names)}")
            return True

        try:
            if self.platform.distribution == 'darwin':
                return self._install_homebrew(package_names)
            elif self.platform.distribution == 'debian':
                return self._install_apt(package_names)
            elif self.platform.is_ostree:
                # Must precede the plain 'fedora' branch: Atomic variants report
                # ID=fedora but dnf install cannot work there.
                return self._install_ostree(package_names)
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

    def _install_ostree(self, packages: List[str]) -> bool:
        """Install packages on Fedora Atomic (Silverblue, Kinoite, Bazzite, Bluefin).

        ``dnf install`` does not work on these images -- the root filesystem is
        read-only, and Bazzite ships a dnf shim that refuses install outright.
        The two real options are Homebrew (no root, no reboot) and
        ``rpm-ostree install`` (layers the package, requires a reboot).

        Homebrew is strongly preferred: every dependency here is a build-time
        header or a CLI tool, so nothing needs to come from the base image, and
        layering would cost the user a reboot for no benefit.
        """
        remaining = []
        for pkg in packages:
            reason = OSTREE_SATISFIED.get(pkg)
            if reason:
                print(f"  Skipping {pkg}: {reason}")
            else:
                remaining.append(pkg)

        if not remaining:
            return True

        brew_pkgs, unmapped = [], []
        for pkg in remaining:
            formula = RPM_TO_BREW.get(pkg)
            if formula:
                if formula not in brew_pkgs:
                    brew_pkgs.append(formula)
            else:
                unmapped.append(pkg)

        ok = True
        if brew_pkgs:
            if get_homebrew_prefix():
                if self.dry_run:
                    print(f"[DRY RUN] Would run: brew install {' '.join(brew_pkgs)}")
                else:
                    print(f"Detected Fedora Atomic -- installing via Homebrew: {', '.join(brew_pkgs)}")
                    ok = self._install_homebrew(brew_pkgs)
            else:
                unmapped.extend(remaining)
                print(
                    "Homebrew is not installed. It is the recommended way to add "
                    "development headers on an immutable OS:\n"
                    '  /bin/bash -c "$(curl -fsSL '
                    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                )
                ok = False

        if unmapped:
            print(
                "\nThese packages have no Homebrew equivalent and must be layered "
                "onto the image:\n"
                f"  sudo rpm-ostree install {' '.join(sorted(set(unmapped)))}\n"
                "  systemctl reboot\n"
                "Layering takes effect only after a reboot. Alternatively, do the "
                "build inside a distrobox container, where dnf works normally:\n"
                "  distrobox create --name dev --image fedora:latest\n"
                "  distrobox enter dev"
            )
            ok = False

        return ok

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
