"""Dependency management for VoiceMode.

This module provides utilities for checking and installing system dependencies
required by VoiceMode and its service components (Whisper, Kokoro, etc.).
"""

from .checker import (
    check_component_dependencies,
    check_dependency,
    install_missing_dependencies,
    load_dependencies,
    detect_platform,
)
from .cache import get_cache, DependencyCache
from .package_managers import get_package_manager, PackageManager

__all__ = [
    "check_component_dependencies",
    "check_dependency",
    "install_missing_dependencies",
    "load_dependencies",
    "detect_platform",
    "get_cache",
    "DependencyCache",
    "get_package_manager",
    "PackageManager",
]
