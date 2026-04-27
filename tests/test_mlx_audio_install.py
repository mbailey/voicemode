"""Tests for the mlx-audio service install pipeline.

Covers:
- Apple-Silicon hardware gate (short-circuits before any subprocess).
- The ``MLX_AUDIO_EXTRAS`` list shape and the install-command generator.
- Patch idempotency via the ``_inference_lock = asyncio.Lock()`` sentinel.
- Backup creation and preservation across re-applies.
- Patch failure surfaces an actionable error.
- Service config + template wiring (plist/systemd) for ``mlx_audio``.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.tools.mlx_audio.install import (
    MLX_AUDIO_DEFAULT_PORT,
    MLX_AUDIO_EXTRAS,
    MLX_AUDIO_PIP_PACKAGE,
    PATCH_SENTINEL,
    _apply_server_patch,
    _build_install_cmd,
    _is_apple_silicon,
    mlx_audio_install,
)
from voice_mode.tools.service import (
    _SERVICE_FILE_NAMES,
    _service_file_name,
    get_service_config_vars,
)


# ============================================================================
# Apple-Silicon gate
# ============================================================================


class TestAppleSiliconCheck:
    """The arm64-Darwin detector must say no on Intel/Linux."""

    def test_apple_silicon_on_arm64_mac(self):
        with patch("voice_mode.tools.mlx_audio.install.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.machine.return_value = "arm64"
            assert _is_apple_silicon() is True

    def test_not_apple_silicon_on_intel_mac(self):
        with patch("voice_mode.tools.mlx_audio.install.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.machine.return_value = "x86_64"
            assert _is_apple_silicon() is False

    def test_not_apple_silicon_on_linux_arm(self):
        with patch("voice_mode.tools.mlx_audio.install.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            mock_platform.machine.return_value = "arm64"
            assert _is_apple_silicon() is False


class TestInstallShortCircuitsOnNonAppleSilicon:
    """install must refuse Intel/Linux *before* any subprocess.run."""

    @pytest.mark.asyncio
    async def test_rejects_intel_mac_without_subprocess(self):
        with patch(
            "voice_mode.tools.mlx_audio.install._is_apple_silicon",
            return_value=False,
        ), patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run"
        ) as mock_run, patch(
            "voice_mode.tools.mlx_audio.install.platform"
        ) as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.machine.return_value = "x86_64"
            result = await mlx_audio_install()
        assert result["success"] is False
        assert "Apple Silicon" in result["error"]
        # Crucial: no `uv tool install` should have been attempted.
        assert mock_run.call_count == 0

    @pytest.mark.asyncio
    async def test_rejects_linux_without_subprocess(self):
        with patch(
            "voice_mode.tools.mlx_audio.install._is_apple_silicon",
            return_value=False,
        ), patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run"
        ) as mock_run, patch(
            "voice_mode.tools.mlx_audio.install.platform"
        ) as mock_platform:
            mock_platform.system.return_value = "Linux"
            mock_platform.machine.return_value = "x86_64"
            result = await mlx_audio_install()
        assert result["success"] is False
        assert "Apple Silicon" in result["error"]
        assert mock_run.call_count == 0


# ============================================================================
# Extras list + install-command shape
# ============================================================================


class TestExtrasList:
    """Pin the runtime extras list -- this is the entire point of the task."""

    EXPECTED_EXTRAS = [
        "misaki[en]",
        "en-core-web-sm",
        "uvicorn",
        "fastapi",
        "webrtcvad",
        "python-multipart",
        "setuptools<81",
        "sounddevice",
        "soundfile",
        "librosa",
        "mlx",
        "mlx-lm",
    ]

    def test_extras_list_has_exactly_twelve_entries(self):
        assert len(MLX_AUDIO_EXTRAS) == 12

    def test_extras_list_matches_canonical(self):
        # Order isn't semantically meaningful but matching it keeps diffs
        # readable; if upstream pins move, update both lists in lockstep.
        assert MLX_AUDIO_EXTRAS == self.EXPECTED_EXTRAS

    def test_setuptools_is_pinned_below_81(self):
        # Bare ``setuptools`` would let pkg_resources removal break us;
        # ``setuptools<81`` is the workaround, do not let it regress.
        assert "setuptools<81" in MLX_AUDIO_EXTRAS
        assert "setuptools" not in MLX_AUDIO_EXTRAS

    def test_misaki_carries_en_extra(self):
        # misaki without [en] doesn't pull spaCy English -- the bundled
        # patch + Kokoro path needs it.
        assert "misaki[en]" in MLX_AUDIO_EXTRAS
        assert "misaki" not in MLX_AUDIO_EXTRAS


class TestInstallCommandShape:
    """``uv tool install mlx-audio`` followed by --with pairs, optional --reinstall."""

    def test_command_starts_with_uv_tool_install_mlx_audio(self):
        cmd = _build_install_cmd(force_reinstall=False)
        assert cmd[:4] == ["uv", "tool", "install", MLX_AUDIO_PIP_PACKAGE]

    def test_each_extra_has_a_with_flag(self):
        cmd = _build_install_cmd(force_reinstall=False)
        # After the head ["uv", "tool", "install", "mlx-audio"], the rest
        # should be a flat sequence of --with <extra> pairs.
        tail = cmd[4:]
        assert len(tail) == 2 * len(MLX_AUDIO_EXTRAS)
        for i in range(0, len(tail), 2):
            assert tail[i] == "--with"
            assert tail[i + 1] in MLX_AUDIO_EXTRAS

    def test_force_reinstall_appends_reinstall_flag(self):
        cmd = _build_install_cmd(force_reinstall=True)
        assert cmd[-1] == "--reinstall"

    def test_no_force_means_no_reinstall_flag(self):
        cmd = _build_install_cmd(force_reinstall=False)
        assert "--reinstall" not in cmd


# ============================================================================
# Patch application: idempotency + backup + failure
# ============================================================================


@pytest.fixture
def fake_server_py(tmp_path: Path) -> Path:
    """A throwaway ``server.py`` that looks pre-patch."""
    server = tmp_path / "server.py"
    server.write_text(
        "# fake mlx_audio server.py\n"
        "import asyncio\n"
        "# (no _inference_lock yet)\n"
    )
    return server


class TestPatchAlreadyApplied:
    """If the sentinel is present, skip patching and report success."""

    def test_skip_patch_when_sentinel_present(self, tmp_path: Path):
        server = tmp_path / "server.py"
        server.write_text(
            f"import asyncio\n# voicemode-patched\n{PATCH_SENTINEL}\n"
        )
        with patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run"
        ) as mock_run:
            result = _apply_server_patch(server)
        assert result["success"] is True
        assert result.get("already_patched") is True
        # Critical: no `patch` invocation -- already patched.
        assert mock_run.call_count == 0
        # Backup must NOT be created when nothing was patched.
        assert not (server.parent / "server.py.pre-voicemode.bak").exists()


class TestPatchBackupCreation:
    """First-time apply writes a one-shot backup; subsequent applies don't overwrite it."""

    def test_backup_created_on_first_apply(self, fake_server_py: Path):
        from voice_mode.tools.mlx_audio import install as install_mod

        # Stub `patch -p1` to "succeed" and inject the sentinel into server.py
        # so the post-patch sanity check passes.
        def fake_patch_run(cmd, **kwargs):
            fake_server_py.write_text(
                fake_server_py.read_text()
                + f"\n{install_mod.PATCH_SENTINEL}\n"
            )
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run",
            side_effect=fake_patch_run,
        ):
            result = install_mod._apply_server_patch(fake_server_py)

        assert result["success"] is True
        assert result["already_patched"] is False
        backup = fake_server_py.parent / "server.py.pre-voicemode.bak"
        assert backup.exists()
        # Backup snapshots the *pre-patch* content (no sentinel).
        assert install_mod.PATCH_SENTINEL not in backup.read_text()

    def test_existing_backup_preserved(self, fake_server_py: Path):
        from voice_mode.tools.mlx_audio import install as install_mod

        # Pre-seed an "older" backup.
        backup = fake_server_py.parent / "server.py.pre-voicemode.bak"
        backup.write_text("ORIGINAL UNTOUCHABLE PRE-PATCH SNAPSHOT")
        original_backup_bytes = backup.read_bytes()

        def fake_patch_run(cmd, **kwargs):
            fake_server_py.write_text(
                fake_server_py.read_text()
                + f"\n{install_mod.PATCH_SENTINEL}\n"
            )
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run",
            side_effect=fake_patch_run,
        ):
            result = install_mod._apply_server_patch(fake_server_py)

        assert result["success"] is True
        # The pre-existing backup must NOT be clobbered.
        assert backup.read_bytes() == original_backup_bytes


