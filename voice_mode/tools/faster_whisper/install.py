"""Installation tool for the faster-whisper (speaches) STT service.

speaches is a Python server that exposes an OpenAI-compatible
``/v1/audio/transcriptions`` endpoint backed by faster-whisper, with
support for ``verbose_json`` and word-level timestamps.

Install layout::

    ~/.local/bin/speaches            # uv-tool-managed entry point
    ~/.local/share/uv/tools/speaches/  # uv-managed isolated env

The install pipeline is:

1. ``uv tool install 'speaches>=0.4.0'`` — installs the speaches CLI.
2. Render ``start-faster-whisper-server.sh`` from the bundled template
   into ``~/.voicemode/services/faster-whisper/bin/``.
3. Register a launchd plist (macOS) / systemd unit (Linux) named
   ``com.voicemode.faster-whisper`` / ``voicemode-faster-whisper``.
4. Append ``http://127.0.0.1:{FASTER_WHISPER_PORT}/v1`` to
   ``VOICEMODE_STT_BASE_URLS`` in ``~/.voicemode/voicemode.env`` if
   not already present.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from voice_mode.config import FASTER_WHISPER_PORT, SERVICE_AUTO_ENABLE

logger = logging.getLogger("voicemode")

# Package specification for uv tool install
SPEACHES_PIP_PACKAGE = "speaches>=0.4.0"

# Service names used by launchd / systemd
LAUNCHD_SERVICE_NAME = "com.voicemode.faster-whisper"
SYSTEMD_SERVICE_NAME = "voicemode-faster-whisper"


def _coerce_bool(value: Union[bool, str, None]) -> Optional[bool]:
    """Permissive bool coercion for MCP/CLI string args."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "y", "on"):
            return True
        if normalized in ("false", "0", "no", "n", "off"):
            return False
    return None


