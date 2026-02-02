#!/usr/bin/env python3
"""Version management script for voice-mode packages."""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_current_version():
    """Get the current version from voice_mode/__version__.py."""
    version_file = Path("voice_mode/__version__.py")
    content = version_file.read_text()
    match = re.search(r'^__version__ = ["\']([^"\']+)["\']', content, re.MULTILINE)
    if match:
        return match.group(1)
    raise ValueError("Could not find version in voice_mode/__version__.py")


def update_version_in_file(filepath, pattern, replacement):
    """Update version using regex pattern in specified file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Warning: {filepath} not found, skipping")
        return False

    content = path.read_text()
    updated = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content == updated:
        print(f"Warning: No changes made to {filepath}")
        return False

    path.write_text(updated)
    print(f"✅ Updated {filepath}")
    return True


def update_changelog(version):
    """Add new version entry to CHANGELOG.md."""
    changelog = Path("CHANGELOG.md")
    if not changelog.exists():
        print("Warning: CHANGELOG.md not found, skipping")
        return False

    content = changelog.read_text()
    date = datetime.now().strftime("%Y-%m-%d")

    # Add new version section after [Unreleased]
    new_section = f"## [Unreleased]\n\n## [{version}] - {date}"
    updated = content.replace("## [Unreleased]", new_section, 1)

    if content == updated:
        print("Warning: Could not update CHANGELOG.md")
        return False

    changelog.write_text(updated)
    print(f"✅ Updated CHANGELOG.md")
    return True


def update_version(new_version, packages=None):
    """Update version in all required files.

    Args:
        new_version: The new version string (e.g., "5.1.5")
        packages: List of packages to update ('package', 'installer', or both)
    """
    if packages is None:
        packages = ["package", "installer"]

    print(f"Updating version to {new_version}...")
    print()

    files_updated = []

    # Always update main package files
    if "package" in packages:
        if update_version_in_file(
            "voice_mode/__version__.py",
            r'^__version__ = ["\'][^"\']+["\']',
            f'__version__ = "{new_version}"'
        ):
            files_updated.append("voice_mode/__version__.py")

        if update_version_in_file(
            "server.json",
            r'"version": "[^"]*"',
            f'"version": "{new_version}"'
        ):
            files_updated.append("server.json")

    # Update installer package if requested
    if "installer" in packages:
        if update_version_in_file(
            "installer/pyproject.toml",
            r'^version = "[^"]*"',
            f'version = "{new_version}"'
        ):
            files_updated.append("installer/pyproject.toml")

    # Update plugin.json with version + p0 suffix
    plugin_version = f"{new_version}p0"
    if update_version_in_file(
        ".claude-plugin/plugin.json",
        r'"version": "[^"]*"',
        f'"version": "{plugin_version}"'
    ):
        files_updated.append(".claude-plugin/plugin.json")

    # Update CHANGELOG for all package updates
    if update_changelog(new_version):
        files_updated.append("CHANGELOG.md")

    if not files_updated:
        print("\n❌ No files were updated!")
        return False

    print()
    print(f"✅ Updated {len(files_updated)} file(s)")
    return True


def commit_and_tag(version, packages=None):
    """Commit version changes and create git tag.

    Args:
        version: The version string
        packages: List of packages being released
    """
    if packages is None or len(packages) == 2:
        package_desc = "all packages"
    elif "installer" in packages:
        package_desc = "voice-mode-install"
    else:
        package_desc = "voice-mode"

    # Stage all changed files
    files_to_add = ["CHANGELOG.md", ".claude-plugin/plugin.json"]
    if packages is None or "package" in packages:
        files_to_add.extend(["voice_mode/__version__.py", "server.json"])
    if packages is None or "installer" in packages:
        files_to_add.append("installer/pyproject.toml")

    try:
        # Git add
        subprocess.run(["git", "add"] + files_to_add, check=True)

        # Git commit
        commit_msg = f"chore: bump version to {version} for {package_desc}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        print(f"✅ Committed changes")

        # Git tag
        tag_name = f"v{version}"
        tag_msg = f"Release v{version}"
        subprocess.run(["git", "tag", "-a", tag_name, "-m", tag_msg], check=True)
        print(f"✅ Created tag {tag_name}")

        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Git operation failed: {e}")
        return False


def push_to_remote(version):
    """Push commits and tags to remote repository."""
    try:
        # Push commits
        subprocess.run(["git", "push", "origin"], check=True)
        print("✅ Pushed commits to origin")

        # Push tag
        tag_name = f"v{version}"
        subprocess.run(["git", "push", "origin", tag_name], check=True)
        print(f"✅ Pushed tag {tag_name} to origin")

        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Git push failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Manage versions for voice-mode packages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update both packages
  %(prog)s 5.1.5

  # Update only voice-mode package
  %(prog)s 5.1.5 --package package

  # Update only voice-mode-install
  %(prog)s 5.1.5 --package installer

  # Update version but don't commit/tag/push
  %(prog)s 5.1.5 --no-commit

  # Just show current version
  %(prog)s --current
"""
    )

    parser.add_argument(
        "version",
        nargs="?",
        help="New version number (e.g., 5.1.5)"
    )

    parser.add_argument(
        "--package",
        action="append",
        choices=["package", "installer"],
        help="Which package(s) to update (can specify multiple times)"
    )

    parser.add_argument(
        "--current",
        action="store_true",
        help="Show current version and exit"
    )

    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Update files but don't commit, tag, or push"
    )

    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Commit and tag but don't push to remote"
    )

    args = parser.parse_args()

    # Show current version
    if args.current:
        try:
            current = get_current_version()
            print(f"Current version: {current}")
            return 0
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    # Version argument is required unless --current
    if not args.version:
        parser.print_help()
        return 1

    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"Error: Invalid version format '{args.version}'")
        print("Expected format: X.Y.Z (e.g., 5.1.5)")
        return 1

    # Default to both packages if not specified
    packages = args.package if args.package else ["package", "installer"]

    # Update version files
    if not update_version(args.version, packages):
        return 1

    # Stop here if --no-commit
    if args.no_commit:
        print()
        print("Version files updated. Commit manually when ready.")
        return 0

    # Commit and tag
    print()
    if not commit_and_tag(args.version, packages):
        return 1

    # Stop here if --no-push
    if args.no_push:
        print()
        print("Changes committed and tagged. Push manually when ready:")
        print(f"  git push origin")
        print(f"  git push origin v{args.version}")
        return 0

    # Push to remote
    print()
    if not push_to_remote(args.version):
        return 1

    print()
    print("🚀 Release pipeline triggered!")
    print()
    print("GitHub Actions will now:")
    print("1. Create a GitHub release with changelog")
    print("2. Publish packages to PyPI")
    print()
    print("Monitor progress at: https://github.com/mbailey/voicemode/actions")

    return 0


if __name__ == "__main__":
    sys.exit(main())