class TestPatchFailureError:
    """Sentinel absent + ``patch`` returns nonzero -> fail with actionable error."""

    def test_patch_failure_surfaces_paths_and_version(self, fake_server_py: Path):
        from voice_mode.tools.mlx_audio import install as install_mod

        def fake_run(cmd, **kwargs):
            # First subprocess.run call is `patch -p1 ...` and fails.
            # Second is `uv tool list` for the version lookup.
            if cmd and cmd[0] == "patch":
                return type("R", (), {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Hunk #1 FAILED at 35.",
                })()
            if cmd[:3] == ["uv", "tool", "list"]:
                return type("R", (), {
                    "returncode": 0,
                    "stdout": "mlx-audio v0.4.2\n",
                    "stderr": "",
                })()
            raise AssertionError(f"unexpected subprocess.run call: {cmd}")

        with patch(
            "voice_mode.tools.mlx_audio.install.subprocess.run",
            side_effect=fake_run,
        ):
            result = install_mod._apply_server_patch(fake_server_py)

        assert result["success"] is False
        assert "Failed to apply" in result["error"]
        # The error must point at the patch file + the installed version
        # so the operator can investigate without source-diving.
        assert "mlx_audio_server.patch" in result["error"]
        assert "v0.4.2" in result["error"] or "unknown" in result["error"]


# ============================================================================
# Service wiring (config vars, templates)
# ============================================================================


