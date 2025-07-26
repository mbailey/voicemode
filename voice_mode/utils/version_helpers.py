"""Version management helpers for service installations."""

import subprocess
import logging
from typing import List, Optional, Tuple
from pathlib import Path
import re

logger = logging.getLogger("voice-mode")


def get_git_tags(repo_url: str) -> List[str]:
    """Fetch git tags from a repository URL."""
    try:
        # Use git ls-remote to get tags without cloning
        result = subprocess.run(
            ["git", "ls-remote", "--tags", repo_url],
            capture_output=True,
            text=True,
            check=True
        )
        
        tags = []
        for line in result.stdout.strip().split('\n'):
            if line:
                # Extract tag name from refs/tags/tagname
                parts = line.split('\t')
                if len(parts) == 2 and 'refs/tags/' in parts[1]:
                    tag = parts[1].replace('refs/tags/', '')
                    # Skip annotated tag references (ending with ^{})
                    if not tag.endswith('^{}'):
                        tags.append(tag)
        
        return sorted(tags, key=parse_version, reverse=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch tags from {repo_url}: {e}")
        return []


def parse_version(version: str) -> Tuple:
    """Parse version string for sorting.
    
    Handles versions like v1.2.3, v1.2.3-pre, v1.2.3-rc1, etc.
    Returns tuple for proper sorting.
    """
    # Remove 'v' prefix if present
    if version.startswith('v'):
        version = version[1:]
    
    # Split on dash for pre-release info
    parts = version.split('-', 1)
    main_version = parts[0]
    pre_release = parts[1] if len(parts) > 1 else None
    
    # Parse main version
    try:
        version_parts = [int(x) for x in main_version.split('.')]
    except ValueError:
        # Handle versions with non-numeric parts
        version_parts = []
        for part in main_version.split('.'):
            try:
                version_parts.append(int(part))
            except ValueError:
                # Convert non-numeric parts to 0 for consistent comparison
                version_parts.append(0)
    
    # Pad version parts to ensure consistent comparison
    while len(version_parts) < 3:
        version_parts.append(0)
    
    # Handle pre-release sorting
    # Stable releases come after pre-releases
    if pre_release is None:
        pre_release_order = (1, '')  # Stable
    else:
        # Extract pre-release type and number
        match = re.match(r'(alpha|beta|rc|pre)(\d*)', pre_release)
        if match:
            pre_type, pre_num = match.groups()
            pre_num = int(pre_num) if pre_num else 0
            # Order: alpha < beta < rc/pre < stable
            type_order = {'alpha': 0, 'beta': 1, 'rc': 2, 'pre': 2}
            pre_release_order = (0, type_order.get(pre_type, 3), pre_num)
        else:
            pre_release_order = (0, 4, pre_release)
    
    return tuple(version_parts + [pre_release_order])


def get_latest_stable_tag(tags: List[str]) -> Optional[str]:
    """Get the latest stable release tag (no pre-release suffixes)."""
    for tag in tags:
        # Skip pre-release versions
        if not any(suffix in tag for suffix in ['-pre', '-rc', '-alpha', '-beta', 'post']):
            return tag
    return tags[0] if tags else None


def get_current_version(install_dir: Path) -> Optional[str]:
    """Get the currently installed version from a git repository."""
    if not install_dir.exists() or not (install_dir / '.git').exists():
        return None
    
    try:
        # Try git describe first (shows tag + commits since tag)
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=install_dir,
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        
        # If we got a commit hash only, try to get the exact tag
        if re.match(r'^[0-9a-f]+$', version):
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match"],
                cwd=install_dir,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                version = result.stdout.strip()
        
        return version
    except subprocess.CalledProcessError:
        # Fallback to commit hash
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None


def checkout_version(install_dir: Path, version: str) -> bool:
    """Checkout a specific version in a git repository."""
    try:
        # Fetch latest tags
        subprocess.run(
            ["git", "fetch", "--tags"],
            cwd=install_dir,
            check=True,
            capture_output=True
        )
        
        # Checkout the version
        subprocess.run(
            ["git", "checkout", version],
            cwd=install_dir,
            check=True,
            capture_output=True
        )
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to checkout version {version}: {e}")
        return False


def is_version_installed(install_dir: Path, version: str) -> bool:
    """Check if a specific version is currently installed."""
    current = get_current_version(install_dir)
    if not current:
        return False
    
    # Handle exact matches
    if current == version:
        return True
    
    # Handle cases where current is "v1.2.3-4-gabcdef" and version is "v1.2.3"
    if '-' in current:
        base_version = current.split('-')[0]
        if base_version == version:
            return True
    
    return False