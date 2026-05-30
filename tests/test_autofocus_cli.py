"""Tests for the `voicemode autofocus` CLI toggle (VM-1024).

Mirrors the soundfonts toggle pattern (see voice_mode/cli_commands/soundfonts.py
and the same-shaped tests there if/when they're added). Targets:

- Sentinel file create / remove via `autofocus off` / `autofocus on`
- `--config` flag persists VOICEMODE_AUTO_FOCUS_PANE in voicemode.env
- `autofocus status` reports correctly across the four states
  (no sentinel + env unset / env true / env false; sentinel present)
"""

from pathlib import Path
from unittest.mock import patch

import click.testing
import pytest

# Import autofocus at test-module load time, BEFORE any pytest fixture has
# patched Path.home(). This ensures SENTINEL_FILE / VOICEMODE_ENV_FILE bind
# to the real user home (where the sentinel typically does NOT exist) — and
# our tests then explicitly monkeypatch those attrs to point under fake_home.
# Without this, autofocus would be imported lazily under a fixture-patched
# Path.home, leaving a stale tmp_path baked into the module forever (and
# leaking sentinel files into later tests in the same session).
from voice_mode.cli_commands import autofocus as _autofocus_eager_import  # noqa: F401


@pytest.fixture
def tmp_voicemode_dir(isolate_home_directory, monkeypatch):
    """Provide handles to the autofocus module's sentinel/env paths.

    Relies on the project-wide autouse `isolate_home_directory` fixture
    (tests/conftest.py:99) which patches `Path.home()` to a tmp dir.

    We pin the autofocus module's module-level `SENTINEL_FILE` and
    `VOICEMODE_ENV_FILE` to paths under this test's fake home via
    `monkeypatch.setattr`. `monkeypatch` undoes the patch at teardown, so
    no module reload is needed — other tests see the originals. This
    avoids the stale-Path bug where a previous test's tmp_path leaks
    into a later test's SENTINEL_FILE via module-level binding.
    """
    from voice_mode.cli_commands import autofocus
    fake_home = isolate_home_directory
    sentinel_path = fake_home / ".voicemode" / "autofocus-disabled"
    env_path = fake_home / ".voicemode" / "voicemode.env"
    monkeypatch.setattr(autofocus, "SENTINEL_FILE", sentinel_path)
    monkeypatch.setattr(autofocus, "VOICEMODE_ENV_FILE", env_path)
    monkeypatch.delenv("VOICEMODE_AUTO_FOCUS_PANE", raising=False)
    yield {
        "home": fake_home,
        "voicemode_dir": fake_home / ".voicemode",
        "sentinel": sentinel_path,
        "env_file": env_path,
        "autofocus": autofocus,
    }


def _run(cmd, args):
    return click.testing.CliRunner().invoke(cmd, args)


class TestAutofocusOff:
    """`voicemode autofocus off` creates the sentinel; --config persists env var."""

    def test_creates_sentinel_when_absent(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        assert not tmp_voicemode_dir["sentinel"].exists()

        result = _run(af.autofocus, ["off"])
        assert result.exit_code == 0
        assert tmp_voicemode_dir["sentinel"].exists()
        assert "disabled" in result.output.lower()

    def test_idempotent_when_sentinel_present(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        tmp_voicemode_dir["sentinel"].parent.mkdir(parents=True, exist_ok=True)
        tmp_voicemode_dir["sentinel"].touch()

        result = _run(af.autofocus, ["off"])
        assert result.exit_code == 0
        assert tmp_voicemode_dir["sentinel"].exists()
        assert "already disabled" in result.output.lower()

    def test_config_flag_writes_env_file(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        result = _run(af.autofocus, ["off", "--config"])
        assert result.exit_code == 0
        contents = tmp_voicemode_dir["env_file"].read_text()
        assert "VOICEMODE_AUTO_FOCUS_PANE=false" in contents


class TestAutofocusOn:
    """`voicemode autofocus on` removes the sentinel; --config flips env var to true."""

    def test_removes_sentinel_when_present(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        tmp_voicemode_dir["sentinel"].parent.mkdir(parents=True, exist_ok=True)
        tmp_voicemode_dir["sentinel"].touch()

        result = _run(af.autofocus, ["on"])
        assert result.exit_code == 0
        assert not tmp_voicemode_dir["sentinel"].exists()
        assert "enabled" in result.output.lower()

    def test_idempotent_when_sentinel_absent_and_env_false(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        result = _run(af.autofocus, ["on"])
        assert result.exit_code == 0
        # No sentinel removed, no change made. The "default is false" hint should
        # fire (env var is unset, so autofocus won't actually run without --config).
        assert "auto-focus" in result.output.lower()
        assert "voicemode_auto_focus_pane" in result.output.lower()

    def test_config_flag_writes_env_file_true(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        result = _run(af.autofocus, ["on", "--config"])
        assert result.exit_code == 0
        contents = tmp_voicemode_dir["env_file"].read_text()
        assert "VOICEMODE_AUTO_FOCUS_PANE=true" in contents


class TestAutofocusStatus:
    """`voicemode autofocus status` reports the four canonical states."""

    def test_disabled_default_when_nothing_set(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        result = _run(af.autofocus, ["status"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        assert "default" in result.output.lower()

    def test_enabled_when_env_true_in_file(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        env = tmp_voicemode_dir["env_file"]
        env.parent.mkdir(parents=True, exist_ok=True)
        env.write_text("VOICEMODE_AUTO_FOCUS_PANE=true\n")

        result = _run(af.autofocus, ["status"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()
        assert "voicemode_auto_focus_pane=true" in result.output.lower()

    def test_disabled_quick_toggle_when_sentinel_present(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        tmp_voicemode_dir["sentinel"].parent.mkdir(parents=True, exist_ok=True)
        tmp_voicemode_dir["sentinel"].touch()

        result = _run(af.autofocus, ["status"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        assert "quick toggle" in result.output.lower()

    def test_sentinel_overrides_env_true(self, tmp_voicemode_dir):
        """Sentinel forces off even when env var would have enabled it."""
        af = tmp_voicemode_dir["autofocus"]
        env = tmp_voicemode_dir["env_file"]
        env.parent.mkdir(parents=True, exist_ok=True)
        env.write_text("VOICEMODE_AUTO_FOCUS_PANE=true\n")
        tmp_voicemode_dir["sentinel"].parent.mkdir(parents=True, exist_ok=True)
        tmp_voicemode_dir["sentinel"].touch()

        result = _run(af.autofocus, ["status"])
        assert result.exit_code == 0
        out = result.output.lower()
        assert "disabled (quick toggle)" in out
        assert "overridden" in out


class TestIsAutofocusDisabledBySentinel:
    """The helper consumed by focus_tmux_pane() in converse.py."""

    def test_false_when_sentinel_absent(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        assert af.is_autofocus_disabled_by_sentinel() is False

    def test_true_when_sentinel_present(self, tmp_voicemode_dir):
        af = tmp_voicemode_dir["autofocus"]
        tmp_voicemode_dir["sentinel"].parent.mkdir(parents=True, exist_ok=True)
        tmp_voicemode_dir["sentinel"].touch()
        assert af.is_autofocus_disabled_by_sentinel() is True
