"""Refuse to delete, reset or clean a directory that is not our own service checkout.

The whisper and kokoro installers ``rmtree`` their install directory on a forced
reinstall and run ``git reset --hard`` / ``git clean -fd`` in it otherwise. Git
walks up from its working directory, so run inside a subdirectory of some other
repository those commands discard that repository's uncommitted work. Before any
of them, the installer calls :func:`check_own_checkout`, which passes only when
the directory is the top level of a git checkout whose ``origin`` is the
expected upstream.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import urlsplit

# owner/repo on github.com. The first entry is the one the installer clones
# today; the others are earlier origins an existing install may still carry.
KOKORO_UPSTREAMS = (
    "ai-cora/Kokoro-FastAPI",
    # voicemode cloned upstream remsky/Kokoro-FastAPI before switching to the
    # ai-cora fork (04d2e997); those checkouts must stay upgradable.
    "remsky/Kokoro-FastAPI",
)
WHISPER_UPSTREAMS = (
    "ggerganov/whisper.cpp",
    # The same repository after its move to the ggml-org organisation.
    "ggml-org/whisper.cpp",
)

_GITHUB_HOST = "github.com"
_URL_SCHEMES = {"https", "http", "ssh", "git", "git+ssh", "ssh+git"}
_SCP_LIKE = re.compile(r"^(?:[^@/:]+@)?(?P<host>[^/:]+):(?P<path>[^/].*)$")
_CONTROL_CHARS = ("\x00", "\r", "\n")

# Variables that point git at a repository other than the one under cwd / -C.
_GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


def git_env() -> Dict[str, str]:
    """The current environment without variables that redirect git elsewhere."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}


def _github_repo(url: str) -> Optional[str]:
    """``owner/repo`` (lower case) for a github.com remote URL, else None."""
    url = url.strip()
    if "://" in url:
        parts = urlsplit(url)
        if parts.scheme.lower() not in _URL_SCHEMES:
            return None
        host, path = parts.hostname or "", parts.path
    else:
        match = _SCP_LIKE.match(url)
        if not match:
            return None
        host, path = match.group("host"), match.group("path")
    if host.lower() != _GITHUB_HOST:
        return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if path.count("/") != 1:
        return None
    return path.lower()


def origin_matches(url: str, upstreams: Iterable[str]) -> bool:
    """True if ``url`` is a github.com remote for one of ``upstreams``.

    Accepts https/http/ssh/git URLs and scp-like ``git@github.com:owner/repo``,
    with or without ``.git`` or a trailing slash; owner/repo compare without case.
    """
    repo = _github_repo(url)
    return repo is not None and repo in {u.lower() for u in upstreams}


def _git_output(path: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            env=git_env(),
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def check_own_checkout(install_dir, upstreams: Iterable[str]) -> Optional[str]:
    """Why ``install_dir`` must not be deleted, reset or cleaned; None if it may.

    It may only when it is the top level of a git checkout (not a directory
    inside one) and its ``remote.origin.url`` is one of ``upstreams``.
    """
    upstreams = tuple(upstreams)
    refusing = "refusing to delete, reset or clean it"
    raw = str(install_dir)
    if any(c in raw for c in _CONTROL_CHARS):
        return f"Install directory {raw!r} contains a control character; {refusing}."

    resolved = Path(raw).expanduser().resolve()
    if not resolved.is_dir():
        return f"{resolved} is not a directory; {refusing}."

    toplevel = _git_output(resolved, "rev-parse", "--show-toplevel")
    if not toplevel:
        return (
            f"{resolved} is not a git checkout; {refusing}. "
            f"If it is an old install you no longer need, remove it yourself."
        )
    if Path(toplevel).resolve() != resolved:
        return (
            f"{resolved} is not the top level of a git checkout "
            f"(it is inside {toplevel}); {refusing}."
        )

    origin = _git_output(resolved, "config", "--get", "remote.origin.url")
    if not origin:
        return f"{resolved} has no origin remote, so it is not a {upstreams[0]} checkout; {refusing}."
    if not origin_matches(origin, upstreams):
        return (
            f"{resolved} is a checkout of {origin}, not {upstreams[0]}; {refusing}."
        )
    return None
