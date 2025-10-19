"""Dependency checking logic."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from .system import PlatformInfo, check_command_exists


@dataclass
class PackageInfo:
    """Information about a system package."""

    name: str
    description: str
    required: bool
    installed: bool
    check_command: Optional[str] = None
    min_version: Optional[str] = None
    note: Optional[str] = None


class DependencyChecker:
    """Check system dependencies against dependencies.yaml."""

    def __init__(self, platform_info: PlatformInfo):
        self.platform = platform_info
        self.dependencies = self._load_dependencies()

    def _load_dependencies(self) -> dict:
        """Load dependencies from bundled YAML file."""
        deps_file = Path(__file__).parent / 'dependencies.yaml'
        with open(deps_file) as f:
            return yaml.safe_load(f)

    def check_core_dependencies(self) -> List[PackageInfo]:
        """Check core VoiceMode dependencies."""
        return self._check_component_dependencies('core')

    def check_whisper_dependencies(self) -> List[PackageInfo]:
        """Check Whisper STT dependencies."""
        return self._check_component_dependencies('whisper')

    def check_kokoro_dependencies(self) -> List[PackageInfo]:
        """Check Kokoro TTS dependencies."""
        return self._check_component_dependencies('kokoro')

    def _check_component_dependencies(self, component: str) -> List[PackageInfo]:
        """Check dependencies for a specific component."""
        packages = []

        # Get the component section
        voicemode_deps = self.dependencies.get('voicemode', {})
        component_deps = voicemode_deps.get(component, {})

        if not component_deps:
            return packages

        # Check common packages first (all platforms)
        if 'common' in component_deps:
            packages.extend(self._check_packages(component_deps['common'].get('packages', [])))

        # Check platform-specific packages
        if self.platform.distribution in component_deps:
            platform_packages = component_deps[self.platform.distribution].get('packages', [])
            packages.extend(self._check_packages(platform_packages))

        return packages

    def _check_packages(self, package_list: List[dict]) -> List[PackageInfo]:
        """Check a list of packages and return their status."""
        results = []

        for pkg_dict in package_list:
            name = pkg_dict.get('name')
            if not name:
                continue

            description = pkg_dict.get('description', '')
            required = pkg_dict.get('required', True)
            check_command = pkg_dict.get('check_command')
            min_version = pkg_dict.get('min_version')
            note = pkg_dict.get('note')

            # Handle WSL-specific requirements
            if required == 'wsl':
                required = self.platform.is_wsl

            # Check if package is installed
            installed = self._is_package_installed(name, check_command)

            results.append(PackageInfo(
                name=name,
                description=description,
                required=bool(required),
                installed=installed,
                check_command=check_command,
                min_version=min_version,
                note=note
            ))

        return results

    def _is_package_installed(self, package_name: str, check_command: Optional[str] = None) -> bool:
        """Check if a package is installed."""
        # If a check command is provided, use it
        if check_command:
            return self._run_check_command(check_command)

        # Otherwise, use package manager-specific checks
        if self.platform.distribution == 'darwin':
            return self._check_homebrew_package(package_name)
        elif self.platform.distribution == 'debian':
            return self._check_apt_package(package_name)
        elif self.platform.distribution == 'fedora':
            return self._check_dnf_package(package_name)
        else:
            # Fallback: check if command exists
            return check_command_exists(package_name)

    def _run_check_command(self, command: str) -> bool:
        """Run a check command and return whether it succeeded."""
        try:
            subprocess.run(
                command,
                shell=True,
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _check_homebrew_package(self, package_name: str) -> bool:
        """Check if a Homebrew package is installed."""
        try:
            subprocess.run(
                ['brew', 'list', package_name],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _check_apt_package(self, package_name: str) -> bool:
        """Check if an apt package is installed."""
        try:
            result = subprocess.run(
                ['dpkg', '-l', package_name],
                capture_output=True,
                text=True
            )
            # dpkg -l returns 0 even if package not found, check output
            # Look for lines starting with "ii" (installed) followed by the exact package name
            # Note: On ARM64 and other architectures, dpkg may include :arch suffix (e.g., python3-dev:arm64)
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'ii':
                    # Strip architecture suffix (e.g., :arm64) if present for comparison
                    pkg_name_in_output = parts[1].split(':')[0]
                    if pkg_name_in_output == package_name:
                        return True
            return False
        except FileNotFoundError:
            return False

    def _check_dnf_package(self, package_name: str) -> bool:
        """Check if a dnf/yum package is installed."""
        try:
            subprocess.run(
                ['rpm', '-q', package_name],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_missing_packages(self, packages: List[PackageInfo]) -> List[PackageInfo]:
        """Filter to only required packages that are not installed."""
        return [pkg for pkg in packages if pkg.required and not pkg.installed]

    def get_summary(self, packages: List[PackageInfo]) -> dict:
        """Get a summary of package status."""
        total = len(packages)
        required = sum(1 for pkg in packages if pkg.required)
        installed = sum(1 for pkg in packages if pkg.installed)
        missing_required = sum(1 for pkg in packages if pkg.required and not pkg.installed)

        return {
            'total': total,
            'required': required,
            'installed': installed,
            'missing_required': missing_required
        }
