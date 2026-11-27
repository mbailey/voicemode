"""The whisper/kokoro installers only ever delete, reset or clean their own checkout.

- The MCP tools take no ``install_dir``; only the CLI (a human) can pass one.
- Before ``rmtree``, ``git reset --hard`` or ``git clean -fd`` the installer
  checks the directory is the top level of a git checkout whose origin is the
  expected upstream. Anything else is refused and left untouched.
- Bool-ish string args coerce: ``force_reinstall="false"`` is False.
- Whisper service files come from ``create_service_file`` (no stray ``{...}``).

No network: ``git clone``/``fetch`` and every non-git subprocess are blocked by
the ``no_network`` fixture; local git (init, commit, rev-parse, reset) runs for
real so the "enclosing repo survives" check is a real one.
"""

import asyncio
import os
import platform
import re
import subprocess
from pathlib import Path

import pytest

import voice_mode.tools.kokoro.install as kokoro_mod
import voice_mode.tools.whisper.install as whisper_mod
from voice_mode.server import mcp
from voice_mode.utils.coerce import coerce_bool
from voice_mode.utils.services.checkout_guard import (
    KOKORO_UPSTREAMS,
    WHISPER_UPSTREAMS,
    check_own_checkout,
    origin_matches,
)

KOKORO_URL = "https://github.com/ai-cora/Kokoro-FastAPI.git"
WHISPER_URL = "https://github.com/ggerganov/whisper.cpp.git"
TEST_VERSION = "v0.0.1-test"

_real_run = subprocess.run
_BLOCKED_GIT = {"clone", "fetch", "pull", "push", "ls-remote"}


def _git(cwd, *args):
    return _real_run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
    )


def _make_repo(path: Path, origin=None, tag=None, files=None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    for name, text in (files or {"a.txt": "v1\n"}).items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    if origin:
        _git(path, "remote", "add", "origin", origin)
    if tag:
        _git(path, "tag", tag)
    return path


@pytest.fixture
def no_network(monkeypatch, isolate_home_directory):
    """Block clone/fetch and every non-git subprocess (conftest fakes HOME)."""
    home = isolate_home_directory
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(home / ".voicemode"))
    blocked = []

    def fake_run(cmd, *args, **kwargs):
        argv = list(cmd) if not isinstance(cmd, str) else [cmd]
        sub = [a for a in argv[1:] if not a.startswith("-")]
        if argv and argv[0] == "git" and not (set(sub[:1]) & _BLOCKED_GIT):
            return _real_run(cmd, *args, **kwargs)
        if argv and argv[0] == "xcode-select":
            return subprocess.CompletedProcess(argv, 0, "", "")
        blocked.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(kokoro_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    return blocked


def _kokoro(**kw):
    kw.setdefault("skip_deps", True)
    kw.setdefault("version", TEST_VERSION)
    kw.setdefault("auto_enable", False)
    return asyncio.run(kokoro_mod.install_kokoro(**kw))


def _whisper(**kw):
    kw.setdefault("skip_deps", True)
    kw.setdefault("version", TEST_VERSION)
    kw.setdefault("auto_enable", False)
    kw.setdefault("use_gpu", False)
    kw.setdefault("no_model", True)
    return asyncio.run(whisper_mod.install_whisper(**kw))


INSTALLERS = [pytest.param(_kokoro, id="kokoro"), pytest.param(_whisper, id="whisper")]


def _ran(blocked, word):
    return [c for c in blocked if word in c]


# --- the MCP surface -------------------------------------------------------

@pytest.mark.parametrize("tool", ["kokoro_install", "whisper_install"])
def test_mcp_tool_schema_has_no_install_dir(tool):
    t = asyncio.run(mcp.get_tool(tool))
    assert "install_dir" not in t.parameters["properties"]


# --- force_reinstall outside our checkout ----------------------------------

@pytest.mark.parametrize("install", INSTALLERS)
def test_force_reinstall_refuses_dir_that_is_not_a_git_checkout(install, tmp_path, no_network):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "important.txt").write_text("keep me")

    result = install(install_dir=str(victim), force_reinstall=True)

    assert (victim / "important.txt").read_text() == "keep me"
    assert result["success"] is False
    assert "not a git checkout" in result["error"]
    assert not _ran(no_network, "clone")


@pytest.mark.parametrize("install", INSTALLERS)
def test_force_reinstall_refuses_foreign_repo(install, tmp_path, no_network):
    victim = _make_repo(tmp_path / "victim", origin="git@github.com:someone/else.git")

    result = install(install_dir=str(victim), force_reinstall=True)

    assert (victim / "a.txt").exists()
    assert result["success"] is False
    assert "someone/else" in result["error"]


# --- no force: git reset/clean must not walk up into an enclosing repo -----

@pytest.mark.parametrize("install", INSTALLERS)
def test_repo_subdir_reset_refused_enclosing_work_survives(install, tmp_path, no_network):
    repo = _make_repo(tmp_path / "repo", files={"a.txt": "v1\n", "sub/keep.txt": "x\n"})
    (repo / "a.txt").write_text("uncommitted work\n")
    (repo / "sub" / "untracked.txt").write_text("untracked\n")

    result = install(install_dir=str(repo / "sub"), force_reinstall=False)

    assert (repo / "a.txt").read_text() == "uncommitted work\n"
    assert (repo / "sub" / "untracked.txt").exists()
    assert result["success"] is False
    assert "not the top level" in result["error"]


# --- bool-ish strings -------------------------------------------------------

