"""Tests for the mlx-audio service install pipeline.

Covers:
- Apple-Silicon hardware gate (short-circuits before any subprocess).
- The ``MLX_AUDIO_EXTRAS`` list shape and the install-command generator.
- Service config + template wiring (plist/systemd) for ``mlx_audio``.
- The install flow uses upstream server.py unpatched (VM-2338).
- The espeak-ng data-path length warning (VM-2338).
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.tools.mlx_audio import install as install_mod
from voice_mode.tools.mlx_audio.install import (
    ESPEAK_DATA_PATH_MAX,
    MLX_AUDIO_DEFAULT_PORT,
    MLX_AUDIO_EXTRAS,
    MLX_AUDIO_PIP_PACKAGE,
    _build_install_cmd,
    _find_espeak_data_dir,
    _is_apple_silicon,
    _post_install_warnings,
    espeak_data_path_warning,
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

    EXPECTED_EXTRA_NAMES = [
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

    @staticmethod
    def _extra_name(spec: str) -> str:
        """Return the bare package name from a uv ``--with`` spec.

        ``uv`` accepts PEP 508 specifiers (e.g. ``en-core-web-sm @ https://...``);
        we want to compare on package identity, not pinned URLs.
        """
        return spec.split(" @ ", 1)[0].strip()

    def test_extras_list_has_exactly_twelve_entries(self):
        assert len(MLX_AUDIO_EXTRAS) == 12

    def test_extras_list_matches_canonical(self):
        # Order isn't semantically meaningful but matching it keeps diffs
        # readable; if upstream pins move, update both lists in lockstep.
        actual_names = [self._extra_name(s) for s in MLX_AUDIO_EXTRAS]
        assert actual_names == self.EXPECTED_EXTRA_NAMES

    def test_setuptools_is_pinned_below_81(self):
        # Bare ``setuptools`` would let pkg_resources removal break us;
        # ``setuptools<81`` is the workaround, do not let it regress.
        assert "setuptools<81" in MLX_AUDIO_EXTRAS
        assert "setuptools" not in MLX_AUDIO_EXTRAS

    def test_misaki_carries_en_extra(self):
        # misaki without [en] doesn't pull spaCy English -- the Kokoro G2P
        # path needs it; without it, /v1/audio/speech crashes with
        # ``ModuleNotFoundError: No module named 'misaki'`` on the first
        # synth request.
        assert "misaki[en]" in MLX_AUDIO_EXTRAS
        assert "misaki" not in MLX_AUDIO_EXTRAS


class TestPipPackagePin:
    """The pip-package spec is ``>=0.5.7,<0.6`` (VM-2338)."""

    def test_pip_package_specifier_is_exact(self):
        assert MLX_AUDIO_PIP_PACKAGE == "mlx-audio>=0.5.7,<0.6"

    def test_floor_is_the_measured_release(self):
        # 0.5.7 is the release VM-2330 measured: the VM-1547 Kokoro SineGen
        # crash (introduced in 0.4.4, fixed upstream in 0.4.5) is gone and
        # response_format is native (since 0.4.4), so no patch is needed.
        assert ">=0.5.7" in MLX_AUDIO_PIP_PACKAGE

    def test_caps_below_next_minor(self):
        # The 0.4.4 lesson: never let an untested minor release reach users.
        assert "<0.6" in MLX_AUDIO_PIP_PACKAGE

    def test_old_0_4_4_cap_is_gone(self):
        # The <0.4.4 cap (VM-1550) blocked every release with the fixes.
        assert "0.4.4" not in MLX_AUDIO_PIP_PACKAGE
        assert "0.4.3" not in MLX_AUDIO_PIP_PACKAGE


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
# No server.py patch (VM-2338)
# ============================================================================
# voicemode used to patch the installed server.py to add OpenAI-style STT
# response_format (VM-1128). Upstream has shipped it natively since 0.4.4
# (PR #704) and the patch's hunks all fail on >=0.4.4, so it was dropped.

REPO_ROOT = Path(__file__).parent.parent


class TestPatchIsGone:
    """The patch file, its constants and its packaging glob are all removed."""

    def test_patch_file_removed(self):
        assert not (
            REPO_ROOT / "voice_mode" / "data" / "patches" / "mlx_audio_server.patch"
        ).exists()

    def test_patch_machinery_removed_from_module(self):
        for name in (
            "PATCH_SENTINEL",
            "_PATCH_RESOURCE",
            "_BACKUP_NAME",
            "_apply_server_patch",
            "_query_installed_version",
        ):
            assert not hasattr(install_mod, name), f"{name} should be gone"

    def test_pyproject_drops_patch_glob(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "voice_mode/data/**/*.patch" not in pyproject

    def test_cli_no_longer_reports_patch_state(self):
        cli = (REPO_ROOT / "voice_mode" / "cli.py").read_text(encoding="utf-8")
        assert "already patched" not in cli


@pytest.fixture
def install_env(tmp_path, monkeypatch):
    """Run mlx_audio_install with every side effect mocked out.

    Nothing touches uv, launchctl, ~/.local or the real ~/.voicemode. The
    caller sets ``server_py`` (or None) before awaiting ``run()``.
    """
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / "vm"))
    # mlx_audio_install writes these; monkeypatch restores them afterwards.
    monkeypatch.setenv("VOICEMODE_MLX_AUDIO_PORT", "8890")
    monkeypatch.setenv("VOICEMODE_MLX_AUDIO_HOST", "127.0.0.1")

    entry_point = tmp_path / "bin" / "mlx_audio.server"
    entry_point.parent.mkdir()
    entry_point.touch()

    class Env:
        server_py = None
        run_mock = MagicMock()

        async def run(self):
            with patch.object(install_mod, "_is_apple_silicon", return_value=True), \
                 patch.object(install_mod, "_ensure_uv_available", return_value=None), \
                 patch.object(install_mod.subprocess, "run", self.run_mock), \
                 patch.object(install_mod, "_entry_point_path", return_value=entry_point), \
                 patch.object(install_mod, "_find_installed_server_py",
                              return_value=self.server_py), \
                 patch.object(install_mod, "_update_mlx_audio_service_files",
                              AsyncMock(return_value={"success": True,
                                                      "service_path": "/x.plist"})):
                return await mlx_audio_install()

    return Env()


def _make_site_packages(root: Path, espeak: bool = True) -> Path:
    """Build a fake tool-env site-packages; return its mlx_audio/server.py."""
    site = root / "site-packages"
    (site / "mlx_audio").mkdir(parents=True)
    server_py = site / "mlx_audio" / "server.py"
    server_py.write_text("# upstream server.py\n")
    if espeak:
        (site / "espeakng_loader" / "espeak-ng-data").mkdir(parents=True)
    return server_py


class TestInstallFlowDoesNotPatch:
    """A successful install runs ``uv tool install`` and never ``patch``."""

    @pytest.mark.asyncio
    async def test_install_never_invokes_patch(self, install_env, tmp_path):
        server_py = _make_site_packages(tmp_path)
        original = server_py.read_text()
        install_env.server_py = server_py
        result = await install_env.run()

        assert result["success"] is True
        argvs = [c.args[0] for c in install_env.run_mock.call_args_list]
        assert argvs == [_build_install_cmd(force_reinstall=False)]
        assert not any(argv and argv[0] == "patch" for argv in argvs)
        # server.py is left exactly as upstream shipped it, with no backup.
        assert server_py.read_text() == original
        assert list(server_py.parent.iterdir()) == [server_py]

    @pytest.mark.asyncio
    async def test_result_has_warnings_not_patch(self, install_env, tmp_path):
        # No espeak dir: macOS tmp_path alone can push the fake espeak path
        # past 160 chars, which would (correctly) warn.
        install_env.server_py = _make_site_packages(tmp_path, espeak=False)
        result = await install_env.run()
        assert "patch" not in result
        assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_missing_server_py_warns_but_succeeds(self, install_env):
        # Nothing needs server.py any more, so failing to find it is not
        # a reason to fail the install; it only skips the espeak check.
        install_env.server_py = None
        result = await install_env.run()
        assert result["success"] is True
        assert len(result["warnings"]) == 1
        assert "espeak-ng data path" in result["warnings"][0]


# ============================================================================
# espeak-ng data-path length guard (VM-2338, from VM-2330 investigate-002 §0)
# ============================================================================


class TestEspeakDataPathWarning:
    """Pure length check: 159 chars passes, 160+ warns."""

    def test_limit_is_160(self):
        assert ESPEAK_DATA_PATH_MAX == 160

    def test_159_chars_no_warning(self):
        path = "/" + "a" * 158
        assert len(path) == 159
        assert espeak_data_path_warning(path) is None

    def test_160_chars_warns(self):
        path = "/" + "a" * 159
        assert len(path) == 160
        warning = espeak_data_path_warning(path)
        assert warning is not None
        assert path in warning
        assert "160 characters" in warning

    def test_long_path_warning_names_the_fix(self):
        warning = espeak_data_path_warning(Path("/" + "b" * 300))
        assert "301 characters" in warning
        for knob in ("HOME", "UV_TOOL_DIR", "XDG_DATA_HOME"):
            assert knob in warning

    def test_default_uv_tool_path_is_fine(self):
        # The live m5 path VM-2330 measured: 104 chars.
        path = (
            "/Users/admin/.local/share/uv/tools/mlx-audio/lib/python3.11/"
            "site-packages/espeakng_loader/espeak-ng-data"
        )
        assert espeak_data_path_warning(path) is None

    def test_pure_does_not_need_path_to_exist(self):
        assert espeak_data_path_warning("/nonexistent/" + "x" * 200) is not None


class TestEspeakDataDirLocator:
    def test_missing_dir_returns_none(self, tmp_path):
        assert _find_espeak_data_dir(tmp_path) is None

    def test_present_dir_is_found(self, tmp_path):
        server_py = _make_site_packages(tmp_path)
        found = _find_espeak_data_dir(server_py.parent.parent)
        assert found == tmp_path / "site-packages" / "espeakng_loader" / "espeak-ng-data"


class TestPostInstallWarnings:
    def test_missing_espeak_dir_does_not_crash(self, tmp_path):
        server_py = _make_site_packages(tmp_path, espeak=False)
        assert _post_install_warnings(server_py) == []

    def test_long_espeak_path_warns(self, tmp_path):
        deep = tmp_path / ("p" * 200)
        server_py = _make_site_packages(deep)
        warnings = _post_install_warnings(server_py)
        assert len(warnings) == 1
        assert "espeak-ng-data" in warnings[0]

    def test_short_espeak_path_is_quiet(self, tmp_path, monkeypatch):
        # tmp_path's own length varies by machine, so raise the limit rather
        # than guess at it; the exact 159/160 boundary is covered above.
        monkeypatch.setattr(install_mod, "ESPEAK_DATA_PATH_MAX", 10_000)
        server_py = _make_site_packages(tmp_path)
        assert _post_install_warnings(server_py) == []

    @pytest.mark.asyncio
    async def test_long_path_warns_but_install_succeeds(self, install_env, tmp_path):
        install_env.server_py = _make_site_packages(tmp_path / ("q" * 200))
        result = await install_env.run()
        assert result["success"] is True
        assert len(result["warnings"]) == 1
        assert "espeak-ng data path" in result["warnings"][0]
