"""In-memory caching for dependency check results."""

from typing import Optional, Dict


class DependencyCache:
    """In-memory cache for dependency status.

    Caches present dependencies (don't recheck).
    Always rechecks missing dependencies (they might get installed).
    """

    def __init__(self):
        self._cache: Dict[str, bool] = {}

    def get(self, package: str) -> Optional[bool]:
        """Get cached status for a package.

        Returns:
            True if installed (cached)
            None if missing (never cached) or not yet checked
        """
        status = self._cache.get(package)
        # Only return cached result if package was found installed
        return status if status else None

    def set(self, package: str, installed: bool):
        """Cache dependency status.

        Only caches positive results (installed=True).
        Missing packages are not cached so they get rechecked.
        """
        if installed:
            self._cache[package] = True

    def clear(self):
        """Clear all cached results."""
        self._cache.clear()


# Global cache instance (created on module import)
_dependency_cache = DependencyCache()


def get_cache() -> DependencyCache:
    """Get the global dependency cache instance."""
    return _dependency_cache