@pytest.mark.parametrize("install,url,marker", [
    pytest.param(_kokoro, KOKORO_URL, "main.py", id="kokoro"),
    pytest.param(_whisper, WHISPER_URL, "main", id="whisper"),
])
def test_force_reinstall_string_false_does_not_delete(install, url, marker, tmp_path,
                                                      no_network, monkeypatch):
    checkout = _make_repo(tmp_path / "svc", origin=url, tag=TEST_VERSION,
                          files={marker: "x\n"})
    (checkout / "local-data.txt").write_text("keep")

    async def no_service_files(**kwargs):
        return {"success": True, "updated": False}

    monkeypatch.setattr(kokoro_mod, "update_kokoro_service_files", no_service_files)
    monkeypatch.setattr(whisper_mod, "update_whisper_service_files", no_service_files)

    result = install(install_dir=str(checkout), force_reinstall="false")

    assert (checkout / "local-data.txt").read_text() == "keep"
    assert result["success"] is True, result
    assert result.get("already_installed") is True


@pytest.mark.parametrize("value,expected", [
    ("false", False), ("False", False), ("0", False), ("no", False), ("", False),
    (" off ", False), ("true", True), ("1", True), ("yes", True), (True, True),
    (False, False), (None, None), ("maybe", None),
])
def test_coerce_bool(value, expected):
    assert coerce_bool(value) is expected


def test_coerce_bool_default_for_unknown():
    assert coerce_bool("maybe", default=False) is False
    assert coerce_bool(None, default=False) is False


# --- the guard itself -------------------------------------------------------

def test_guard_allows_our_own_checkout_and_force_proceeds(tmp_path, no_network):
    checkout = _make_repo(tmp_path / "kokoro", origin=KOKORO_URL)

    result = _kokoro(install_dir=str(checkout), force_reinstall=True)

    # The guard let rmtree run; the re-clone was then blocked (no network).
    assert not checkout.exists()
    assert _ran(no_network, "clone")
    assert result["success"] is False


def test_guard_refuses_symlink_to_foreign_repo(tmp_path):
    foreign = _make_repo(tmp_path / "foreign", origin="https://github.com/x/y")
    link = tmp_path / "link"
    link.symlink_to(foreign)
    assert "x/y" in check_own_checkout(link, KOKORO_UPSTREAMS)


def test_guard_refuses_repo_with_no_origin(tmp_path):
    repo = _make_repo(tmp_path / "r")
    assert "no origin" in check_own_checkout(repo, WHISPER_UPSTREAMS)


def test_guard_refuses_control_characters(tmp_path):
    assert "control character" in check_own_checkout(tmp_path / "a\nb", WHISPER_UPSTREAMS)


def test_guard_passes_own_checkout(tmp_path):
    repo = _make_repo(tmp_path / "w", origin="git@github.com:ggerganov/whisper.cpp.git")
    assert check_own_checkout(repo, WHISPER_UPSTREAMS) is None


@pytest.mark.parametrize("url", [
    "https://github.com/ai-cora/Kokoro-FastAPI",
    "https://github.com/ai-cora/Kokoro-FastAPI.git",
    "https://github.com/ai-cora/Kokoro-FastAPI/",
    "https://github.com/AI-Cora/kokoro-fastapi.git",
    "http://github.com/ai-cora/Kokoro-FastAPI",
    "git@github.com:ai-cora/Kokoro-FastAPI.git",
    "ssh://git@github.com/ai-cora/Kokoro-FastAPI.git",
    "ssh://git@github.com:22/ai-cora/Kokoro-FastAPI",
    "git://github.com/ai-cora/Kokoro-FastAPI.git",
    "https://github.com/remsky/Kokoro-FastAPI.git",
])
def test_origin_matches_accepts_kokoro_variants(url):
    assert origin_matches(url, KOKORO_UPSTREAMS)


@pytest.mark.parametrize("url", [
    "",
    "https://github.com/evil/Kokoro-FastAPI.git",
    "https://github.com.evil.example/ai-cora/Kokoro-FastAPI.git",
    "https://evil.example/github.com/ai-cora/Kokoro-FastAPI.git",
    "https://github.com/ai-cora/Kokoro-FastAPI-x.git",
    "https://github.com/ai-cora/Kokoro-FastAPI/tree/x",
    "/local/path/Kokoro-FastAPI",
    "git@gitlab.com:ai-cora/Kokoro-FastAPI.git",
])
def test_origin_matches_rejects_others(url):
    assert not origin_matches(url, KOKORO_UPSTREAMS)


def test_origin_matches_whisper_variants():
    assert origin_matches("https://github.com/ggerganov/whisper.cpp", WHISPER_UPSTREAMS)
    assert origin_matches("git@github.com:ggml-org/whisper.cpp.git", WHISPER_UPSTREAMS)
    assert not origin_matches(KOKORO_URL, WHISPER_UPSTREAMS)


# --- whisper service files --------------------------------------------------

@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_whisper_service_file_has_no_unreplaced_placeholder(system, monkeypatch,
                                                            isolate_home_directory):
    home = isolate_home_directory
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(home / ".voicemode"))
    monkeypatch.setattr(platform, "system", lambda: system)
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, *a, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    install_dir = home / ".voicemode" / "services" / "whisper"

    result = asyncio.run(whisper_mod.update_whisper_service_files(
        install_dir=str(install_dir),
        voicemode_dir=str(home / ".voicemode"),
        auto_enable=False,
    ))

    assert result["success"] is True, result
    path = Path(result.get("plist_path") or result["service_path"])
    assert str(path).startswith(str(home))
    content = path.read_text()
    assert not re.search(r"\{[A-Z_]+\}", content), content
    assert str(install_dir / "bin" / "start-whisper-server.sh") in content
    assert (install_dir / "bin" / "start-whisper-server.sh").exists()