class TestServiceFileNameMapping:
    """``mlx_audio`` (snake) -> ``mlx-audio`` (kebab) for plist/systemd files."""

    def test_mlx_audio_maps_to_kebab(self):
        assert _service_file_name("mlx_audio") == "mlx-audio"

    def test_voicemode_maps_to_serve(self):
        # Existing convention preserved by the same helper.
        assert _service_file_name("voicemode") == "serve"

    def test_passthrough_for_other_services(self):
        assert _service_file_name("whisper") == "whisper"
        assert _service_file_name("kokoro") == "kokoro"

    def test_mapping_table_includes_mlx_audio(self):
        assert "mlx_audio" in _SERVICE_FILE_NAMES
        assert _SERVICE_FILE_NAMES["mlx_audio"] == "mlx-audio"


class TestMlxAudioConfigVars:
    """``mlx_audio`` config vars provide HOME for plist substitution."""

    def test_config_vars_provide_home(self):
        config_vars = get_service_config_vars("mlx_audio")
        assert "HOME" in config_vars
        # Sanity-check it's an absolute path.
        assert config_vars["HOME"].startswith("/")

    def test_no_start_script_for_mlx_audio(self):
        # mlx-audio runs the uv-tool entry point directly; there is no
        # start-mlx-audio.sh to render.
        config_vars = get_service_config_vars("mlx_audio")
        assert "START_SCRIPT" not in config_vars


class TestMlxAudioTemplates:
    """Bundled launchd plist must exist; no systemd unit ships (Apple-only)."""

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).parent.parent / "voice_mode" / "templates"

    def test_launchd_plist_exists(self):
        template = self.templates_dir / "launchd" / "com.voicemode.mlx-audio.plist"
        assert template.exists(), f"Launchd template missing: {template}"

    def test_no_systemd_unit_ships(self):
        # mlx-audio is Apple-Silicon-only; the install gate rejects Linux
        # before any service-rendering code runs, so no systemd unit ships.
        template = self.templates_dir / "systemd" / "voicemode-mlx-audio.service"
        assert not template.exists(), (
            f"Linux systemd unit must not ship for mlx-audio: {template}"
        )

    def test_load_template_refuses_mlx_audio_on_linux(self):
        # The template loader must refuse mlx_audio on non-Darwin so we
        # fail loud rather than silently looking up a nonexistent file.
        from voice_mode.tools.service import load_service_template

        with patch("voice_mode.tools.service.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            with pytest.raises(FileNotFoundError, match="macOS-only"):
                load_service_template("mlx_audio")

    def test_launchd_plist_calls_local_bin_entry_point(self):
        template = self.templates_dir / "launchd" / "com.voicemode.mlx-audio.plist"
        content = template.read_text()
        assert "com.voicemode.mlx-audio" in content
        # Direct entry-point exec, no service-local start script.
        assert "$HOME/.local/bin/mlx_audio.server" in content
        assert "VOICEMODE_MLX_AUDIO_HOST" in content
        assert "VOICEMODE_MLX_AUDIO_PORT" in content

    def test_launchd_plist_logs_to_voicemode_logs_dir(self):
        template = self.templates_dir / "launchd" / "com.voicemode.mlx-audio.plist"
        content = template.read_text()
        assert "/.voicemode/logs/mlx-audio" in content

    def test_old_clone_templates_are_gone(self):
        # Belt-and-braces: PR #346 shipped a com.voicemode.clone.plist.
        # After VM-1108 it must not exist alongside the new one.
        assert not (self.templates_dir / "launchd" / "com.voicemode.clone.plist").exists()
        assert not (self.templates_dir / "systemd" / "voicemode-clone.service").exists()
        assert not (self.templates_dir / "scripts" / "start-clone-server.sh").exists()


class TestMlxAudioConfigEnvVars:
    """Config module exports MLX_AUDIO_PORT/HOST with the right defaults."""

    def test_mlx_audio_port_default(self):
        from voice_mode.config import MLX_AUDIO_PORT
        assert MLX_AUDIO_PORT == MLX_AUDIO_DEFAULT_PORT == 8890

    def test_mlx_audio_host_default(self):
        from voice_mode.config import MLX_AUDIO_HOST
        assert MLX_AUDIO_HOST == "127.0.0.1"


# ============================================================================
# Bundled patch resource
# ============================================================================


class TestBundledPatchResource:
    """The patch file ships under voice_mode/data/patches/."""

    def test_patch_file_exists_in_package(self):
        patch_path = (
            Path(__file__).parent.parent
            / "voice_mode"
            / "data"
            / "patches"
            / "mlx_audio_server.patch"
        )
        assert patch_path.exists(), (
            f"Bundled patch missing at {patch_path} -- this is a packaging bug"
        )

    def test_patch_file_contains_sentinel_introduction(self):
        # The whole point of bundling: the patch introduces our sentinel.
        patch_path = (
            Path(__file__).parent.parent
            / "voice_mode"
            / "data"
            / "patches"
            / "mlx_audio_server.patch"
        )
        content = patch_path.read_text()
        # The patch should add (not remove) the sentinel line.
        assert f"+_inference_lock = asyncio.Lock()" in content
