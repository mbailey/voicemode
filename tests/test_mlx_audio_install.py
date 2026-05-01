"""Tests for the mlx-audio service install pipeline.

Covers:
- Apple-Silicon hardware gate (short-circuits before any subprocess).
- The ``MLX_AUDIO_EXTRAS`` list shape and the install-command generator.
- Service config + template wiring (plist/systemd) for ``mlx_audio``.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.tools.mlx_audio.install import (
    MLX_AUDIO_DEFAULT_PORT,
    MLX_AUDIO_EXTRAS,
    MLX_AUDIO_PIP_PACKAGE,
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
    """The pip-package spec must keep the ``>=0.4.3`` floor."""

    def test_pip_package_specifier_pins_at_or_above_0_4_3(self):
        # 0.4.3 is the first upstream release that absorbed the MLX Metal
        # serialisation lock + OpenAI-style STT response_format fixes that
        # voicemode used to ship as a bundled patch (see VM-1126). Older
        # mlx-audio releases will misbehave on real workloads.
        assert MLX_AUDIO_PIP_PACKAGE.startswith("mlx-audio")
        assert ">=0.4.3" in MLX_AUDIO_PIP_PACKAGE


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


# (Removed VM-1126: server.py patch tests + _query_installed_version tests.
# Both fixes were upstreamed in mlx-audio 0.4.3 so voicemode no longer
# ships a patch nor needs to query the installed version.)


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
# Bundled patch resource (restored VM-1128)
# ============================================================================
# voice_mode/data/patches/mlx_audio_server.patch ships the OpenAI-style STT
# response_format handling that mlx-audio 0.4.3 still does NOT provide.
# (VM-1126 incorrectly removed it on the assumption that all fixes were
# upstreamed; only the inference lock was. VM-1128 restores the
# response_format half against the 0.4.3 endpoint shape.)


class TestBundledPatchShips:
    """The patch file and its sentinel must exist and be wired through."""

    def test_patch_file_exists(self):
        from voice_mode.tools.mlx_audio.install import _PATCH_RESOURCE
        assert _PATCH_RESOURCE.exists(), (
            f"Bundled patch missing at {_PATCH_RESOURCE}. "
            "Wheel/sdist will ship without STT response_format support."
        )

    def test_patch_sentinel_present_in_patch(self):
        """The sentinel must literally appear in the patch -- otherwise
        applying the patch can never satisfy the post-patch sanity check."""
        from voice_mode.tools.mlx_audio.install import (
            _PATCH_RESOURCE,
            PATCH_SENTINEL,
        )
        text = _PATCH_RESOURCE.read_text(encoding="utf-8")
        assert PATCH_SENTINEL in text, (
            f"Sentinel {PATCH_SENTINEL!r} not found in patch content. "
            "Either the sentinel constant or the patch comment has drifted."
        )

    def test_patch_targets_response_format(self):
        """Smoke test: patch should add response_format form param and the
        text/json/verbose_json branching block."""
        from voice_mode.tools.mlx_audio.install import _PATCH_RESOURCE
        text = _PATCH_RESOURCE.read_text(encoding="utf-8")
        assert "response_format: str = Form" in text
        assert "PlainTextResponse" in text
        assert "JSONResponse" in text

    def test_pyproject_includes_patches_glob(self):
        """The wheel target must include *.patch under data/ or the patch
        file silently won't ship to PyPI."""
        pyproject = (
            Path(__file__).parent.parent / "pyproject.toml"
        ).read_text(encoding="utf-8")
        assert "voice_mode/data/**/*.patch" in pyproject, (
            "pyproject.toml [tool.hatch.build.targets.wheel].include is "
            "missing the *.patch glob -- the bundled patch will not ship."
        )
