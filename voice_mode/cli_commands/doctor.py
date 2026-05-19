"""Doctor command for VoiceMode installation health checks.

Runs checks against installation, dependencies, audio, services, and
configuration — showing pass/fail verdicts with actionable fix commands.
"""

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import click


class CheckStatus(str, Enum):
    """Status of a health check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: CheckStatus
    message: str
    fix: Optional[str] = None


@dataclass
class Section:
    """A group of related health checks."""
    title: str
    checks: List[CheckResult] = field(default_factory=list)


# ── Check functions ──────────────────────────────────────────────────


def check_installation() -> Section:
    """Check VoiceMode installation health."""
    from voice_mode.version import get_version, is_git_repository

    section = Section(title="Installation")

    # Version
    version = get_version()
    section.checks.append(CheckResult(
        name="Version",
        status=CheckStatus.PASS,
        message=version,
    ))

    # Install method
    if is_git_repository():
        method = "Development (git)"
    elif shutil.which("uvx"):
        method = "uvx"
    elif shutil.which("pipx"):
        method = "pipx"
    else:
        method = "pip"
    section.checks.append(CheckResult(
        name="Install method",
        status=CheckStatus.PASS,
        message=method,
    ))

    # Python version
    py_version = platform.python_version()
    py_major, py_minor = sys.version_info[:2]
    if (py_major, py_minor) < (3, 10):
        section.checks.append(CheckResult(
            name="Python",
            status=CheckStatus.FAIL,
            message=f"{py_version} (requires 3.10+)",
            fix="uv python install 3.12",
        ))
    else:
        section.checks.append(CheckResult(
            name="Python",
            status=CheckStatus.PASS,
            message=py_version,
        ))

    # Python path
    section.checks.append(CheckResult(
        name="Path",
        status=CheckStatus.PASS,
        message=sys.executable,
    ))

    return section


def check_platform_info() -> Section:
    """Check platform details."""
    section = Section(title="Platform")

    os_name = platform.system()
    arch = platform.machine()
    section.checks.append(CheckResult(
        name="OS",
        status=CheckStatus.PASS,
        message=f"{os_name} {platform.release()}",
    ))
    section.checks.append(CheckResult(
        name="Architecture",
        status=CheckStatus.PASS,
        message=arch,
    ))

    # WSL detection
    if os_name == "Linux":
        try:
            with open("/proc/version", "r") as f:
                proc_version = f.read().lower()
                if "microsoft" in proc_version or "wsl" in proc_version:
                    section.checks.append(CheckResult(
                        name="WSL",
                        status=CheckStatus.WARN,
                        message="Detected (audio may require extra config)",
                    ))
        except (IOError, OSError):
            pass

    return section


def check_dependencies() -> Section:
    """Check required dependencies."""
    from voice_mode.cli_commands.status import check_ffmpeg, check_portaudio, check_uv

    section = Section(title="Dependencies")
    system = platform.system()

    # ffmpeg
    ffmpeg = check_ffmpeg()
    if ffmpeg.installed:
        msg = ffmpeg.version if ffmpeg.version else "installed"
        section.checks.append(CheckResult(
            name="ffmpeg",
            status=CheckStatus.PASS,
            message=msg,
        ))
    else:
        fix = "brew install ffmpeg" if system == "Darwin" else "sudo apt install ffmpeg"
        section.checks.append(CheckResult(
            name="ffmpeg",
            status=CheckStatus.FAIL,
            message="not found",
            fix=fix,
        ))

    # portaudio
    portaudio = check_portaudio()
    if portaudio.installed:
        section.checks.append(CheckResult(
            name="portaudio",
            status=CheckStatus.PASS,
            message="installed",
        ))
    else:
        fix = "brew install portaudio" if system == "Darwin" else "sudo apt install portaudio19-dev"
        section.checks.append(CheckResult(
            name="portaudio",
            status=CheckStatus.FAIL,
            message="not found",
            fix=fix,
        ))

    # uv
    uv = check_uv()
    if uv.installed:
        msg = uv.version if uv.version else "installed"
        section.checks.append(CheckResult(
            name="uv",
            status=CheckStatus.PASS,
            message=msg,
        ))
    else:
        section.checks.append(CheckResult(
            name="uv",
            status=CheckStatus.WARN,
            message="not found (optional)",
            fix="curl -LsSf https://astral.sh/uv/install.sh | sh",
        ))

    return section


def check_audio() -> Section:
    """Check audio subsystem."""
    section = Section(title="Audio")

    try:
        import sounddevice as sd

        section.checks.append(CheckResult(
            name="sounddevice",
            status=CheckStatus.PASS,
            message="working",
        ))

        # Count devices
        devices = sd.query_devices()
        if isinstance(devices, dict):
            # Single device returned as dict
            devices = [devices]

        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        output_devices = [d for d in devices if d.get("max_output_channels", 0) > 0]

        if input_devices:
            section.checks.append(CheckResult(
                name="Input devices",
                status=CheckStatus.PASS,
                message=f"{len(input_devices)} found",
            ))
        else:
            section.checks.append(CheckResult(
                name="Input devices",
                status=CheckStatus.WARN,
                message="none found (microphone required for voice input)",
            ))

        if output_devices:
            section.checks.append(CheckResult(
                name="Output devices",
                status=CheckStatus.PASS,
                message=f"{len(output_devices)} found",
            ))
        else:
            section.checks.append(CheckResult(
                name="Output devices",
                status=CheckStatus.WARN,
                message="none found",
            ))

        # Default input device
        try:
            default_input = sd.query_devices(kind="input")
            if default_input:
                name = default_input.get("name", "unknown")
                # Truncate long device names
                if len(name) > 40:
                    name = name[:37] + "..."
                section.checks.append(CheckResult(
                    name="Default input",
                    status=CheckStatus.PASS,
                    message=name,
                ))
        except Exception:
            pass

    except ImportError:
        section.checks.append(CheckResult(
            name="sounddevice",
            status=CheckStatus.FAIL,
            message="not installed",
            fix="uv pip install sounddevice",
        ))
    except Exception as e:
        section.checks.append(CheckResult(
            name="sounddevice",
            status=CheckStatus.FAIL,
            message=f"error: {e}",
        ))

    return section


def check_services() -> Section:
    """Check voice service status."""
    from voice_mode.cli_commands.status import (
        check_whisper_service,
        check_kokoro_service,
        check_openai_api,
        ServiceStatus,
    )

    section = Section(title="Services")

    # Whisper (STT)
    whisper = check_whisper_service()
    if whisper.status == ServiceStatus.RUNNING:
        details = f"Running (port {whisper.port})"
        if whisper.details and whisper.details.get("model"):
            details += f", model: {whisper.details['model']}"
        section.checks.append(CheckResult(
            name="Whisper (STT)",
            status=CheckStatus.PASS,
            message=details,
        ))
    elif whisper.status == ServiceStatus.FORWARDED:
        section.checks.append(CheckResult(
            name="Whisper (STT)",
            status=CheckStatus.PASS,
            message=f"Forwarded (port {whisper.port})",
        ))
    elif whisper.status == ServiceStatus.INITIALIZING:
        section.checks.append(CheckResult(
            name="Whisper (STT)",
            status=CheckStatus.WARN,
            message="Initializing...",
        ))
    elif whisper.status == ServiceStatus.NOT_INSTALLED:
        section.checks.append(CheckResult(
            name="Whisper (STT)",
            status=CheckStatus.SKIP,
            message="Not installed",
            fix="voicemode service install whisper",
        ))
    else:
        section.checks.append(CheckResult(
            name="Whisper (STT)",
            status=CheckStatus.WARN,
            message="Not running",
            fix="voicemode service start whisper",
        ))

    # Kokoro (TTS)
    kokoro = check_kokoro_service()
    if kokoro.status == ServiceStatus.RUNNING:
        details = f"Running (port {kokoro.port})"
        if kokoro.details and kokoro.details.get("voice"):
            details += f", voice: {kokoro.details['voice']}"
        section.checks.append(CheckResult(
            name="Kokoro (TTS)",
            status=CheckStatus.PASS,
            message=details,
        ))
    elif kokoro.status == ServiceStatus.FORWARDED:
        section.checks.append(CheckResult(
            name="Kokoro (TTS)",
            status=CheckStatus.PASS,
            message=f"Forwarded (port {kokoro.port})",
        ))
    elif kokoro.status == ServiceStatus.NOT_INSTALLED:
        section.checks.append(CheckResult(
            name="Kokoro (TTS)",
            status=CheckStatus.SKIP,
            message="Not installed",
            fix="voicemode service install kokoro",
        ))
    else:
        section.checks.append(CheckResult(
            name="Kokoro (TTS)",
            status=CheckStatus.WARN,
            message="Not running",
            fix="voicemode service start kokoro",
        ))

    # OpenAI API
    openai = check_openai_api()
    if openai["api_key_set"]:
        section.checks.append(CheckResult(
            name="OpenAI API",
            status=CheckStatus.PASS,
            message="Configured",
        ))
    else:
        section.checks.append(CheckResult(
            name="OpenAI API",
            status=CheckStatus.SKIP,
            message="Not configured",
        ))

    return section


def check_configuration() -> Section:
    """Check VoiceMode configuration."""
    from voice_mode.cli_commands.status import get_config_info

    section = Section(title="Configuration")

    config = get_config_info()
    config_file = Path.home() / ".voicemode" / "voicemode.env"

    # Config file
    if config.get("file"):
        section.checks.append(CheckResult(
            name="Config file",
            status=CheckStatus.PASS,
            message=config["file"],
        ))
    else:
        section.checks.append(CheckResult(
            name="Config file",
            status=CheckStatus.SKIP,
            message=f"{config_file} (not found, using defaults)",
        ))

    # Voices
    voices = config.get("voices", ["af_sky"])
    section.checks.append(CheckResult(
        name="Voices",
        status=CheckStatus.PASS,
        message=", ".join(voices),
    ))

    # Logs directory writable
    logs_dir = Path.home() / ".voicemode" / "logs"
    if logs_dir.exists():
        if os.access(logs_dir, os.W_OK):
            section.checks.append(CheckResult(
                name="Logs directory",
                status=CheckStatus.PASS,
                message=str(logs_dir),
            ))
        else:
            section.checks.append(CheckResult(
                name="Logs directory",
                status=CheckStatus.FAIL,
                message=f"{logs_dir} (not writable)",
                fix=f"chmod u+w {logs_dir}",
            ))
    else:
        # Will be created on first use — not an error
        section.checks.append(CheckResult(
            name="Logs directory",
            status=CheckStatus.PASS,
            message=f"{logs_dir} (will be created on first use)",
        ))

    return section


def check_connect() -> Optional[Section]:
    """Check VoiceMode Connect status. Returns None if Connect is not configured."""
    try:
        from voice_mode.auth import get_valid_credentials, load_credentials
    except ImportError:
        return None

    # Only show this section if the user has attempted to use Connect
    creds = load_credentials()
    if creds is None:
        return None

    section = Section(title="Connect")

    valid_creds = get_valid_credentials(auto_refresh=False)
    if valid_creds is not None:
        user_info = valid_creds.user_info or {}
        email = user_info.get("email", "authenticated")
        section.checks.append(CheckResult(
            name="Auth",
            status=CheckStatus.PASS,
            message=email,
        ))
    else:
        section.checks.append(CheckResult(
            name="Auth",
            status=CheckStatus.WARN,
            message="Token expired or invalid",
            fix="voicemode connect auth login",
        ))

    return section


def check_updates() -> Section:
    """Check for VoiceMode updates on PyPI."""
    from voice_mode.__version__ import __version__ as current_version

    section = Section(title="Updates")

    try:
        import httpx

        resp = httpx.get(
            "https://pypi.org/pypi/voice-mode/json",
            timeout=5.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("info", {}).get("version", "unknown")

            if latest == current_version:
                section.checks.append(CheckResult(
                    name="voice-mode",
                    status=CheckStatus.PASS,
                    message=f"{current_version} (latest)",
                ))
            else:
                section.checks.append(CheckResult(
                    name="voice-mode",
                    status=CheckStatus.WARN,
                    message=f"{current_version} → {latest} available",
                    fix="uvx voice-mode@latest --help",
                ))
        else:
            section.checks.append(CheckResult(
                name="voice-mode",
                status=CheckStatus.SKIP,
                message=f"{current_version} (PyPI check failed)",
            ))
    except ImportError:
        # httpx not available — try urllib as fallback
        try:
            import urllib.request

            req = urllib.request.Request(
                "https://pypi.org/pypi/voice-mode/json",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                latest = data.get("info", {}).get("version", "unknown")

                if latest == current_version:
                    section.checks.append(CheckResult(
                        name="voice-mode",
                        status=CheckStatus.PASS,
                        message=f"{current_version} (latest)",
                    ))
                else:
                    section.checks.append(CheckResult(
                        name="voice-mode",
                        status=CheckStatus.WARN,
                        message=f"{current_version} → {latest} available",
                        fix="uvx voice-mode@latest --help",
                    ))
        except Exception:
            section.checks.append(CheckResult(
                name="voice-mode",
                status=CheckStatus.SKIP,
                message=f"{current_version} (update check failed)",
            ))
    except Exception:
        section.checks.append(CheckResult(
            name="voice-mode",
            status=CheckStatus.SKIP,
            message=f"{current_version} (update check failed)",
        ))

    return section


# ── Formatting ───────────────────────────────────────────────────────


def _status_symbol(status: CheckStatus, use_colors: bool) -> str:
    """Return a colored status symbol."""
    if status == CheckStatus.PASS:
        sym = "✓"
        return click.style(sym, fg="green") if use_colors else sym
    elif status == CheckStatus.FAIL:
        sym = "✗"
        return click.style(sym, fg="red") if use_colors else sym
    elif status == CheckStatus.WARN:
        sym = "!"
        return click.style(sym, fg="yellow") if use_colors else sym
    else:  # SKIP
        sym = "-"
        return click.style(sym, fg="bright_black") if use_colors else sym


def format_doctor_output(sections: List[Section], use_colors: bool = True) -> str:
    """Format doctor output with tree connectors."""
    lines: List[str] = []
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}

    for section in sections:
        # Section header
        title = section.title
        if use_colors:
            title = click.style(title, bold=True)
        lines.append(f" {title}")

        for i, check in enumerate(section.checks):
            is_last = i == len(section.checks) - 1 and not (
                check.fix and check.status in (CheckStatus.FAIL, CheckStatus.WARN)
            )

            connector = " └ " if is_last else " ├ "
            sym = _status_symbol(check.status, use_colors)
            lines.append(f"{connector}{check.name}: {check.message} {sym}")

            # Show fix command on next line
            if check.fix and check.status in (CheckStatus.FAIL, CheckStatus.WARN):
                is_last_with_fix = i == len(section.checks) - 1
                prefix = " " if is_last_with_fix else " │"
                fix_text = check.fix
                if use_colors:
                    fix_text = click.style(fix_text, fg="cyan")
                lines.append(f"{prefix}   Fix: {fix_text}")

            counts[check.status.value] += 1

        lines.append("")

    # Summary line
    total_issues = counts["fail"] + counts["warn"]
    parts = []
    if counts["pass"]:
        part = f"{counts['pass']} passed"
        parts.append(click.style(part, fg="green") if use_colors else part)
    if counts["fail"]:
        part = f"{counts['fail']} failed"
        parts.append(click.style(part, fg="red") if use_colors else part)
    if counts["warn"]:
        part = f"{counts['warn']} warning{'s' if counts['warn'] != 1 else ''}"
        parts.append(click.style(part, fg="yellow") if use_colors else part)
    if counts["skip"]:
        part = f"{counts['skip']} skipped"
        parts.append(click.style(part, fg="bright_black") if use_colors else part)

    summary = ", ".join(parts)
    if total_issues == 0:
        label = "All checks passed"
        if use_colors:
            label = click.style(label, fg="green", bold=True)
    else:
        label = "Summary"
    lines.append(f" {label}: {summary}")

    return "\n".join(lines)


def format_doctor_json(sections: List[Section]) -> str:
    """Format doctor output as structured JSON."""
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    output_sections = []

    for section in sections:
        checks = []
        for check in section.checks:
            counts[check.status.value] += 1
            entry: Dict[str, Any] = {
                "name": check.name,
                "status": check.status.value,
                "message": check.message,
            }
            if check.fix:
                entry["fix"] = check.fix
            checks.append(entry)

        output_sections.append({
            "title": section.title,
            "checks": checks,
        })

    result = {
        "sections": output_sections,
        "summary": {
            "passed": counts["pass"],
            "failed": counts["fail"],
            "warnings": counts["warn"],
            "skipped": counts["skip"],
            "total": sum(counts.values()),
        },
    }

    return json.dumps(result, indent=2)


# ── CLI command ──────────────────────────────────────────────────────


@click.command()
@click.help_option("-h", "--help")
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["terminal", "json"]),
    default=None,
    help="Output format (default: auto-detect based on TTY)",
)
@click.option("--no-color", is_flag=True, help="Disable colored output")
def doctor(output_format: Optional[str], no_color: bool):
    """Check VoiceMode installation health.

    Runs checks against installation, dependencies, audio, services, and
    configuration — showing pass/fail verdicts with actionable fix commands.

    \b
    Examples:
      voicemode doctor              # Terminal output with colors
      voicemode doctor -f json      # JSON for automation
      voicemode doctor --no-color   # Plain text without colors
    """
    # Collect all sections
    sections: List[Section] = [
        check_installation(),
        check_platform_info(),
        check_dependencies(),
        check_audio(),
        check_services(),
        check_configuration(),
    ]

    # Connect section only if configured
    connect_section = check_connect()
    if connect_section is not None:
        sections.append(connect_section)

    sections.append(check_updates())

    # Determine output format
    if output_format is None:
        output_format = "terminal" if sys.stdout.isatty() else "json"

    # Respect NO_COLOR
    use_colors = not no_color and not os.environ.get("NO_COLOR")

    if output_format == "json":
        click.echo(format_doctor_json(sections))
    else:
        click.echo(format_doctor_output(sections, use_colors=use_colors))