def _coerce_int(value: Union[int, str], default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            logger.warning("Invalid int value %r, using default %d", value, default)
    return default


def _ensure_uv_available() -> Optional[str]:
    """Ensure ``uv`` is on PATH; install via the official script if missing.

    Returns an error string on failure, ``None`` on success.
    """
    if shutil.which("uv"):
        return None

    logger.info("uv not found, installing via astral.sh installer...")
    try:
        subprocess.run(
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            shell=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to install uv: {exc}"

    cargo_bin = os.path.expanduser("~/.cargo/bin")
    local_bin = os.path.expanduser("~/.local/bin")
    os.environ["PATH"] = f"{cargo_bin}:{local_bin}:{os.environ.get('PATH', '')}"

    if not shutil.which("uv"):
        return "uv was installed but is not on PATH"
    return None


def _build_install_cmd(force_reinstall: bool) -> List[str]:
    """Build the ``uv tool install`` command."""
    cmd: List[str] = ["uv", "tool", "install", SPEACHES_PIP_PACKAGE]
    if force_reinstall:
        cmd.append("--reinstall")
    return cmd


def _render_start_script(install_dir: Path) -> Path:
    """Render the start-faster-whisper-server.sh template into bin/."""
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Load template from bundled package resources
    template_path = (
        Path(__file__).resolve().parent.parent.parent
        / "templates"
        / "scripts"
        / "start-faster-whisper-server.sh"
    )
    if template_path.exists():
        content = template_path.read_text(encoding="utf-8")
    else:
        # Fallback inline template
        content = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'PORT="${VOICEMODE_FASTER_WHISPER_PORT:-2023}"\n'
            "exec speaches serve --host 127.0.0.1 --port \"$PORT\"\n"
        )

    script = bin_dir / "start-faster-whisper-server.sh"
    script.write_text(content, encoding="utf-8")
    script.chmod(0o755)
    return script


def _append_stt_url_to_env(port: int, voicemode_dir: Path) -> None:
    """Append the faster-whisper endpoint to VOICEMODE_STT_BASE_URLS if absent."""
    env_file = voicemode_dir / "voicemode.env"
    endpoint = f"http://127.0.0.1:{port}/v1"

    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if endpoint in content:
            logger.debug("faster-whisper endpoint already present in voicemode.env")
            return
        # Try to append to existing VOICEMODE_STT_BASE_URLS line
        lines = content.splitlines(keepends=True)
        updated = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("VOICEMODE_STT_BASE_URLS=") and endpoint not in stripped:
                # Strip trailing newline, append endpoint
                new_line = stripped.rstrip() + f",{endpoint}\n"
                lines[i] = new_line
                updated = True
                break
        if updated:
            env_file.write_text("".join(lines), encoding="utf-8")
            logger.info("Appended faster-whisper URL to VOICEMODE_STT_BASE_URLS")
            return

    # No existing entry — append a new variable
    with env_file.open("a", encoding="utf-8") as f:
        f.write(f"\nVOICEMODE_STT_BASE_URLS={endpoint}\n")
    logger.info("Added VOICEMODE_STT_BASE_URLS=%s to voicemode.env", endpoint)


async def _register_service(
    script_path: Path,
    voicemode_dir: Path,
    log_dir: Path,
    auto_enable: Optional[bool],
) -> Dict[str, Any]:
    """Register launchd plist (macOS) or systemd unit (Linux)."""
    system = platform.system()
    result: Dict[str, Any] = {"success": False}

    if system == "Darwin":
        launchagents_dir = Path.home() / "Library" / "LaunchAgents"
        launchagents_dir.mkdir(parents=True, exist_ok=True)

        plist_name = f"{LAUNCHD_SERVICE_NAME}.plist"
        plist_path = launchagents_dir / plist_name

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/faster-whisper.out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/faster-whisper.err.log</string>
</dict>
</plist>
"""
        # Best-effort unload of stale entry
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
        )

        plist_path.write_text(plist_content, encoding="utf-8")
        result["success"] = True
        result["service_path"] = str(plist_path)

        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            logger.info("Auto-enabling faster-whisper service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("faster_whisper")
            result["enabled"] = "✅" in enable_result
            if not result["enabled"]:
                logger.warning("faster-whisper auto-enable failed: %s", enable_result)

    elif system == "Linux":
        systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
        systemd_user_dir.mkdir(parents=True, exist_ok=True)

        service_name = f"{SYSTEMD_SERVICE_NAME}.service"
        service_path = systemd_user_dir / service_name

        service_content = f"""[Unit]
Description=faster-whisper (speaches) Speech Recognition Server
After=network.target

[Service]
Type=simple
ExecStart={script_path}
Restart=on-failure
RestartSec=10
StandardOutput=append:{log_dir}/faster-whisper.out.log
StandardError=append:{log_dir}/faster-whisper.err.log

[Install]
WantedBy=default.target
"""
        service_path.write_text(service_content, encoding="utf-8")

        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        except subprocess.CalledProcessError as exc:
            logger.warning("systemctl daemon-reload failed: %s", exc)

        result["success"] = True
        result["service_path"] = str(service_path)

        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            logger.info("Auto-enabling faster-whisper service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("faster_whisper")
            result["enabled"] = "✅" in enable_result
            if not result["enabled"]:
                logger.warning("faster-whisper auto-enable failed: %s", enable_result)

    else:
        result["success"] = False
        result["error"] = f"Unsupported platform: {system}"

    return result


async def faster_whisper_install(
    port: Union[int, str] = FASTER_WHISPER_PORT,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
) -> Dict[str, Any]:
    """Install faster-whisper (speaches) as a voicemode STT service.

    Installs the ``speaches`` package via ``uv tool install``, writes the
    start script to ``~/.voicemode/services/faster-whisper/bin/``, registers
    a launchd plist (macOS) or systemd unit (Linux), and appends the endpoint
    URL to ``VOICEMODE_STT_BASE_URLS`` in ``~/.voicemode/voicemode.env``.

    Args:
        port: Local TCP port (default 2023 — VOICEMODE_FASTER_WHISPER_PORT).
        force_reinstall: Pass ``--reinstall`` to ``uv tool install`` —
            forces a reinstall even if speaches is already present.
        auto_enable: Enable the service after install. ``None`` falls back
            to ``VOICEMODE_SERVICE_AUTO_ENABLE``.

    Returns:
        Dict with ``success``, ``install_path``, ``service_url``, and
        ``service_path``.
    """
    if sys.version_info < (3, 10):
        return {
            "success": False,
            "error": f"Python 3.10+ required. Current: {sys.version}",
        }

    port_int = _coerce_int(port, FASTER_WHISPER_PORT)
    force_bool = bool(_coerce_bool(force_reinstall))
    auto_enable_val = _coerce_bool(auto_enable)

    voicemode_dir = Path(
        os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    )
    voicemode_dir.mkdir(parents=True, exist_ok=True)

    install_dir = voicemode_dir / "services" / "faster-whisper"
    log_dir = voicemode_dir / "logs" / "faster-whisper"
    install_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    os.environ["VOICEMODE_FASTER_WHISPER_PORT"] = str(port_int)

    uv_error = _ensure_uv_available()
    if uv_error:
        return {"success": False, "error": uv_error}

    cmd = _build_install_cmd(force_bool)
    logger.info("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        return {
            "success": False,
            "error": f"`{' '.join(cmd)}` failed",
            "stderr": (exc.stderr or b"").decode(errors="replace"),
        }

    entry_point = Path.home() / ".local" / "bin" / "speaches"
    if not entry_point.exists():
        # uv on some systems puts binaries in ~/.cargo/bin or a custom uv bin dir
        alt = shutil.which("speaches")
        if alt:
            entry_point = Path(alt)
        else:
            return {
                "success": False,
                "error": (
                    f"`uv tool install {SPEACHES_PIP_PACKAGE}` succeeded but "
                    "the `speaches` binary could not be found. Check `uv tool list`."
                ),
            }

    # Render the start script from template
    try:
        script_path = _render_start_script(install_dir)
    except OSError as exc:
        return {
            "success": False,
            "error": f"Failed to write start script: {exc}",
            "install_path": str(install_dir),
        }

    # Register platform service
    service_result = await _register_service(
        script_path, voicemode_dir, log_dir, auto_enable_val
    )
    if not service_result.get("success"):
        return {
            "success": False,
            "error": f"Service registration failed: {service_result.get('error')}",
            "install_path": str(install_dir),
        }

    # Append endpoint to voicemode.env
    try:
        _append_stt_url_to_env(port_int, voicemode_dir)
    except OSError as exc:
        logger.warning("Could not update voicemode.env: %s", exc)

    return {
        "success": True,
        "install_path": str(install_dir),
        "entry_point": str(entry_point),
        "service_path": service_result.get("service_path"),
        "service_url": f"http://127.0.0.1:{port_int}",
        "port": port_int,
        "auto_enabled": service_result.get("enabled", False),
        "message": (
            f"speaches installed via uv tool install. "
            f"Entry point: {entry_point}. "
            f"Service URL: http://127.0.0.1:{port_int}/v1."
        ),
    }
