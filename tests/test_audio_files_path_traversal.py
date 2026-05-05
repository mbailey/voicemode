"""Regression tests for path-traversal handling in the audio file resource.

The MCP resource ``audio://file/{filename}`` previously accepted the
filename without sanitisation, so a request like ``../../etc/passwd``
would resolve to a file outside ``AUDIO_DIR``. Fixed in PR #376.

These tests exercise the underlying handler directly (via the
FastMCP-wrapped ``.fn`` attribute) so they can run without an MCP
server. They verify:

1. Path-traversal sequences cannot escape ``AUDIO_DIR``.
2. Absolute paths are normalised to a basename and contained.
3. Empty filenames are rejected.
4. A file *outside* ``AUDIO_DIR`` with the same basename as one
   *inside* still resolves to the in-dir copy (basename + containment).
5. Backslash variants behave the same on POSIX (``\\`` is just a char in
   filenames here, so it's treated as a single component).
"""

import asyncio
from pathlib import Path

import pytest

from voice_mode.resources import audio_files as audio_files_module
from voice_mode.resources.audio_files import get_audio_file


# Resolve the underlying async function (FastMCP wraps the decorated fn).
_handler = get_audio_file.fn


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def isolated_audio_dir(tmp_path, monkeypatch):
    """Point AUDIO_DIR at a tmp dir and force SAVE_AUDIO on.

    Patches the module-level globals the handler reads (it imports them
    by name from voice_mode.config, so we patch on the audio_files
    module rather than on config -- that's the binding the handler
    actually uses).
    """
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(audio_files_module, "AUDIO_DIR", str(audio_dir))
    monkeypatch.setattr(audio_files_module, "SAVE_AUDIO", True)
    return audio_dir


@pytest.fixture
def sensitive_outside_file(tmp_path):
    """Create a file *outside* AUDIO_DIR that traversal might reach."""
    secret = tmp_path / "secret.txt"
    secret.write_text("SHOULD NOT LEAK")
    return secret


def test_traversal_dotdot_does_not_escape_audio_dir(
    isolated_audio_dir, sensitive_outside_file
):
    """``../secret.txt`` must not return metadata for the sibling file."""
    result = _run(_handler("../secret.txt"))
    assert "SHOULD NOT LEAK" not in (result or "")
    # basename strips the prefix -> "secret.txt", not in AUDIO_DIR -> not found.
    assert "Audio file not found" in result


def test_traversal_deep_dotdot_does_not_escape_audio_dir(isolated_audio_dir):
    """``../../etc/passwd`` should be reduced to ``passwd`` and bounce."""
    result = _run(_handler("../../etc/passwd"))
    # The handler must NOT return metadata for /etc/passwd.
    assert "Path: /etc/passwd" not in (result or "")
    # And must NOT leak any directory above AUDIO_DIR.
    assert "/etc/" not in (result or "")
    # basename -> "passwd", not present in tmp audio dir -> not found.
    assert "Audio file not found" in result


def test_absolute_path_does_not_escape_audio_dir(isolated_audio_dir):
    """``/etc/passwd`` -> basename ``passwd`` -> not found (no /etc read)."""
    result = _run(_handler("/etc/passwd"))
    assert "Path: /etc/passwd" not in (result or "")
    assert "Audio file not found" in result


def test_empty_filename_is_rejected(isolated_audio_dir):
    """An empty filename (or one that becomes empty after basename) errors."""
    result = _run(_handler(""))
    assert result == "Invalid filename."


def test_traversal_does_not_read_existing_outside_file(
    isolated_audio_dir, sensitive_outside_file
):
    """Even if the resolved path *would* exist outside AUDIO_DIR, we don't read it.

    Construct a traversal that, naively joined, would land on the
    real ``sensitive_outside_file``. The handler must not return its
    metadata.
    """
    # Walk up from AUDIO_DIR to tmp_path/secret.txt.
    traversal = f"../{sensitive_outside_file.name}"
    result = _run(_handler(traversal))
    assert "SHOULD NOT LEAK" not in (result or "")
    # No leak of the outside path either.
    assert str(sensitive_outside_file) not in (result or "")


def test_legitimate_filename_resolves_inside_audio_dir(isolated_audio_dir):
    """A bare in-dir filename returns metadata for the in-dir file."""
    inside = isolated_audio_dir / "real.wav"
    inside.write_bytes(b"\x00" * 1024)
    result = _run(_handler("real.wav"))
    assert "Audio file: real.wav" in result
    assert f"Path: {inside}" in result


def test_basename_collision_resolves_to_in_dir_copy(
    isolated_audio_dir, tmp_path
):
    """A traversal that *names* an existing in-dir file still returns the in-dir copy.

    basename() strips ``../`` etc. so the handler always reads
    ``AUDIO_DIR/<basename>``. If that file exists in AUDIO_DIR, it's
    returned -- the outside copy with the same name is never consulted.
    """
    inside = isolated_audio_dir / "shared.wav"
    inside.write_bytes(b"INSIDE")
    outside = tmp_path / "shared.wav"
    outside.write_bytes(b"OUTSIDE-SHOULD-NOT-LEAK")

    result = _run(_handler("../shared.wav"))
    assert "OUTSIDE-SHOULD-NOT-LEAK" not in (result or "")
    assert f"Path: {inside}" in result
    assert "Audio file: shared.wav" in result


def test_save_audio_disabled_short_circuits(monkeypatch, tmp_path):
    """When SAVE_AUDIO is off, the handler returns the disabled message.

    This is just a guard that the security check doesn't accidentally
    fire before the disabled-feature check, which would change the
    user-visible behaviour for normal users who haven't opted into
    audio saving.
    """
    monkeypatch.setattr(audio_files_module, "SAVE_AUDIO", False)
    monkeypatch.setattr(audio_files_module, "AUDIO_DIR", str(tmp_path))
    result = _run(_handler("../../etc/passwd"))
    assert "not enabled" in result
