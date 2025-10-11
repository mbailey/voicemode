"""Core dependency checking and installation logic."""

import yaml
import platform
import os
import subprocess
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from .package_managers import get_package_manager
from .cache import get_cache

logger = logging.getLogger(__name__)


def load_dependencies() -> dict:
    """Load dependencies.yaml from package.

    Returns:
        dict: Parsed dependencies configuration

    Raises:
        FileNotFoundError: If dependencies.yaml cannot be found
        yaml.YAMLError: If the YAML is malformed
    """
    try:
        # Try importlib.resources first (Python 3.9+)
        from importlib.resources import files
        yaml_path = files("voice_mode") / "dependencies.yaml"
        with yaml_path.open() as f:
            return yaml.safe_load(f)
    except (ImportError, AttributeError):
        # Fallback to pkg_resources
        try:
            import pkg_resources
            yaml_text = pkg_resources.resource_string("voice_mode", "dependencies.yaml")
            return yaml.safe_load(yaml_text)
        except Exception:
            # Last resort: try reading from relative path (development mode)
            current_dir = Path(__file__).parent.parent.parent
            yaml_file = current_dir / "dependencies.yaml"
            if yaml_file.exists():
                with yaml_file.open() as f:
                    return yaml.safe_load(f)
            raise FileNotFoundError("Could not find dependencies.yaml")


def detect_platform() -> str:
    """Detect OS/distribution.

    Returns:
        str: Platform key - 'darwin', 'debian', 'fedora', 'wsl-debian', 'wsl-fedora', or 'unknown'
    """
    system = platform.system().lower()

    if system == "darwin":
        return "darwin"
    elif system == "linux":
        # Check for WSL
        try:
            with open("/proc/version", "r") as f:
                proc_version = f.read().lower()
                if "microsoft" in proc_version or "wsl" in proc_version:
                    # Detect distro within WSL
                    if os.path.exists("/etc/debian_version"):
                        return "wsl-debian"
                    elif os.path.exists("/etc/fedora-release"):
                        return "wsl-fedora"
                    # Default to wsl-debian if we can't determine
                    return "wsl-debian"
        except (IOError, OSError):
            pass

        # Check Linux distro
        if os.path.exists("/etc/debian_version"):
            return "debian"
        elif os.path.exists("/etc/fedora-release"):
            return "fedora"

    logger.warning(f"Unknown platform: {system}")
    return "unknown"


def check_dependency(package: dict, platform_key: str) -> bool:
    """Check if a single dependency is installed.

    Args:
        package: Package info dict from dependencies.yaml
        platform_key: Platform key ('darwin', 'debian', 'fedora', etc.)

    Returns:
        bool: True if installed, False otherwise
    """
    cache = get_cache()
    package_name = package["name"]

    # Check cache first
    cached = cache.get(package_name)
    if cached is not None:
        logger.debug(f"Cache hit for {package_name}: installed")
        return cached

    # Use check_command if provided
    if "check_command" in package:
        try:
            cmd = package["check_command"].split()
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                text=True
            )
            installed = result.returncode == 0
            logger.debug(f"Check command for {package_name}: {installed}")
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Error running check command for {package_name}: {e}")
            installed = False
    else:
        # Use package manager
        try:
            pm = get_package_manager()
            installed = pm.check_package(package_name)
            logger.debug(f"Package manager check for {package_name}: {installed}")
        except RuntimeError as e:
            logger.warning(f"No package manager available: {e}")
            installed = False

    # Cache result
    cache.set(package_name, installed)
    return installed


def check_component_dependencies(
    component: str,
    dependencies_yaml: Optional[dict] = None
) -> Dict[str, bool]:
    """Check all dependencies for a component.

    Args:
        component: Component name ('core', 'whisper', 'kokoro', 'installation')
        dependencies_yaml: Loaded dependencies (if None, loads from file)

    Returns:
        Dict mapping package name to installed status
    """
    if dependencies_yaml is None:
        dependencies_yaml = load_dependencies()

    platform_key = detect_platform()

    # Strip 'wsl-' prefix for package lookup (wsl-debian -> debian)
    # but keep it for WSL-specific requirement checking
    is_wsl = platform_key.startswith("wsl-")
    package_platform_key = platform_key.replace("wsl-", "") if is_wsl else platform_key

    results = {}

    component_deps = dependencies_yaml["voicemode"].get(component, {})

    # Check common packages first (for installation component)
    common_deps = component_deps.get("common", {}).get("packages", [])
    for package in common_deps:
        required = package.get("required", False)
        if required:
            results[package["name"]] = check_dependency(package, "common")

    # Check platform-specific packages
    platform_deps = component_deps.get(package_platform_key, {}).get("packages", [])

    for package in platform_deps:
        # Check if required
        required = package.get("required", False)

        # Handle WSL-specific requirements
        if required == "wsl" and not is_wsl:
            continue  # Skip WSL-only deps on native systems

        # Skip non-required packages unless explicitly required
        if required:
            results[package["name"]] = check_dependency(package, package_platform_key)

    return results


def install_missing_dependencies(
    missing: List[str],
    interactive: bool = True
) -> Tuple[bool, str]:
    """Install missing dependencies.

    Args:
        missing: List of package names to install
        interactive: If True, prompt for confirmation

    Returns:
        Tuple[bool, str]: (success, message)
    """
    if not missing:
        return True, "No dependencies to install"

    if interactive:
        print(f"\nMissing dependencies: {', '.join(missing)}")
        response = input("Install missing dependencies? [Y/n] ")
        if response.lower() in ("n", "no"):
            return False, "Installation cancelled by user"

    try:
        pm = get_package_manager()
    except RuntimeError as e:
        return False, str(e)

    success, output = pm.install_packages(missing)

    if success:
        # Clear cache so they get rechecked
        cache = get_cache()
        cache.clear()
        logger.info(f"Successfully installed: {', '.join(missing)}")
    else:
        logger.error(f"Failed to install dependencies: {output}")

    return success, output
