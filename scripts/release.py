#!/usr/bin/env python3
"""Version management script for voice-mode packages."""

import argparse
import os
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


# The canonical GitHub repo that carries the release pipeline (Actions fire on
# a `v*` tag push there). Resolve the remote dynamically by URL — never assume
# the remote is named "origin": post-2026-06-10 migration, origin -> ms2 (a bare
# git host with no Actions), so a tag push to origin ships nothing.
CANONICAL_GITHUB = ("mbailey", "voicemode")


def _parse_remote_url(url):
    """Parse a git remote URL into (host, owner, repo), or None if unparseable.

    Handles HTTPS (https://github.com/owner/repo[.git]), ssh:// URLs
    (ssh://git@github.com/owner/repo), and scp-like SSH
    (git@github.com:owner/repo, including ssh-config host aliases such as
    git@github.com_work:owner/repo).
    """
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    m = re.match(r"^(?:https?|ssh)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url)
    if m:
        host, path = m.group(1), m.group(2)
    else:
        m = re.match(r"^(?:[^@]+@)?([^:/]+):(.+)$", url)  # scp-like
        if not m:
            return None
        host, path = m.group(1), m.group(2)
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    return host, parts[-2], parts[-1]


def _is_canonical_github(url):
    parsed = _parse_remote_url(url)
    if not parsed:
        return False
    host, owner, repo = parsed
    is_github = host == "github.com" or host.startswith("github.com_")
    return is_github and (owner, repo) == CANONICAL_GITHUB


def get_remotes():
    """Return {remote_name: url} for the current repo."""
    names = subprocess.run(
        ["git", "remote"], capture_output=True, text=True, check=True
    ).stdout.split()
    remotes = {}
    for name in names:
        remotes[name] = subprocess.run(
            ["git", "remote", "get-url", name], capture_output=True, text=True, check=True
        ).stdout.strip()
    return remotes


def resolve_github_remote(remotes=None):
    """Return the name of the remote pointing at github.com/mbailey/voicemode.

    Matches by parsed host + owner/repo so a fork remote (e.g.
    Sallvainian/voicemode) is never selected. Honours a
    VOICEMODE_GITHUB_REMOTE override for non-canonical clones. Returns None if
    no canonical GitHub remote is configured.
    """
    if remotes is None:
        remotes = get_remotes()
    override = os.environ.get("VOICEMODE_GITHUB_REMOTE")
    if override and override in remotes:
        return override
    for name, url in remotes.items():
        if _is_canonical_github(url):
            return name
    return None


def push_to_remote(version):
    """Push the release commit + v-tag to the GitHub remote (Actions pipeline).

    The GitHub push is loud and blocking — if no canonical GitHub remote exists
    or the push fails, the release stops with a non-zero result rather than
    silently shipping nothing. The ms2 `origin` mirror is kept in sync on a
    best-effort basis (a mirror failure does not fail the release).
    """
    tag_name = f"v{version}"
    remotes = get_remotes()
    github_remote = resolve_github_remote(remotes)

    if github_remote is None:
        print(
            "\n❌ No GitHub remote for github.com/mbailey/voicemode is configured."
        )
        print(f"   Remotes found: {', '.join(remotes) or '(none)'}")
        print(
            "   The release pipeline (PyPI publish + GitHub Release) only fires on a"
            " tag push to GitHub, so this release would ship nothing."
        )
        print("   Add it, then re-run:")
        print("     git remote add github https://github.com/mbailey/voicemode.git")
        print("   (or set VOICEMODE_GITHUB_REMOTE=<remote-name> for a non-canonical clone)")
        return False

    try:
        # Push commits + tag to GitHub — this fires the release workflows.
        subprocess.run(["git", "push", github_remote], check=True)
        print(f"✅ Pushed commits to {github_remote} (GitHub)")
        subprocess.run(["git", "push", github_remote, tag_name], check=True)
        print(f"✅ Pushed tag {tag_name} to {github_remote} (GitHub) — Actions will fire")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Push to GitHub remote '{github_remote}' failed: {e}")
        return False

    # Keep the origin (ms2) mirror in sync — best effort; do not fail the release.
    if "origin" in remotes and "origin" != github_remote:
        try:
            subprocess.run(["git", "push", "origin"], check=True)
            subprocess.run(["git", "push", "origin", tag_name], check=True)
            print("✅ Mirrored commits + tag to origin")
        except subprocess.CalledProcessError as e:
            print(
                f"⚠️  Warning: could not mirror to origin (release already on GitHub): {e}"
            )

    return True


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
        github_remote = resolve_github_remote() or "github"
        print()
        print("Changes committed and tagged. Push manually when ready:")
        print(f"  # Push to GitHub to fire the release pipeline (Actions):")
        print(f"  git push {github_remote}")
        print(f"  git push {github_remote} v{args.version}")
        print(f"  # (optional) mirror to the origin (ms2) remote:")
        print(f"  git push origin && git push origin v{args.version}")
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
