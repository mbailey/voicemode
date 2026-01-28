"""
CLI entry points for voice-mode package.
"""
import asyncio
import sys
import os
import warnings
import subprocess
import shutil
import click

# Import version info
try:
    from voice_mode.version import __version__
except ImportError:
    __version__ = "unknown"

# Import configuration constants
from voice_mode.config import (
    DEFAULT_WHISPER_MODEL,
    DEFAULT_LISTEN_DURATION,
    MIN_RECORDING_DURATION,
    SERVE_ALLOW_LOCAL,
    SERVE_ALLOW_ANTHROPIC,
    SERVE_ALLOW_TAILSCALE,
    SERVE_ALLOWED_IPS,
    SERVE_SECRET,
    SERVE_TOKEN,
    SERVE_TRANSPORT,
)


# Suppress known deprecation warnings for better user experience
# These apply to both CLI commands and MCP server operation
# They can be shown with VOICEMODE_DEBUG=true or --debug flag
if not os.environ.get('VOICEMODE_DEBUG', '').lower() in ('true', '1', 'yes'):
    # Suppress audioop deprecation warning from pydub
    warnings.filterwarnings('ignore', message='.*audioop.*deprecated.*', category=DeprecationWarning)
    # Suppress pkg_resources deprecation warning from webrtcvad
    warnings.filterwarnings('ignore', message='.*pkg_resources.*deprecated.*', category=UserWarning)
    # Suppress psutil connections() deprecation warning
    warnings.filterwarnings('ignore', message='.*connections.*deprecated.*', category=DeprecationWarning)
    
    # Also suppress INFO logging for CLI commands (but not for MCP server)
    import logging
    logging.getLogger("voicemode").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Service management CLI - runs MCP server by default, subcommands override
@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="VoiceMode")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--debug', is_flag=True, help='Enable debug mode and show all warnings')
@click.option('--tools-enabled', help='Comma-separated list of tools to enable (whitelist)')
@click.option('--tools-disabled', help='Comma-separated list of tools to disable (blacklist)')
@click.pass_context
def voice_mode_main_cli(ctx, debug, tools_enabled, tools_disabled):
    """Voice Mode - MCP server and service management.

    Without arguments, starts the MCP server.
    With subcommands, executes service management operations.
    """
    if debug:
        # Re-enable warnings if debug flag is set
        warnings.resetwarnings()
        os.environ['VOICEMODE_DEBUG'] = 'true'
        # Re-enable INFO logging
        import logging
        logging.getLogger("voicemode").setLevel(logging.INFO)

    # Set environment variables from CLI args
    if tools_enabled:
        os.environ['VOICEMODE_TOOLS_ENABLED'] = tools_enabled
    if tools_disabled:
        os.environ['VOICEMODE_TOOLS_DISABLED'] = tools_disabled

    if ctx.invoked_subcommand is None:
        # No subcommand - run MCP server
        # Note: warnings are already suppressed at module level unless debug is enabled
        from .server import main as voice_mode_main
        voice_mode_main()


def voice_mode() -> None:
    """Entry point for voicemode command - starts the MCP server or runs subcommands."""
    voice_mode_main_cli()


# ============================================================================
# Unified Service Command Group
# ============================================================================
# All service management commands under a single group:
#   voicemode service start <service>
#   voicemode service stop <service>
#   voicemode service status [service]
# etc.

VALID_SERVICES = ['whisper', 'kokoro', 'voicemode']


@voice_mode_main_cli.group()
@click.help_option('-h', '--help')
def service():
    """Manage VoiceMode services.

    \b
    Services:
      whisper    Local speech-to-text (STT) on port 2022
      kokoro     Local text-to-speech (TTS) on port 8880
      voicemode  HTTP MCP server for remote access on port 8765

    \b
    Quick Start:
      voicemode service status           # Check all services
      voicemode service start whisper    # Start Whisper STT
      voicemode service enable voicemode # Auto-start HTTP server

    \b
    Service Lifecycle:
      install  Install service software (whisper, kokoro)
      start    Start a service
      stop     Stop a service
      restart  Restart a service
      status   Show service status
      enable   Enable auto-start at boot/login
      disable  Disable auto-start
      logs     View service logs
      health   Check if service is responding
    """
    pass


@service.command('start')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_start(service_name):
    """Start a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service(service_name))
    click.echo(result)


@service.command('stop')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_stop(service_name):
    """Stop a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service(service_name))
    click.echo(result)


@service.command('restart')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_restart(service_name):
    """Restart a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service(service_name))
    click.echo(result)


@service.command('status')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), required=False, metavar='SERVICE')
@click.help_option('-h', '--help')
def service_status(service_name):
    """Show service status.

    \b
    Without arguments, shows status for all services.
    With a service name, shows detailed status for that service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access

    \b
    Examples:
      voicemode service status          # Show all services
      voicemode service status whisper  # Show only Whisper
      voicemode service status voicemode # Show HTTP server status
    """
    from voice_mode.tools.service import status_service

    if service_name:
        # Show specific service
        result = asyncio.run(status_service(service_name))
        click.echo(result)
    else:
        # Show all services
        click.echo("VoiceMode Service Status")
        click.echo("=" * 50)
        for svc in VALID_SERVICES:
            result = asyncio.run(status_service(svc))
            click.echo(f"\n{svc.upper()}:")
            click.echo(result)


@service.command('enable')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_enable(service_name):
    """Enable a service to start at boot/login.

    \b
    On macOS, creates a launchd plist in ~/Library/LaunchAgents/
    On Linux, creates a systemd user service in ~/.config/systemd/user/

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service(service_name))
    click.echo(result)


@service.command('disable')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_disable(service_name):
    """Disable a service from starting at boot/login.

    \b
    Removes the service from launchd (macOS) or systemd (Linux).
    The service will stop running and won't start after reboot.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service(service_name))
    click.echo(result)


@service.command('logs')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
@click.help_option('-h', '--help')
def service_logs(service_name, lines):
    """View service logs.

    \b
    On macOS, reads from ~/Library/Logs/ or ~/.voicemode/logs/
    On Linux, uses journalctl for systemd services

    \b
    Examples:
      voicemode service logs whisper       # Last 50 lines
      voicemode service logs voicemode -n 100  # Last 100 lines
    """
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs(service_name, lines))
    click.echo(result)


@service.command('health')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_health(service_name):
    """Check the health endpoint of a service.

    \b
    Checks if the service is responding on its expected port:
      whisper    Port 2022
      kokoro     Port 8880
      voicemode  Port 8765 (configurable via VOICEMODE_SERVE_PORT)
    """
    if service_name == 'whisper':
        port = 2022
        display_name = 'Whisper'
    elif service_name == 'kokoro':
        port = 8880
        display_name = 'Kokoro'
    else:
        click.echo(f"❌ Unknown service: {service_name}")
        return

    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://127.0.0.1:{port}/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo(f"✅ {display_name} is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo(f"✅ {display_name} is responding (non-JSON response)")
        else:
            click.echo(f"❌ {display_name} not responding on port {port}")
    except subprocess.TimeoutExpired:
        click.echo(f"❌ {display_name} health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@service.command('install')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.help_option('-h', '--help')
def service_install(service_name, force):
    """Install a voice service.

    \b
    Downloads and installs the service software:
      whisper    whisper.cpp speech-to-text server
      kokoro     Kokoro text-to-speech server
      voicemode  Already installed (enables the HTTP server)

    \b
    Examples:
      voicemode service install whisper
      voicemode service install kokoro --force
    """
    if service_name == 'whisper':
        from voice_mode.tools.whisper.install import whisper_install
        result = asyncio.run(whisper_install.fn(force_reinstall=force))
        # Handle dict result from tool
        if isinstance(result, dict):
            if result.get("success"):
                click.echo(f"✅ Whisper installed successfully")
                if result.get('install_path'):
                    click.echo(f"   Install path: {result['install_path']}")
            else:
                click.echo(f"❌ Whisper installation failed: {result.get('error', 'Unknown error')}")
        else:
            click.echo(result)
    elif service_name == 'kokoro':
        from voice_mode.tools.kokoro.install import kokoro_install
        result = asyncio.run(kokoro_install.fn(force_reinstall=force))
        if isinstance(result, dict):
            if result.get("success"):
                click.echo(f"✅ Kokoro installed successfully")
                if result.get('install_path'):
                    click.echo(f"   Install path: {result['install_path']}")
            else:
                click.echo(f"❌ Kokoro installation failed: {result.get('error', 'Unknown error')}")
        else:
            click.echo(result)
    elif service_name == 'voicemode':
        from voice_mode.tools.service import install_voicemode_start_script
        result = asyncio.run(install_voicemode_start_script())
        if result.get("success"):
            click.echo(f"✅ VoiceMode start script installed successfully")
            if result.get('start_script'):
                click.echo(f"   Start script: {result['start_script']}")
        else:
            click.echo(f"❌ VoiceMode installation failed: {result.get('error', 'Unknown error')}")
    else:
        click.echo(f"❌ Unknown service: {service_name}")


# ============================================================================
# Legacy Service Groups (Deprecated)
# ============================================================================
# These are hidden from help/tab completion but still functional for backward
# compatibility. Use 'voicemode service <action> <service>' instead.

@voice_mode_main_cli.group(hidden=True)
@click.help_option('-h', '--help', help='Show this message and exit')
def kokoro():
    """Manage Kokoro TTS service. [DEPRECATED: Use 'voicemode service' instead]"""
    pass


@voice_mode_main_cli.group(hidden=True)
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper():
    """Manage Whisper STT service. [DEPRECATED: Use 'voicemode service' instead]"""
    pass


# Service functions are imported lazily in their respective command handlers to improve startup time


# Kokoro service commands (deprecated - hidden from help but still functional)
@kokoro.command(hidden=True)
def status():
    """(Deprecated) Show Kokoro service status. Use 'voicemode service status kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service status kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def start():
    """(Deprecated) Start Kokoro service. Use 'voicemode service start kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service start kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def stop():
    """(Deprecated) Stop Kokoro service. Use 'voicemode service stop kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service stop kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def restart():
    """(Deprecated) Restart Kokoro service. Use 'voicemode service restart kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service restart kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def enable():
    """(Deprecated) Enable Kokoro service. Use 'voicemode service enable kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service enable kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def disable():
    """(Deprecated) Disable Kokoro service. Use 'voicemode service disable kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service disable kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def logs(lines):
    """(Deprecated) View Kokoro logs. Use 'voicemode service logs kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service logs kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("kokoro", lines))
    click.echo(result)


@kokoro.command(hidden=True)
def health():
    """Check Kokoro health endpoint."""
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8880/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo("✅ Kokoro is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo("✅ Kokoro is responding (non-JSON response)")
        else:
            click.echo("❌ Kokoro not responding on port 8880")
    except subprocess.TimeoutExpired:
        click.echo("❌ Kokoro health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@kokoro.command()
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install kokoro-fastapi')
@click.option('--port', default=8880, help='Port to configure for the service')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
def install(install_dir, port, force, version, auto_enable, skip_deps):
    """Install kokoro-fastapi TTS service."""
    from voice_mode.tools.kokoro.install import kokoro_install
    result = asyncio.run(kokoro_install.fn(
        install_dir=install_dir,
        port=port,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable,
        skip_deps=skip_deps
    ))
    
    if result.get('success'):
        if result.get('already_installed'):
            click.echo(f"✅ Kokoro already installed at {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
        else:
            click.echo("✅ Kokoro installed successfully!")
            click.echo(f"   Install path: {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
            
        if result.get('enabled'):
            click.echo("   Auto-start: Enabled")
        
        if result.get('migration_message'):
            click.echo(f"\n{result['migration_message']}")
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@kokoro.command()
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Kokoro models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Kokoro data including logs and cache')
@click.confirmation_option(prompt='Are you sure you want to uninstall Kokoro?')
def uninstall(remove_models, remove_all_data):
    """Uninstall kokoro-fastapi service and optionally remove data."""
    from voice_mode.tools.kokoro.uninstall import kokoro_uninstall
    result = asyncio.run(kokoro_uninstall.fn(
        remove_models=remove_models,
        remove_all_data=remove_all_data
    ))
    
    if result.get('success'):
        click.echo("✅ Kokoro uninstalled successfully!")
        
        if result.get('service_stopped'):
            click.echo("   Service stopped")
        if result.get('service_disabled'):
            click.echo("   Service disabled")
        if result.get('install_removed'):
            click.echo(f"   Installation removed: {result['install_path']}")
        if result.get('models_removed'):
            click.echo("   Models removed")
        if result.get('data_removed'):
            click.echo("   All data removed")
            
        if result.get('warnings'):
            click.echo("\n⚠️  Warnings:")
            for warning in result['warnings']:
                click.echo(f"   - {warning}")
    else:
        click.echo(f"❌ Uninstall failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


# Create service group for whisper
@whisper.group("service")
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper_service():
    """Manage Whisper service."""
    pass

# Service commands under the group
@whisper_service.command("status")
def whisper_service_status():
    """Show Whisper service status."""
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("whisper"))
    click.echo(result)


@whisper_service.command("start")
def whisper_service_start():
    """Start Whisper service."""
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("whisper"))
    click.echo(result)


@whisper_service.command("stop")
def whisper_service_stop():
    """Stop Whisper service."""
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("whisper"))
    click.echo(result)


@whisper_service.command("restart")
def whisper_service_restart():
    """Restart Whisper service."""
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("whisper"))
    click.echo(result)


@whisper_service.command("enable")
def whisper_service_enable():
    """Enable Whisper service to start at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("whisper"))
    click.echo(result)


@whisper_service.command("disable")
def whisper_service_disable():
    """Disable Whisper service from starting at boot/login."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("whisper"))
    click.echo(result)


@whisper_service.command("logs")
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def whisper_service_logs(lines):
    """View Whisper service logs."""
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("whisper", lines))
    click.echo(result)


@whisper_service.command("health")
def whisper_service_health():
    """Check Whisper health endpoint."""
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:2022/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo("✅ Whisper is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo("✅ Whisper is responding (non-JSON response)")
        else:
            click.echo("❌ Whisper not responding on port 2022")
    except subprocess.TimeoutExpired:
        click.echo("❌ Whisper health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@whisper_service.command("install")
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install whisper.cpp')
@click.option('--model', default=DEFAULT_WHISPER_MODEL, help=f'Whisper model to download (default: {DEFAULT_WHISPER_MODEL})')
@click.option('--use-gpu/--no-gpu', default=None, help='Enable GPU support if available')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
def whisper_service_install(install_dir, model, use_gpu, force, version, auto_enable, skip_deps):
    """Install whisper.cpp STT service with automatic system detection."""
    from voice_mode.tools.whisper.install import whisper_install
    result = asyncio.run(whisper_install.fn(
        install_dir=install_dir,
        model=model,
        use_gpu=use_gpu,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable,
        skip_deps=skip_deps
    ))
    
    if result.get('success'):
        if result.get('already_installed'):
            click.echo(f"✅ Whisper already installed at {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
        else:
            click.echo("✅ Whisper installed successfully!")
            click.echo(f"   Install path: {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
            
        if result.get('gpu_enabled'):
            click.echo("   GPU support: Enabled")
        if result.get('model_downloaded'):
            click.echo(f"   Model: {result.get('model', 'unknown')}")
        if result.get('enabled'):
            click.echo("   Auto-start: Enabled")
        
        if result.get('migration_message'):
            click.echo(f"\n{result['migration_message']}")
            
        if result.get('next_steps'):
            click.echo("\nNext steps:")
            for step in result['next_steps']:
                click.echo(f"   - {step}")

        # Show warning if model download failed (GH-174)
        if result.get('model_error'):
            click.echo()
            click.secho("⚠️  Model download failed:", fg='yellow', bold=True)
            click.secho(f"   {result['model_error']}", fg='yellow')
            click.echo("   Whisper won't work without a model.")
            click.echo("   Try: voicemode whisper model install")
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@whisper_service.command("uninstall")
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Whisper models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Whisper data including logs and transcriptions')
@click.confirmation_option(prompt='Are you sure you want to uninstall Whisper?')
def whisper_service_uninstall(remove_models, remove_all_data):
    """Uninstall whisper.cpp and optionally remove models and data."""
    from voice_mode.tools.whisper.uninstall import whisper_uninstall
    result = asyncio.run(whisper_uninstall.fn(
        remove_models=remove_models,
        remove_all_data=remove_all_data
    ))
    
    if result.get('success'):
        click.echo("✅ Whisper uninstalled successfully!")
        
        if result.get('service_stopped'):
            click.echo("   Service stopped")
        if result.get('service_disabled'):
            click.echo("   Service disabled")
        if result.get('install_removed'):
            click.echo(f"   Installation removed: {result['install_path']}")
        if result.get('models_removed'):
            click.echo("   Models removed")
        if result.get('data_removed'):
            click.echo("   All data removed")
            
        if result.get('warnings'):
            click.echo("\n⚠️  Warnings:")
            for warning in result['warnings']:
                click.echo(f"   - {warning}")
    else:
        click.echo(f"❌ Uninstall failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


# Import the unified model command
from voice_mode.whisper_model_unified import whisper_model_unified

# Add it directly to the whisper group
whisper.add_command(whisper_model_unified, name="model")

# Backward compatibility: Add hidden aliases for old direct commands
# These allow "whisper start" to work as "whisper service start"
# But show deprecation warnings pointing to the new unified service commands
@whisper.command("status", hidden=True)
@click.pass_context
def whisper_status_alias(ctx):
    """(Deprecated) Show Whisper service status. Use 'voicemode service status whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service status whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_status)

@whisper.command("start", hidden=True)
@click.pass_context
def whisper_start_alias(ctx):
    """(Deprecated) Start Whisper service. Use 'voicemode service start whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service start whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_start)

@whisper.command("stop", hidden=True)
@click.pass_context
def whisper_stop_alias(ctx):
    """(Deprecated) Stop Whisper service. Use 'voicemode service stop whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service stop whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_stop)

@whisper.command("restart", hidden=True)
@click.pass_context
def whisper_restart_alias(ctx):
    """(Deprecated) Restart Whisper service. Use 'voicemode service restart whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service restart whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_restart)

@whisper.command("enable", hidden=True)
@click.pass_context
def whisper_enable_alias(ctx):
    """(Deprecated) Enable Whisper service. Use 'voicemode service enable whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service enable whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_enable)

@whisper.command("disable", hidden=True)
@click.pass_context
def whisper_disable_alias(ctx):
    """(Deprecated) Disable Whisper service. Use 'voicemode service disable whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service disable whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_disable)

@whisper.command("logs", hidden=True)
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
@click.pass_context
def whisper_logs_alias(ctx, lines):
    """(Deprecated) View Whisper logs. Use 'voicemode service logs whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service logs whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_logs, lines=lines)

@whisper.command("health", hidden=True)
@click.pass_context
def whisper_health_alias(ctx):
    """(Deprecated) Check Whisper health. Use 'voicemode service health whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service health whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_health)

@whisper.command("install", hidden=True)
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install whisper.cpp')
@click.option('--model', default=DEFAULT_WHISPER_MODEL, help=f'Whisper model to download (default: {DEFAULT_WHISPER_MODEL})')
@click.option('--use-gpu/--no-gpu', default=None, help='Enable GPU support if available')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
@click.pass_context
def whisper_install_alias(ctx, install_dir, model, use_gpu, force, version, auto_enable, skip_deps):
    """(Deprecated) Install Whisper. Use 'voicemode service install whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service install whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_install, install_dir=install_dir, model=model, use_gpu=use_gpu,
                force=force, version=version, auto_enable=auto_enable, skip_deps=skip_deps)

@whisper.command("uninstall", hidden=True)
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Whisper models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Whisper data including logs and transcriptions')
@click.confirmation_option(prompt='Are you sure you want to uninstall Whisper?')
@click.pass_context
def whisper_uninstall_alias(ctx, remove_models, remove_all_data):
    """(Deprecated) Uninstall Whisper. Use 'voicemode service uninstall whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service uninstall whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_uninstall, remove_models=remove_models, remove_all_data=remove_all_data)


# Old subcommand structure removed - replaced by unified model command
# The old @whisper_model group and all its subcommands have been replaced
# by the unified whisper_model_unified command above

# Note: The old model group commands (list, active, install, remove, benchmark)
# have been removed in favor of the unified model command that works as:
#   voicemode whisper model           # show current
#   voicemode whisper model --all     # list all
#   voicemode whisper model <name>    # set/install model

# Skip the old definitions to prevent errors
'''
def whisper_model_list():
    """List available Whisper models and their installation status.

    Shows all available models with:
    - Installation status (installed/available)
    - Core ML acceleration status on Apple Silicon
    - File sizes
    - Language support
    - Performance characteristics
    """
    from voice_mode.tools.whisper.models import (
        WHISPER_MODEL_REGISTRY,
        get_model_directory,
        get_active_model,
        is_whisper_model_installed,
        get_installed_whisper_models,
        format_size,
        has_whisper_coreml_model
    )

    model_dir = get_model_directory()
    current_model = get_active_model()
    installed_models = get_installed_whisper_models()

    # Calculate totals
    total_installed_size = sum(
        (model_dir / f"ggml-{name}.bin").stat().st_size
        for name in installed_models
        if (model_dir / f"ggml-{name}.bin").exists()
    )

    total_available_size = sum(
        info["size_mb"] * 1024 * 1024
        for info in WHISPER_MODEL_REGISTRY.values()
    )

    click.echo("\nWhisper Models:\n")

    # Display each model
    for model_name, model_info in WHISPER_MODEL_REGISTRY.items():
        # Check installation status
        is_installed = is_whisper_model_installed(model_name)
        has_coreml = has_whisper_coreml_model(model_name)

        # Status indicator
        if is_installed and has_coreml:
            status = "[✓ Installed+ML]"
        elif is_installed:
            status = "[✓ Installed]"
        else:
            status = "[ Download ]"

        # Active model indicator
        prefix = "→ " if model_name == current_model else "  "

        # Format size
        size_mb = model_info["size_mb"]
        if size_mb >= 1000:
            size_str = f"{size_mb / 1000:.1f} GB"
        else:
            size_str = f"{size_mb} MB"

        # Format description
        desc = model_info["description"]
        if model_name == current_model:
            desc += " (active)"

        # Print model line
        click.echo(
            f"{prefix}{model_name:15} {status:16} {size_str:7} "
            f"{model_info['languages']:20} {desc}"
        )

    # Show summary
    click.echo(f"\nModels directory: {model_dir}")
    if total_installed_size > 0:
        click.echo(
            f"Total size: {format_size(total_installed_size)} installed / "
            f"{format_size(total_available_size)} available"
        )

    click.echo("\nTo download a model: voicemode whisper model install <model-name>")
    click.echo("To set default model: voicemode whisper model active <model-name>")


@whisper_model.command("active")
@click.help_option('-h', '--help')
@click.argument('model_name', required=False)
def whisper_model_active(model_name):
    """Show or set the active Whisper model.
    
    Without arguments: Shows the current active model
    With MODEL_NAME: Sets the active model (updates VOICEMODE_WHISPER_MODEL)
    """
    from voice_mode.tools.whisper.models import (
        get_active_model,
        WHISPER_MODEL_REGISTRY,
        is_whisper_model_installed,
        set_active_model
    )
    import os
    import subprocess
    
    if model_name:
        # Set model mode
        if model_name not in WHISPER_MODEL_REGISTRY:
            click.echo(f"Error: '{model_name}' is not a valid model.", err=True)
            click.echo("\nAvailable models:", err=True)
            for name in WHISPER_MODEL_REGISTRY.keys():
                click.echo(f"  - {name}", err=True)
            return
        
        # Check if model is installed
        if not is_whisper_model_installed(model_name):
            click.echo(f"Error: Model '{model_name}' is not installed.", err=True)
            click.echo(f"Install it with: voicemode whisper model install {model_name}", err=True)
            raise click.Abort()
        
        # Get previous model
        previous_model = get_active_model()
        
        # Update the configuration file
        set_active_model(model_name)
        
        click.echo(f"✓ Active model set to: {model_name}")
        if previous_model != model_name:
            click.echo(f"  (was: {previous_model})")
        
        # Check if whisper service is running
        try:
            result = subprocess.run(['pgrep', '-f', 'whisper-server'], capture_output=True)
            if result.returncode == 0:
                # Service is running
                click.echo(f"\n⚠️  Please restart the whisper service for changes to take effect:")
                click.echo(f"  {click.style('voicemode whisper restart', fg='yellow', bold=True)}")
            else:
                click.echo(f"\nWhisper service is not running. Start it with:")
                click.echo(f"  voicemode whisper start")
                click.echo(f"(or restart the whisper service if it's managed by systemd/launchd)")
        except:
            click.echo(f"\nPlease restart the whisper service for changes to take effect:")
            click.echo(f"  voicemode whisper restart")
    
    else:
        # Show current model
        current = get_active_model()
        
        # Check if current model is installed
        installed = is_whisper_model_installed(current)
        status = click.style("[✓ Installed]", fg="green") if installed else click.style("[Not installed]", fg="red")
        
        # Get model info
        model_info = WHISPER_MODEL_REGISTRY.get(current, {})
        
        click.echo(f"\nActive Whisper model: {click.style(current, fg='yellow', bold=True)} {status}")
        if model_info:
            click.echo(f"  Size: {model_info.get('size_mb', 'Unknown')} MB")
            click.echo(f"  Languages: {model_info.get('languages', 'Unknown')}")
            click.echo(f"  Description: {model_info.get('description', 'Unknown')}")
        
        # Check what model the service is actually using
        try:
            result = subprocess.run(['pgrep', '-f', 'whisper-server'], capture_output=True)
            if result.returncode == 0:
                # Service is running, could check its actual model here
                click.echo(f"\nWhisper service status: {click.style('Running', fg='green')}")
        except:
            pass
        
        click.echo(f"\nTo change: voicemode whisper model active <model-name>")
        click.echo(f"To list all models: voicemode whisper models")


@whisper.command("models", hidden=True)  # Hidden - use 'whisper model list' instead
def whisper_models():
    """List available Whisper models and their installation status.

    DEPRECATED: Use 'voicemode whisper model list' instead.
    """
    from voice_mode.tools.whisper.models import (
        WHISPER_MODEL_REGISTRY, 
        get_model_directory,
        get_active_model,
        is_whisper_model_installed,
        get_installed_whisper_models,
        format_size,
        has_whisper_coreml_model
    )
    
    model_dir = get_model_directory()
    current_model = get_active_model()
    installed_models = get_installed_whisper_models()
    
    # Calculate totals
    total_installed_size = sum(
        WHISPER_MODEL_REGISTRY[m]["size_mb"] for m in installed_models
    )
    total_available_size = sum(
        m["size_mb"] for m in WHISPER_MODEL_REGISTRY.values()
    )
    
    # Print header
    click.echo("\nWhisper Models:")
    click.echo("")
    
    # Print models table
    for model_name, info in WHISPER_MODEL_REGISTRY.items():
        # Check status
        is_installed = is_whisper_model_installed(model_name)
        is_current = model_name == current_model
        
        # Format status
        if is_current:
            status = click.style("→", fg="yellow", bold=True)
            model_display = click.style(f"{model_name:15}", fg="yellow", bold=True)
        else:
            status = " "
            model_display = f"{model_name:15}"
        
        # Format installation status
        if is_installed:
            # Check for Core ML model
            if has_whisper_coreml_model(model_name):
                install_status = click.style("[✓ Installed+ML]", fg="green")
            else:
                install_status = click.style("[✓ Installed]", fg="green")
        else:
            install_status = click.style("[ Download ]", fg="bright_black")
        
        # Format size
        size_str = format_size(info["size_mb"]).rjust(8)
        
        # Format languages
        lang_str = f"{info['languages']:20}"
        
        # Format description
        desc = info['description']
        if is_current:
            desc += " (Currently selected)"
            desc = click.style(desc, fg="yellow")
        
        # Print row
        click.echo(f"{status} {model_display} {install_status:18} {size_str}  {lang_str} {desc}")
    
    # Print footer
    click.echo("")
    click.echo(f"Models directory: {model_dir}")
    click.echo(f"Total size: {format_size(total_installed_size)} installed / {format_size(total_available_size)} available")
    click.echo("")
    click.echo("To download a model: voicemode whisper model install <model-name>")
    click.echo("To set default model: voicemode whisper model <model-name>")


@whisper_model.command("install")
@click.help_option('-h', '--help')
@click.argument('model', default=DEFAULT_WHISPER_MODEL)
@click.option('--force', '-f', is_flag=True, help='Re-download even if model exists')
@click.option('--skip-core-ml', is_flag=True, help='Skip Core ML conversion on Apple Silicon')
def whisper_model_install(model, force, skip_core_ml):
    """Install Whisper model(s) with automatic Core ML support on Apple Silicon.

    MODEL can be a model name (e.g., 'base'), 'all' to download all models,
    or omitted to use the default (base).
    
    Available models: tiny, tiny.en, base, base.en, small, small.en,
    medium, medium.en, large-v1, large-v2, large-v3, large-v3-turbo
    """
    import json
    import voice_mode.tools.whisper.model_install as install_module
    # Get the actual function from the MCP tool wrapper
    tool = install_module.whisper_model_install
    install_func = tool.fn if hasattr(tool, 'fn') else tool
    
    # Call the install function
    result = asyncio.run(install_func(
        model=model,
        force_download=force,
        skip_core_ml=skip_core_ml
    ))
    
    try:
        # Parse JSON response
        data = json.loads(result)
        
        # Core ML is now automatic with pre-built models - no prompts needed!
        if data.get('success'):
            click.echo("✅ Model download completed!")
            
            if 'results' in data:
                for model_result in data['results']:
                    click.echo(f"\n📦 {model_result['model']}:")
                    if model_result.get('already_exists') and not force:
                        click.echo("   Already downloaded")
                    else:
                        click.echo("   Downloaded successfully")
                    
                    if model_result.get('core_ml_converted'):
                        click.echo("   Core ML: Converted")
                    elif model_result.get('core_ml_exists'):
                        click.echo("   Core ML: Already exists")
            
            if 'models_dir' in data:
                click.echo(f"\nModels location: {data['models_dir']}")
        else:
            click.echo(f"❌ Download failed: {data.get('error', 'Unknown error')}")
            if 'available_models' in data:
                click.echo("\nAvailable models:")
                for m in data['available_models']:
                    click.echo(f"   - {m}")
    except json.JSONDecodeError:
        click.echo(result)


@whisper_model.command("remove")
@click.help_option('-h', '--help')
@click.argument('model')
@click.option('--force', '-f', is_flag=True, help='Remove without confirmation')
def whisper_model_remove(model, force):
    """Remove an installed Whisper model.
    
    MODEL is the name of the model to remove (e.g., 'large-v2').
    """
    from voice_mode.tools.whisper.models import (
        WHISPER_MODEL_REGISTRY,
        is_whisper_model_installed,
        get_model_directory,
        get_active_model
    )
    import os
    
    # Validate model name
    if model not in WHISPER_MODEL_REGISTRY:
        click.echo(f"Error: '{model}' is not a valid model.", err=True)
        click.echo("\nAvailable models:", err=True)
        for name in WHISPER_MODEL_REGISTRY.keys():
            click.echo(f"  - {name}", err=True)
        ctx.exit(1)
    
    # Check if model is installed
    if not is_whisper_model_installed(model):
        click.echo(f"Model '{model}' is not installed.")
        return
    
    # Check if it's the current model
    current = get_active_model()
    if model == current:
        click.echo(f"Warning: '{model}' is the currently selected model.", err=True)
        if not force:
            if not click.confirm("Do you still want to remove it?"):
                return
    
    # Get model path
    model_dir = get_model_directory()
    model_info = WHISPER_MODEL_REGISTRY[model]
    model_path = model_dir / model_info["filename"]
    
    # Also check for Core ML models
    coreml_path = model_dir / f"ggml-{model}-encoder.mlmodelc"
    
    # Confirm removal if not forced
    if not force:
        size_mb = model_info["size_mb"]
        if not click.confirm(f"Remove {model} ({size_mb} MB)?"):
            return
    
    # Remove the model file
    try:
        if model_path.exists():
            os.remove(model_path)
            click.echo(f"✓ Removed model: {model}")
        
        # Remove Core ML model if exists
        if coreml_path.exists():
            import shutil
            shutil.rmtree(coreml_path)
            click.echo(f"✓ Removed Core ML model: {model}")
        
        click.echo(f"\nModel '{model}' has been removed.")
    except Exception as e:
        click.echo(f"Error removing model: {e}", err=True)


@whisper_model.command("benchmark")
@click.help_option('-h', '--help')
@click.option('--models', default='installed', help='Models to benchmark: installed, all, or comma-separated list')
@click.option('--sample', help='Audio file to use for benchmarking')
@click.option('--runs', default=1, help='Number of benchmark runs per model')
def whisper_model_benchmark_cmd(models, sample, runs):
    """Benchmark Whisper model performance.
    
    Runs performance tests on specified models to help choose the optimal model
    for your use case based on speed vs accuracy trade-offs.
    """
    from voice_mode.tools.whisper.model_benchmark import whisper_model_benchmark
    
    # Parse models parameter
    if ',' in models:
        model_list = [m.strip() for m in models.split(',')]
    else:
        model_list = models
    
    # Run benchmark
    result = asyncio.run(whisper_model_benchmark(
        models=model_list,
        sample_file=sample,
        runs=runs
    ))
    
    if not result.get('success'):
        click.echo(f"❌ Benchmark failed: {result.get('error', 'Unknown error')}", err=True)
        return
    
    # Display results
    click.echo("\n" + "="*60)
    click.echo("Whisper Model Benchmark Results")
    click.echo("="*60)
    
    if result.get('sample_file'):
        click.echo(f"Sample: {result['sample_file']}")
    if result.get('runs_per_model') > 1:
        click.echo(f"Runs per model: {result['runs_per_model']} (showing best)")
    click.echo("")
    
    # Display benchmark table
    click.echo(f"{'Model':<20} {'Load (ms)':<12} {'Encode (ms)':<12} {'Total (ms)':<12} {'Speed':<10}")
    click.echo("-"*70)
    
    for bench in result.get('benchmarks', []):
        if bench.get('success'):
            model = bench['model']
            load_time = f"{bench.get('load_time_ms', 0):.1f}"
            encode_time = f"{bench.get('encode_time_ms', 0):.1f}"
            total_time = f"{bench.get('total_time_ms', 0):.1f}"
            rtf = f"{bench.get('real_time_factor', 0):.1f}x"
            
            # Highlight fastest model
            if bench['model'] == result.get('fastest_model'):
                model = click.style(model, fg='green', bold=True)
                rtf = click.style(rtf, fg='green', bold=True)
            
            click.echo(f"{model:<20} {load_time:<12} {encode_time:<12} {total_time:<12} {rtf:<10}")
        else:
            click.echo(f"{bench['model']:<20} {'Failed':<12} {bench.get('error', 'Unknown error')}")
    
    # Display recommendations
    if result.get('recommendations'):
        click.echo("\nRecommendations:")
        for rec in result['recommendations']:
            click.echo(f"  • {rec}")
    
    # Summary
    if result.get('fastest_model'):
        click.echo(f"\nFastest model: {click.style(result['fastest_model'], fg='yellow', bold=True)}")
        click.echo(f"Processing time: {result.get('fastest_time_ms', 'N/A')} ms")
    
    click.echo("\nNote: Speed values show real-time factor (higher is better)")
    click.echo("      1.0x = real-time, 10x = 10 times faster than real-time")
''' # End of old model subcommands


@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def config():
    """Manage voicemode configuration."""
    pass


@config.command("list")
def config_list():
    """List all configuration keys with their descriptions."""
    from voice_mode.tools.configuration_management import list_config_keys
    result = asyncio.run(list_config_keys.fn())
    click.echo(result)


@config.command("get")
@click.help_option('-h', '--help')
@click.argument('key')
def config_get(key):
    """Get a configuration value."""
    import os
    from pathlib import Path
    
    # Read from the env file
    env_file = Path.home() / ".voicemode" / "voicemode.env"
    if not env_file.exists():
        click.echo(f"❌ Configuration file not found: {env_file}")
        return
    
    # Look for the key
    found = False
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                if k.strip() == key:
                    click.echo(f"{key}={v.strip()}")
                    found = True
                    break
    
    if not found:
        # Check environment variable
        env_value = os.getenv(key)
        if env_value is not None:
            click.echo(f"{key}={env_value} (from environment)")
        else:
            click.echo(f"❌ Configuration key not found: {key}")
            click.echo("Run 'voicemode config list' to see available keys")


@config.command("set")
@click.help_option('-h', '--help')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """Set a configuration value."""
    from voice_mode.tools.configuration_management import update_config
    result = asyncio.run(update_config.fn(key, value))
    click.echo(result)


@config.command("edit")
@click.help_option('-h', '--help')
@click.option('--editor', help='Editor to use (overrides $EDITOR)')
def config_edit(editor):
    """Open the configuration file in your default editor.

    Opens ~/.voicemode/voicemode.env in your configured editor.
    Uses $EDITOR environment variable by default, or you can specify with --editor.

    Examples:
        voicemode config edit           # Use $EDITOR
        voicemode config edit --editor vim
        voicemode config edit --editor "code --wait"
    """
    from pathlib import Path

    # Find the config file
    config_path = Path.home() / ".voicemode" / "voicemode.env"

    # Create default config if it doesn't exist
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        from voice_mode.config import load_voicemode_env
        # This will create the default config
        load_voicemode_env()

    # Determine which editor to use
    if editor:
        editor_cmd = editor
    else:
        # Try environment variables in order of preference
        editor_cmd = (
            os.environ.get('EDITOR') or
            os.environ.get('VISUAL') or
            shutil.which('nano') or
            shutil.which('vim') or
            shutil.which('vi')
        )

    if not editor_cmd:
        click.echo("❌ No editor found. Please set $EDITOR or use --editor")
        click.echo("   Example: export EDITOR=vim")
        click.echo("   Or use: voicemode config edit --editor vim")
        return

    # Handle complex editor commands (e.g., "code --wait")
    if ' ' in editor_cmd:
        import shlex
        cmd_parts = shlex.split(editor_cmd)
        cmd = cmd_parts + [str(config_path)]
    else:
        cmd = [editor_cmd, str(config_path)]

    # Open the editor
    try:
        click.echo(f"Opening {config_path} in {editor_cmd}...")
        subprocess.run(cmd, check=True)
        click.echo("✅ Configuration file edited successfully")
        click.echo("\nChanges will take effect when voicemode is restarted.")
    except subprocess.CalledProcessError:
        click.echo(f"❌ Editor exited with an error")
    except FileNotFoundError:
        click.echo(f"❌ Editor not found: {editor_cmd}")
        click.echo("   Please check that the editor is installed and in your PATH")


# Dependency management group
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--component', type=click.Choice(['core', 'whisper', 'kokoro']),
              help='Check specific component only')
@click.option('--yes', '-y', is_flag=True, help='Install without prompting')
@click.option('--dry-run', is_flag=True, help='Show what would be installed')
@click.option('--verbose', '-v', is_flag=True, help='Show full installation output')
def deps(component, yes, dry_run, verbose):
    """Check and install system dependencies.

    Shows dependency status and offers to install missing ones.
    Checks core dependencies by default, or specify --component.

    Examples:
        voicemode deps                    # Check all dependencies
        voicemode deps --component whisper  # Check whisper dependencies only
        voicemode deps --yes              # Install without prompting
        voicemode deps --verbose          # Show full installation output
    """
    from voice_mode.utils.dependencies.checker import (
        check_component_dependencies,
        load_dependencies,
        install_missing_dependencies
    )

    deps_yaml = load_dependencies()
    components = [component] if component else ['core', 'whisper', 'kokoro']

    all_missing = []

    for comp in components:
        click.echo(f"\n{comp.capitalize()} Dependencies:")
        results = check_component_dependencies(comp, deps_yaml)

        if not results:
            click.echo("  (No required dependencies for this platform)")
            continue

        for pkg, installed in results.items():
            status = "✓" if installed else "✗"
            click.echo(f"  {status} {pkg}")

            if not installed:
                all_missing.append(pkg)

    if not all_missing:
        click.echo("\n✅ All dependencies satisfied")
        return

    if dry_run:
        click.echo(f"\nWould install: {', '.join(all_missing)}")
        return

    # Offer to install
    success, message = install_missing_dependencies(
        all_missing,
        interactive=not yes,
        verbose=verbose
    )

    if success:
        click.echo("\n✅ Dependencies installed successfully")
    else:
        click.echo(f"\n❌ Installation failed: {message}")


# Diagnostics group
@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def diag():
    """Diagnostic tools for voicemode."""
    pass


@diag.command()
def info():
    """Show voicemode installation information."""
    from voice_mode.tools.diagnostics import voice_mode_info
    result = asyncio.run(voice_mode_info.fn())
    click.echo(result)


@diag.command()
def devices():
    """List available audio input and output devices."""
    from voice_mode.tools.devices import check_audio_devices
    result = asyncio.run(check_audio_devices.fn())
    click.echo(result)


@diag.command()
def registry():
    """Show voice provider registry with all discovered endpoints."""
    from voice_mode.tools.voice_registry import voice_registry
    result = asyncio.run(voice_registry.fn())
    click.echo(result)


@diag.command()
def dependencies():
    """Check system audio dependencies and provide installation guidance."""
    import json
    from voice_mode.tools.dependencies import check_audio_dependencies
    result = asyncio.run(check_audio_dependencies.fn())
    
    if isinstance(result, dict):
        # Format the dictionary output nicely
        click.echo("System Audio Dependencies Check")
        click.echo("=" * 50)
        
        click.echo(f"\nPlatform: {result.get('platform', 'Unknown')}")
        
        if 'packages' in result:
            click.echo("\nSystem Packages:")
            for pkg, status in result['packages'].items():
                symbol = "✅" if status else "❌"
                click.echo(f"  {symbol} {pkg}")
        
        if 'missing_packages' in result and result['missing_packages']:
            click.echo("\n❌ Missing Packages:")
            for pkg in result['missing_packages']:
                click.echo(f"  - {pkg}")
            if 'install_command' in result:
                click.echo(f"\nInstall with: {result['install_command']}")
        
        if 'pulseaudio' in result:
            pa = result['pulseaudio']
            click.echo(f"\nPulseAudio Status: {'✅ Running' if pa.get('running') else '❌ Not running'}")
            if pa.get('version'):
                click.echo(f"  Version: {pa['version']}")
        
        if 'diagnostics' in result and result['diagnostics']:
            click.echo("\nDiagnostics:")
            for diag in result['diagnostics']:
                click.echo(f"  - {diag}")
        
        if 'recommendations' in result and result['recommendations']:
            click.echo("\nRecommendations:")
            for rec in result['recommendations']:
                click.echo(f"  - {rec}")
    else:
        # Fallback for string output
        click.echo(str(result))


# Legacy CLI for voicemode-cli command
@click.group()
@click.version_option()
@click.help_option('-h', '--help')
def cli():
    """Voice Mode CLI - Manage conversations, view logs, and analyze voice interactions."""
    pass


# Import subcommand groups
from voice_mode.cli_commands import exchanges as exchanges_cmd
from voice_mode.cli_commands import transcribe as transcribe_cmd
from voice_mode.cli_commands import history as history_cmd
from voice_mode.cli_commands import status as status_cmd

# Add subcommands to legacy CLI
cli.add_command(exchanges_cmd.exchanges)
cli.add_command(transcribe_cmd.transcribe)

# Add exchanges to main CLI
voice_mode_main_cli.add_command(exchanges_cmd.exchanges)
voice_mode_main_cli.add_command(history_cmd.history)

# Add unified status command
voice_mode_main_cli.add_command(status_cmd.status)

# Note: We'll add these commands after the groups are defined
# audio group will get transcribe and play commands


# Now add the subcommands to their respective groups
# Add transcribe as top-level command
transcribe_audio_cmd = transcribe_cmd.transcribe.commands['audio']
transcribe_audio_cmd.name = 'transcribe'
voice_mode_main_cli.add_command(transcribe_audio_cmd)

# Converse command - direct voice conversation from CLI
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--message', '-m', default="Hello! How can I help you today?", help='Initial message to speak')
@click.option('--wait/--no-wait', default=True, help='Wait for response after speaking')
@click.option('--duration', '-d', type=float, default=DEFAULT_LISTEN_DURATION, help='Listen duration in seconds')
@click.option('--min-duration', type=float, default=MIN_RECORDING_DURATION, help='Minimum listen duration before silence detection')
@click.option('--voice', help='TTS voice to use (e.g., nova, shimmer, af_sky)')
@click.option('--tts-provider', type=click.Choice(['openai', 'kokoro']), help='TTS provider')
@click.option('--tts-model', help='TTS model (e.g., tts-1, tts-1-hd)')
@click.option('--tts-instructions', help='Tone/style instructions for gpt-4o-mini-tts')
@click.option('--audio-feedback/--no-audio-feedback', default=None, help='Enable/disable audio feedback')
@click.option('--audio-format', help='Audio format (pcm, mp3, wav, flac, aac, opus)')
@click.option('--disable-silence-detection', is_flag=True, help='Disable silence detection')
@click.option('--speed', type=float, help='Speech rate (0.25 to 4.0)')
@click.option('--vad-aggressiveness', type=int, help='VAD aggressiveness (0-3)')
@click.option('--skip-tts/--no-skip-tts', default=None, help='Skip TTS and only show text')
@click.option('--continuous', '-c', is_flag=True, help='Continuous conversation mode')
def converse(message, wait, duration, min_duration, voice, tts_provider,
            tts_model, tts_instructions, audio_feedback, audio_format, disable_silence_detection,
            speed, vad_aggressiveness, skip_tts, continuous):
    """Have a voice conversation directly from the command line.

    Examples:

        # Simple conversation
        voicemode converse

        # Speak a message without waiting
        voicemode converse -m "Hello there!" --no-wait

        # Continuous conversation mode
        voicemode converse --continuous

        # Use specific voice
        voicemode converse --voice nova
    """
    # Check core dependencies before running
    from voice_mode.utils.dependencies.checker import check_component_dependencies

    results = check_component_dependencies('core')
    missing = [pkg for pkg, installed in results.items() if not installed]

    if missing:
        click.echo(f"⚠️  Missing core dependencies: {', '.join(missing)}")
        click.echo("   Run 'voicemode deps' to install them")
        return

    from voice_mode.tools.converse import converse as converse_fn
    
    async def run_conversation():
        """Run the conversation asynchronously."""
        # Suppress the spurious aiohttp warning that appears on startup
        # This warning is a false positive from asyncio detecting an unclosed
        # session that was likely created during module import
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)

        # Enable INFO logging for converse command to show progress
        logging.getLogger('voicemode').setLevel(logging.INFO)

        try:
            if continuous:
                # Continuous conversation mode
                click.echo("🎤 Starting continuous conversation mode...")
                click.echo("   Press Ctrl+C to exit\n")
                
                # First message
                result = await converse_fn.fn(
                    message=message,
                    wait_for_response=True,
                    listen_duration_max=duration,
                    listen_duration_min=min_duration,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    chime_enabled=audio_feedback,
                    audio_format=audio_format,
                    disable_silence_detection=disable_silence_detection,
                    speed=speed,
                    vad_aggressiveness=vad_aggressiveness,
                    skip_tts=skip_tts
                )
                
                if result and "Voice response:" in result:
                    click.echo(f"You: {result.split('Voice response:')[1].split('|')[0].strip()}")
                
                # Continue conversation
                while True:
                    # Wait for user's next input
                    result = await converse_fn.fn(
                        message="",  # Empty message for listening only
                        wait_for_response=True,
                        listen_duration_max=duration,
                        listen_duration_min=min_duration,
                        voice=voice,
                        tts_provider=tts_provider,
                        tts_model=tts_model,
                        tts_instructions=tts_instructions,
                        chime_enabled=audio_feedback,
                        audio_format=audio_format,
                        disable_silence_detection=disable_silence_detection,
                        speed=speed,
                        vad_aggressiveness=vad_aggressiveness,
                        skip_tts=skip_tts
                    )
                    
                    if result and "Voice response:" in result:
                        user_text = result.split('Voice response:')[1].split('|')[0].strip()
                        click.echo(f"You: {user_text}")
                        
                        # Check for exit commands
                        if user_text.lower() in ['exit', 'quit', 'goodbye', 'bye']:
                            await converse_fn.fn(
                                message="Goodbye!",
                                wait_for_response=False,
                                voice=voice,
                                tts_provider=tts_provider,
                                tts_model=tts_model,
                                audio_format=audio_format,
                                speed=speed,
                                skip_tts=skip_tts
                            )
                            break
            else:
                # Single conversation
                result = await converse_fn.fn(
                    message=message,
                    wait_for_response=wait,
                    listen_duration_max=duration,
                    listen_duration_min=min_duration,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    chime_enabled=audio_feedback,
                    audio_format=audio_format,
                    disable_silence_detection=disable_silence_detection,
                    speed=speed,
                    vad_aggressiveness=vad_aggressiveness,
                    skip_tts=skip_tts
                )
                
                # Display result
                if result:
                    if "Voice response:" in result:
                        # Extract the response text and timing info
                        parts = result.split('|')
                        response_text = result.split('Voice response:')[1].split('|')[0].strip()
                        timing_info = parts[1].strip() if len(parts) > 1 else ""
                        
                        click.echo(f"\n📢 Spoke: {message}")
                        if wait:
                            click.echo(f"🎤 Heard: {response_text}")
                        if timing_info:
                            click.echo(f"⏱️  {timing_info}")
                    else:
                        click.echo(result)
                        
        except KeyboardInterrupt:
            click.echo("\n\n👋 Conversation ended")
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            import traceback
            if os.environ.get('VOICEMODE_DEBUG'):
                traceback.print_exc()
    
    # Run the async function
    asyncio.run(run_conversation())


# Serve command - HTTP/SSE server for remote access
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--host', default='127.0.0.1', help='Host to bind to (use 0.0.0.0 for all interfaces)')
@click.option('--port', '-p', default=8765, type=int, help='Port to bind to')
@click.option('--transport', '-t', default=SERVE_TRANSPORT,
              type=click.Choice(['streamable-http', 'sse']),
              help='MCP transport protocol (streamable-http is recommended, sse is deprecated)')
@click.option('--log-level', default='info', type=click.Choice(['debug', 'info', 'warning', 'error']),
              help='Logging level')
@click.option('--allow-anthropic/--no-allow-anthropic', default=None,
              help='Allow connections from Anthropic IP ranges (for Claude Cowork)')
@click.option('--allow-tailscale/--no-allow-tailscale', default=None,
              help='Allow connections from Tailscale IP range (100.64.0.0/10)')
@click.option('--allow-ip', multiple=True,
              help='Allow connections from custom CIDR ranges (can be specified multiple times)')
@click.option('--allow-local/--no-allow-local', default=None,
              help='Allow connections from local/private IP ranges (default: enabled)')
@click.option('--secret', default=None,
              help='Require a secret path segment for access (e.g., --secret=my-uuid)')
@click.option('--token', default=None,
              help='Require Bearer token authentication via Authorization header')
def serve(host: str, port: int, transport: str, log_level: str, allow_anthropic: bool | None,
          allow_tailscale: bool | None, allow_ip: tuple, allow_local: bool | None,
          secret: str | None, token: str | None):
    """Start VoiceMode as an HTTP/SSE server for remote access.

    This enables Claude Code, Claude Desktop, Claude Cowork, or other MCP
    clients to connect to VoiceMode over HTTP instead of stdio. Useful for:

    - Multiple Claude Code projects sharing one VoiceMode instance
    - Claude Cowork (runs in a sandboxed VM without audio access)
    - Claude Desktop with mcp-remote
    - Any MCP client that supports HTTP transport

    The server exposes all VoiceMode MCP tools via the HTTP transport.
    Audio capture and playback happens on the host machine.

    Examples:

        # Start server on localhost (default)
        voicemode serve

        # Allow connections from VMs (bind to all interfaces)
        voicemode serve --host 0.0.0.0

        # Custom port
        voicemode serve --port 9000

        # Enable Anthropic IP ranges (for Claude Cowork)
        voicemode serve --host 0.0.0.0 --allow-anthropic

        # Allow all devices on your Tailscale network
        voicemode serve --allow-tailscale

        # Add custom IP allowlist
        voicemode serve --allow-ip 10.0.0.0/8 --allow-ip 192.168.1.100/32

        # Use secret path for authentication
        voicemode serve --secret my-secret-uuid

        # Use Bearer token authentication
        voicemode serve --token my-secret-token

    Connect from Claude Code:

        claude mcp add --transport http voicemode http://localhost:8765/mcp
    """
    import logging
    from .server import mcp
    from .config import setup_logging
    from .serve_middleware import (
        AccessLogMiddleware,
        IPAllowlistMiddleware,
        TokenAuthMiddleware,
        ANTHROPIC_CIDRS,
        TAILSCALE_CIDRS,
        LOCAL_CIDRS,
    )

    # Warn if SSE transport is used (deprecated in favor of streamable-http)
    if transport == "sse":
        click.echo(
            click.style("Warning: ", fg="yellow", bold=True) +
            "SSE transport is deprecated. Use --transport streamable-http for the modern protocol.",
            err=True
        )

    # Set up logging based on level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger = setup_logging()
    logger.setLevel(numeric_level)

    # Apply config defaults when CLI options are not provided
    # CLI flags always override config file values
    if allow_local is None:
        allow_local = SERVE_ALLOW_LOCAL
    if allow_anthropic is None:
        allow_anthropic = SERVE_ALLOW_ANTHROPIC
    if allow_tailscale is None:
        allow_tailscale = SERVE_ALLOW_TAILSCALE
    if not allow_ip and SERVE_ALLOWED_IPS:
        # Parse comma-separated CIDRs from config
        allow_ip = tuple(cidr.strip() for cidr in SERVE_ALLOWED_IPS.split(',') if cidr.strip())
    if secret is None and SERVE_SECRET:
        secret = SERVE_SECRET
    if token is None and SERVE_TOKEN:
        token = SERVE_TOKEN

    # Build allowed CIDR list
    allowed_cidrs: list[str] = []
    if allow_local:
        allowed_cidrs.extend(LOCAL_CIDRS)
    if allow_anthropic:
        allowed_cidrs.extend(ANTHROPIC_CIDRS)
    if allow_tailscale:
        allowed_cidrs.extend(TAILSCALE_CIDRS)
    if allow_ip:
        allowed_cidrs.extend(allow_ip)

    # Determine if any security is enabled
    has_ip_allowlist = bool(allowed_cidrs) and (allow_anthropic or allow_tailscale or allow_ip or not allow_local)
    has_secret = bool(secret)  # secret is set and non-empty
    has_token = bool(token)  # token is set and non-empty
    has_security = has_ip_allowlist or has_secret or has_token

    # Determine base path based on transport
    if transport == "streamable-http":
        base_path = "/mcp"
    else:  # sse
        base_path = "/sse"

    # Build the endpoint path with optional secret segment
    endpoint_path = f"{base_path}/{secret}" if has_secret else base_path
    endpoint_url = f"http://{host}:{port}{endpoint_path}"

    # Helper to mask secrets
    def mask_secret(s: str, show_chars: int = 4) -> str:
        if len(s) <= show_chars:
            return s[:1] + "..."
        return s[:show_chars] + "..."

    # Log startup info
    click.echo(f"Starting VoiceMode MCP server on {host}:{port}")
    click.echo(f"Transport: {transport}")
    click.echo()

    # Print security configuration if any is enabled
    if has_security:
        click.echo("Security configuration:")

        # IP allowlist info
        if allowed_cidrs:
            ip_parts = []
            if allow_local:
                ip_parts.append("local")
            if allow_anthropic:
                ip_parts.append(f"Anthropic ({ANTHROPIC_CIDRS[0]})")
            if allow_tailscale:
                ip_parts.append(f"Tailscale ({TAILSCALE_CIDRS[0]})")
            if allow_ip:
                ip_parts.append(f"custom ({len(allow_ip)} CIDRs)")
            click.echo(f"  IP allowlist: {' + '.join(ip_parts)}")
        else:
            click.echo("  IP allowlist: disabled (--no-allow-local)")

        # Secret path info
        if has_secret:
            click.echo(f"  URL secret: {mask_secret(secret)}")

        # Token auth info
        if has_token:
            click.echo(f"  Bearer token: {mask_secret(token)}")

        click.echo()

    click.echo(f"Endpoint: {endpoint_url}")
    click.echo(f"Log level: {log_level}")
    click.echo()

    # Show Claude Code connection options
    click.echo(click.style("Connect from Claude Code:", bold=True))
    click.echo()
    click.echo(f"  claude mcp add --transport http voicemode {endpoint_url}")
    click.echo()

    # Show JSON config for manual setup
    click.echo(click.style("Manual configuration:", bold=True))
    click.echo()
    click.echo('  {')
    click.echo('    "mcpServers": {')
    click.echo('      "voicemode": {')
    click.echo('        "type": "http",')
    click.echo(f'        "url": "{endpoint_url}"')
    click.echo('      }')
    click.echo('    }')
    click.echo('  }')
    click.echo()

    click.echo(click.style("Legacy (mcp-remote):", bold=True))
    click.echo(f"  npx mcp-remote {endpoint_url}")
    click.echo()
    click.echo("Press Ctrl+C to stop the server")
    click.echo()

    # Create the app with the selected transport (fastmcp 2.14+ API)
    app = mcp.http_app(transport=transport, path=endpoint_path)

    # Note: Middleware is applied in reverse order (last added = first executed)
    # Add token auth middleware (checked after IP allowlist)
    if has_token:
        app.add_middleware(TokenAuthMiddleware, token=token)

    # Add IP allowlist middleware (checked first)
    if allowed_cidrs:
        app.add_middleware(IPAllowlistMiddleware, allowed_cidrs=allowed_cidrs)

    # Add access logging middleware (runs first, logs all requests)
    app.add_middleware(AccessLogMiddleware)

    try:
        # Run the app with uvicorn directly to use our middleware
        import uvicorn

        # Disable uvicorn's access logging - we use our own AccessLogMiddleware
        # which shows X-Forwarded-For headers
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=False,  # Disable uvicorn access log, use our middleware instead
        )
    except KeyboardInterrupt:
        click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Error starting server: {e}", err=True)
        raise click.Abort()


# Version command
@voice_mode_main_cli.command()
def version():
    """Show VoiceMode version and check for updates."""
    import requests

    # Use the same version that --version shows
    click.echo(f"VoiceMode version: {__version__}")

    # Check for updates if not in development mode
    if not ("dev" in __version__ or "dirty" in __version__):
        try:
            response = requests.get(
                "https://pypi.org/pypi/voice-mode/json",
                timeout=2
            )
            if response.status_code == 200:
                latest_version = response.json()["info"]["version"]
                
                # Simple version comparison (works for semantic versioning)
                if latest_version != __version__:
                    click.echo(f"Latest version: {latest_version} available")
                    click.echo("Run 'voicemode update' to update")
                else:
                    click.echo("You are running the latest version")
        except (requests.RequestException, KeyError, ValueError):
            # Fail silently if we can't check for updates
            pass


# Update command
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--force', is_flag=True, help='Force reinstall even if already up to date')
def update(force):
    """Update Voice Mode to the latest version.
    
    Automatically detects installation method (UV tool, UV pip, or regular pip)
    and uses the appropriate update command.
    """
    import subprocess
    import requests
    from pathlib import Path
    from importlib.metadata import version as get_version, PackageNotFoundError
    
    def detect_uv_tool_installation():
        """Detect if running from a UV tool installation."""
        prefix_path = Path(sys.prefix).resolve()
        uv_tools_base = Path.home() / ".local" / "share" / "uv" / "tools"
        
        # Check if sys.prefix is within UV tools directory
        if uv_tools_base in prefix_path.parents or prefix_path.parent == uv_tools_base:
            # Find the tool directory
            tool_dir = prefix_path if prefix_path.parent == uv_tools_base else None
            
            if not tool_dir:
                for parent in prefix_path.parents:
                    if parent.parent == uv_tools_base:
                        tool_dir = parent
                        break
            
            if tool_dir:
                # Verify with uv-receipt.toml
                receipt_file = tool_dir / "uv-receipt.toml"
                if receipt_file.exists():
                    # Parse tool name from receipt or use directory name
                    try:
                        with open(receipt_file) as f:
                            content = f.read()
                            import re
                            match = re.search(r'name = "([^"]+)"', content)
                            tool_name = match.group(1) if match else tool_dir.name
                            return True, tool_name
                    except Exception:
                        return True, tool_dir.name
        
        return False, None
    
    def detect_uv_venv():
        """Detect if running in a UV-managed virtual environment."""
        # Check if we're in a venv
        if sys.prefix == sys.base_prefix:
            return False
        
        # Check for UV markers in pyvenv.cfg
        pyvenv_cfg = Path(sys.prefix) / "pyvenv.cfg"
        if pyvenv_cfg.exists():
            try:
                with open(pyvenv_cfg) as f:
                    content = f.read()
                    if "uv" in content.lower() or "managed by uv" in content:
                        return True
            except Exception:
                pass
        
        return False
    
    def check_uv_available():
        """Check if UV is available."""
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    # Get current version
    try:
        current_version = get_version("voice-mode")
    except PackageNotFoundError:
        current_version = "development"
    
    # Check if update needed (unless forced)
    if not force and current_version != "development":
        try:
            response = requests.get(
                "https://pypi.org/pypi/voice-mode/json",
                timeout=2
            )
            if response.status_code == 200:
                latest_version = response.json()["info"]["version"]
                if latest_version == current_version:
                    click.echo(f"Already running the latest version ({current_version})")
                    return
        except (requests.RequestException, KeyError, ValueError):
            pass  # Continue with update if we can't check
    
    # Detect installation method
    is_uv_tool, tool_name = detect_uv_tool_installation()
    
    if is_uv_tool:
        # UV tool installation - use uv tool upgrade
        click.echo(f"Updating Voice Mode (UV tool: {tool_name})...")
        
        result = subprocess.run(
            ["uv", "tool", "upgrade", tool_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            try:
                new_version = get_version("voice-mode")
                click.echo(f"✅ Successfully updated to version {new_version}")
            except PackageNotFoundError:
                click.echo("✅ Successfully updated Voice Mode")
        else:
            click.echo(f"❌ Update failed: {result.stderr}")
            click.echo(f"Try running manually: uv tool upgrade {tool_name}")
    
    elif detect_uv_venv():
        # UV-managed virtual environment
        click.echo("Updating Voice Mode (UV virtual environment)...")
        
        result = subprocess.run(
            ["uv", "pip", "install", "--upgrade", "voice-mode"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            try:
                new_version = get_version("voice-mode")
                click.echo(f"✅ Successfully updated to version {new_version}")
            except PackageNotFoundError:
                click.echo("✅ Successfully updated Voice Mode")
        else:
            click.echo(f"❌ Update failed: {result.stderr}")
            click.echo("Try running: uv pip install --upgrade voice-mode")
    
    else:
        # Standard installation - try UV if available, else pip
        has_uv = check_uv_available()
        
        if has_uv:
            click.echo("Updating Voice Mode (using UV)...")
            result = subprocess.run(
                ["uv", "pip", "install", "--upgrade", "voice-mode"],
                capture_output=True,
                text=True
            )
        else:
            click.echo("Updating Voice Mode (using pip)...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "voice-mode"],
                capture_output=True,
                text=True
            )
        
        if result.returncode == 0:
            try:
                new_version = get_version("voice-mode")
                click.echo(f"✅ Successfully updated to version {new_version}")
            except PackageNotFoundError:
                click.echo("✅ Successfully updated Voice Mode")
        else:
            click.echo(f"❌ Update failed: {result.stderr}")
            if has_uv:
                click.echo("Try running: uv pip install --upgrade voice-mode")
            else:
                click.echo("Try running: pip install --upgrade voice-mode")


# Completions command
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish']))
@click.option('--install', is_flag=True, help='Install completion script to the appropriate location')
def completions(shell, install):
    """Generate or install shell completion scripts.
    
    Examples:
        voicemode completions bash              # Output bash completion to stdout
        voicemode completions bash --install    # Install to ~/.bash_completion.d/
        voicemode completions zsh --install     # Install to ~/.zfunc/
        voicemode completions fish --install    # Install to ~/.config/fish/completions/
    """
    from pathlib import Path
    
    # Generate completion scripts based on shell type
    if shell == 'bash':
        completion_script = '''# bash completion for voicemode
_voicemode_completion() {
    local IFS=$'\\n'
    local response
    
    response=$(env _VOICEMODE_COMPLETE=bash_complete COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD voicemode 2>/dev/null)
    
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        
        if [[ $type == 'plain' ]]; then
            COMPREPLY+=("$value")
        elif [[ $type == 'file' ]]; then
            COMPREPLY+=("$value")
        elif [[ $type == 'dir' ]]; then
            COMPREPLY+=("$value")
        fi
    done
    
    return 0
}

complete -o default -F _voicemode_completion voicemode
'''
    
    elif shell == 'zsh':
        completion_script = '''#compdef voicemode
# zsh completion for voicemode

_voicemode() {
    local -a response
    response=(${(f)"$(env _VOICEMODE_COMPLETE=zsh_complete COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) voicemode 2>/dev/null)"})
    
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        compadd -U -- "$value"
    done
}

compdef _voicemode voicemode
'''
    
    elif shell == 'fish':
        completion_script = '''# fish completion for voicemode
function __fish_voicemode_complete
    set -l response (env _VOICEMODE_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) voicemode 2>/dev/null)
    
    for completion in $response
        echo $completion
    end
end

complete -c voicemode -f -a '(__fish_voicemode_complete)'
'''
    
    if install:
        # Define installation locations for each shell
        locations = {
            'bash': '~/.bash_completion.d/voicemode',
            'zsh': '~/.zfunc/_voicemode',
            'fish': '~/.config/fish/completions/voicemode.fish'
        }
        
        install_path = Path(locations[shell]).expanduser()
        install_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write completion script to file
        install_path.write_text(completion_script)
        click.echo(f"✅ Installed {shell} completions to {install_path}")
        
        # Provide shell-specific instructions
        if shell == 'bash':
            click.echo("\nTo activate now, run:")
            click.echo(f"  source {install_path}")
            click.echo("\nTo activate permanently, add to ~/.bashrc:")
            click.echo(f"  source {install_path}")
        elif shell == 'zsh':
            click.echo("\nTo activate now, run:")
            click.echo("  autoload -U compinit && compinit")
            click.echo("\nMake sure ~/.zfunc is in your fpath (add to ~/.zshrc):")
            click.echo("  fpath=(~/.zfunc $fpath)")
        elif shell == 'fish':
            click.echo("\nCompletions will be active in new fish sessions.")
            click.echo("To activate now, run:")
            click.echo(f"  source {install_path}")
    else:
        # Output completion script to stdout
        click.echo(completion_script)


# DJ (Background Music) command group
@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def dj():
    """Background music playback for voice sessions.

    Control audio playback via mpv for ambient music during conversations.
    Supports files, URLs, and chapter navigation.

    Examples:
        voicemode dj play /path/to/ambient.mp3
        voicemode dj play https://example.com/stream.mp3 --volume 30
        voicemode dj status
        voicemode dj pause
        voicemode dj stop
    """
    pass


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 2] + ".."


def _print_status_line(status) -> None:
    """Print compact one-line status for tmux status bar.

    Format: Artist - Title Position (-Remaining) ♪
    With tmux color codes for remaining time warnings.
    """
    # Get chapter info or fall back to track info
    if status.chapter:
        # Chapter format is typically "Title - Artist" from ffmeta
        display = status.chapter
    elif status.artist and status.title:
        display = f"{status.artist} - {status.title}"
    elif status.title:
        display = status.title
    else:
        display = status.path or "Unknown"

    # Truncate display to reasonable length
    display = _truncate(display, 40)

    # Position
    pos_str = _format_time(status.position)

    # Remaining time with color coding
    remaining = int(status.remaining)
    remaining_str = _format_time(status.remaining)

    if remaining < 10:
        color = "#[fg=red,bold]"
        reset = "#[fg=default,nobold]"
    elif remaining < 30:
        color = "#[fg=yellow]"
        reset = "#[fg=default]"
    else:
        color = ""
        reset = ""

    # Paused indicator
    icon = "⏸" if status.is_paused else "♪"

    click.echo(f"{display} {pos_str} {color}(-{remaining_str}){reset} {icon}")


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('source')
@click.option('--chapters', '-c', help='Path to chapters file (FFmetadata or CUE)')
@click.option('--volume', '-v', default=50, type=int, help='Initial volume (0-100)')
def play(source: str, chapters: str | None, volume: int):
    """Start playing a file or URL.

    SOURCE can be a local file path or a URL.

    Examples:
        voicemode dj play /path/to/music.mp3
        voicemode dj play /path/to/album.mp3 --chapters /path/to/chapters.txt
        voicemode dj play https://stream.example.com/audio --volume 30
    """
    from voice_mode.dj import DJController

    controller = DJController()
    if controller.play(source, chapters_file=chapters, volume=volume):
        click.echo(f"Playing: {source}")
        if chapters:
            click.echo(f"Chapters: {chapters}")
        click.echo(f"Volume: {volume}%")
    else:
        click.echo("Failed to start playback", err=True)
        click.echo("Make sure mpv is installed: brew install mpv", err=True)


@dj.command()
@click.option('--line', '-l', is_flag=True, help='One-line output for tmux status bar')
@click.help_option('-h', '--help', help='Show this message and exit')
def status(line: bool):
    """Show what's currently playing.

    Displays track information, playback position, volume, and chapter info.

    Use --line for compact tmux status bar output.
    """
    from voice_mode.dj import DJController

    controller = DJController()
    track_status = controller.status()

    if track_status:
        if line:
            # Compact one-line format for tmux status bar
            _print_status_line(track_status)
        else:
            # Full multi-line format
            # Track info
            title = track_status.title or track_status.path or "(unknown)"
            click.echo(f"Track: {title}")

            # Position
            pos_str = _format_time(track_status.position)
            dur_str = _format_time(track_status.duration)
            progress = track_status.progress_percent
            click.echo(f"Position: {pos_str} / {dur_str} ({progress:.0f}%)")

            # Volume and state
            state = "Paused" if track_status.is_paused else "Playing"
            click.echo(f"Volume: {track_status.volume}%")
            click.echo(f"State: {state}")

            # Chapter info if available
            if track_status.chapter_count and track_status.chapter_count > 0:
                chapter_num = (track_status.chapter_index or 0) + 1
                chapter_name = track_status.chapter or f"Chapter {chapter_num}"
                click.echo(f"Chapter: {chapter_name} ({chapter_num}/{track_status.chapter_count})")
    else:
        if not line:
            click.echo("DJ is not running")


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def stop():
    """Stop playback and quit the player."""
    from voice_mode.dj import DJController

    controller = DJController()
    if controller.is_playing():
        controller.stop()
        click.echo("Stopped")
    else:
        click.echo("DJ is not running")


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def pause():
    """Pause playback."""
    from voice_mode.dj import DJController

    controller = DJController()
    if controller.pause():
        click.echo("Paused")
    else:
        click.echo("DJ is not running", err=True)


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def resume():
    """Resume playback."""
    from voice_mode.dj import DJController

    controller = DJController()
    if controller.resume():
        click.echo("Resumed")
    else:
        click.echo("DJ is not running", err=True)


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def next():
    """Skip to the next chapter."""
    from voice_mode.dj import DJController

    controller = DJController()
    status = controller.next()
    if status:
        if status.chapter:
            click.echo(f"Chapter: {status.chapter}")
        elif status.chapter_index is not None and status.chapter_count:
            click.echo(f"Chapter: {status.chapter_index + 1}/{status.chapter_count}")
        else:
            click.echo("Skipped to next chapter")
    else:
        click.echo("DJ is not running", err=True)


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def prev():
    """Go to the previous chapter."""
    from voice_mode.dj import DJController

    controller = DJController()
    status = controller.prev()
    if status:
        if status.chapter:
            click.echo(f"Chapter: {status.chapter}")
        elif status.chapter_index is not None and status.chapter_count:
            click.echo(f"Chapter: {status.chapter_index + 1}/{status.chapter_count}")
        else:
            click.echo("Skipped to previous chapter")
    else:
        click.echo("DJ is not running", err=True)


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('level', required=False, type=int)
def volume(level: int | None):
    """Get or set the volume level.

    Without LEVEL: Shows the current volume.
    With LEVEL: Sets volume to the specified level (0-100).

    Examples:
        voicemode dj volume        # Show current volume
        voicemode dj volume 30     # Set volume to 30%
        voicemode dj volume 100    # Set volume to 100%
    """
    from voice_mode.dj import DJController

    controller = DJController()
    result = controller.volume(level)

    if result is not None:
        if level is not None:
            click.echo(f"Volume: {result}%")
        else:
            click.echo(f"Volume: {result}%")
    else:
        click.echo("DJ is not running", err=True)


# MFP (Music For Programming) subcommand group
@dj.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def mfp():
    """Music For Programming episodes.

    Play curated ambient mixes designed for coding sessions.
    Each episode features chapter markers for track navigation.

    Examples:
        voicemode dj mfp list              # List episodes with chapters
        voicemode dj mfp play 49           # Play episode 49
        voicemode dj mfp sync              # Sync chapter files from package
        voicemode dj mfp edit              # Open visual chapter editor
    """
    pass


@mfp.command("list")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--all', '-a', 'show_all', is_flag=True, help='Show all episodes (not just those with chapters)')
@click.option('--refresh', '-r', is_flag=True, help='Force refresh from RSS feed')
def mfp_list(show_all: bool, refresh: bool):
    """List available Music For Programming episodes.

    By default, only shows episodes that have chapter files for track navigation.
    Use --all to see all episodes from the RSS feed.

    Examples:
        voicemode dj mfp list              # Episodes with chapters
        voicemode dj mfp list --all        # All episodes
        voicemode dj mfp list --refresh    # Refresh from RSS
    """
    from voice_mode.dj.mfp import MfpService

    service = MfpService()
    try:
        episodes = service.list_episodes(with_chapters_only=not show_all, refresh=refresh)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        return

    if not episodes:
        if show_all:
            click.echo("No episodes found in RSS feed.")
        else:
            click.echo("No episodes with chapter files found.")
            click.echo("Use --all to see all episodes, or run 'voicemode dj mfp sync' to sync chapters.")
        return

    title = "All Episodes" if show_all else "Episodes with Chapters"
    click.echo(f"Music For Programming - {title}")
    click.echo("=" * (27 + len(title)))
    click.echo()

    # Header
    click.echo(f"{'#':>3}  {'Curator':<25}  {'Ch':>3}  {'MP3':>3}")
    click.echo("-" * 42)

    for ep in episodes:
        ch_status = "yes" if ep.has_chapters else " - "
        mp3_status = "yes" if ep.has_local_file else " - "
        curator = ep.curator[:25] if len(ep.curator) > 25 else ep.curator
        click.echo(f"{ep.number:3d}  {curator:<25}  {ch_status:>3}  {mp3_status:>3}")

    click.echo()
    click.echo(f"Total: {len(episodes)} episodes")
    click.echo()
    click.echo("Play with: voicemode dj mfp play <number>")


@mfp.command("play")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('episode', type=int)
@click.option('--volume', '-v', default=50, type=int, help='Initial volume (0-100)')
def mfp_play(episode: int, volume: int):
    """Play a Music For Programming episode by number.

    Automatically loads chapter files if available for track navigation.
    Use 'voicemode dj next' and 'voicemode dj prev' to skip between tracks.

    Examples:
        voicemode dj mfp play 49           # Play episode 49
        voicemode dj mfp play 76 -v 30     # Play episode 76 at 30% volume
    """
    from voice_mode.dj import DJController
    from voice_mode.dj.mfp import MfpService

    service = MfpService()
    ep = service.get_episode(episode)

    if not ep:
        click.echo(f"Episode {episode} not found.", err=True)
        click.echo("Use 'voicemode dj mfp list --all' to see available episodes.", err=True)
        return

    # Determine source - prefer local file if available
    local_path = service.get_local_path(episode)
    source = str(local_path) if local_path else ep.url

    # Get chapters file if available
    chapters_path = service.get_chapters_file(episode)

    # Play
    controller = DJController()
    if controller.play(source, chapters_file=str(chapters_path) if chapters_path else None, volume=volume):
        click.echo(f"Playing: MFP {episode} - {ep.curator}")
        if chapters_path:
            click.echo(f"Chapters: Loaded ({chapters_path.name})")
        if local_path:
            click.echo(f"Source: Local file")
        else:
            click.echo(f"Source: Streaming")
        click.echo(f"Volume: {volume}%")
    else:
        click.echo("Failed to start playback", err=True)
        click.echo("Make sure mpv is installed: brew install mpv", err=True)


@mfp.command("sync")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--force', '-f', is_flag=True, help='Overwrite local files even if modified')
def mfp_sync(force: bool):
    """Sync chapter files from package to local cache.

    Copies chapter files bundled with VoiceMode to your local cache directory.
    Compares checksums to identify new and updated files.

    User modifications are preserved unless --force is used, in which case
    they are backed up with a .user extension.

    Examples:
        voicemode dj mfp sync              # Sync new chapter files
        voicemode dj mfp sync --force      # Overwrite local modifications
    """
    from voice_mode.dj.mfp import MfpService

    service = MfpService()
    results = service.sync_chapters(force=force)

    if not results:
        click.echo("No chapter files found in package.")
    else:
        click.echo()
        click.echo("Chapter sync complete")

    click.echo(f"Cache directory: {service.cache_dir}")


@mfp.command("edit")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('episode', type=int, required=False)
def mfp_edit(episode: int | None):
    """Open the visual chapter editor for MFP episodes.

    Launches a Marimo app with an interactive waveform editor for adjusting
    chapter timestamps. The editor displays the audio waveform with draggable
    markers for each chapter boundary.

    Features:
    - Interactive waveform with WaveSurfer.js
    - Drag chapter boundaries to adjust timestamps
    - Add new chapter markers
    - Auto-saves changes to CUE files
    - Persists unsaved edits in browser localStorage

    Requires: marimo, pandas, numpy, scipy (installed with `uv run`)

    Examples:
        voicemode dj mfp edit              # Edit first available episode
        voicemode dj mfp edit 49           # Edit episode 49
    """
    import subprocess
    import sys
    from pathlib import Path

    # Get the editor module path
    editor_path = Path(__file__).parent / "dj" / "mfp_editor.py"

    if not editor_path.exists():
        click.echo(f"Error: Editor module not found at {editor_path}", err=True)
        sys.exit(1)

    # Build the command - run marimo with the editor script
    # Use 'uv run' to ensure dependencies are available
    cmd = ["uv", "run", "marimo", "run", str(editor_path)]

    click.echo("Starting MFP Chapter Editor...")
    click.echo(f"Opening in browser at http://localhost:2718")
    click.echo()
    click.echo("Press Ctrl+C to stop the editor.")
    click.echo()

    try:
        # Run marimo, passing through stdin/stdout for interactive use
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"Editor exited with error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nEditor stopped.")
    except FileNotFoundError:
        click.echo("Error: 'uv' not found. Please install uv: https://docs.astral.sh/uv/", err=True)
        click.echo("Or run directly with: marimo run " + str(editor_path), err=True)
        sys.exit(1)


# Music library search command (top-level under dj for convenience)
@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('query')
@click.option('--limit', '-l', default=50, type=int, help='Maximum results to show')
@click.option('--all', '-a', 'include_sidecars', is_flag=True, help='Include sidecars (stems, loops)')
def find(query: str, limit: int, include_sidecars: bool):
    """Search music library by artist, album, or title.

    Searches the indexed music library for tracks matching QUERY.
    Results show track ID, artist, title, and album.

    Examples:
        voicemode dj find "daft punk"      # Search for Daft Punk tracks
        voicemode dj find ambient          # Search for ambient music
        voicemode dj find --limit 10 jazz  # Show top 10 jazz results
    """
    from voice_mode.dj.library import MusicLibrary

    library = MusicLibrary()
    tracks = library.search(query, limit=limit, include_sidecars=include_sidecars)

    if not tracks:
        click.echo(f"No tracks found matching '{query}'")
        click.echo()
        click.echo("Tip: Make sure you've scanned your library:")
        click.echo("  voicemode dj library scan --path ~/Audio/music")
        return

    # Display results in a table format
    for track in tracks:
        artist = track.artist or "(unknown)"
        title = track.title
        album = track.album or ""
        fav = "*" if track.is_favorite else ""
        sidecar = f" [{track.sidecar_type}]" if track.is_sidecar else ""
        click.echo(f"[{track.id}] {fav}{artist} - {title}{sidecar}")
        if album:
            click.echo(f"     Album: {album}")

    click.echo()
    click.echo(f"Found {len(tracks)} track(s)")


# Library subcommand group
@dj.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def library():
    """Music library management.

    Commands for scanning, indexing, and managing your local music library.

    Examples:
        voicemode dj library scan          # Scan default music folder
        voicemode dj library stats         # Show library statistics
    """
    pass


@library.command("scan")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--path', '-p', type=click.Path(exists=True), help='Music directory to scan')
def library_scan(path: str | None):
    """Scan and index music folder.

    Scans the music directory and indexes all audio files.
    Metadata is parsed from directory structure: Artist/Year-Album/Track.ext

    Supported formats: mp3, flac, m4a, wav, ogg, opus

    Examples:
        voicemode dj library scan                    # Scan ~/Audio/music
        voicemode dj library scan --path ~/Music    # Scan custom path
    """
    from pathlib import Path
    from voice_mode.dj.library import MusicLibrary

    library = MusicLibrary()
    music_path = Path(path) if path else library.music_root

    click.echo(f"Scanning: {music_path}")
    click.echo()

    count = library.scan(music_path)

    if count > 0:
        click.echo(f"Indexed {count} file(s)")
        click.echo()
        # Show stats
        stats = library.stats()
        click.echo(f"Library: {stats.total_tracks} tracks, {stats.total_artists} artists, {stats.total_albums} albums")
        if stats.total_sidecars > 0:
            click.echo(f"Sidecars: {stats.total_sidecars} (stems/loops/samples)")
    else:
        click.echo("No audio files found.")
        click.echo()
        click.echo(f"Make sure {music_path} contains audio files in the format:")
        click.echo("  Artist/Year-Album/Track.mp3")


@library.command("stats")
@click.help_option('-h', '--help', help='Show this message and exit')
def library_stats():
    """Show library statistics.

    Displays summary information about your indexed music library.

    Examples:
        voicemode dj library stats
    """
    from voice_mode.dj.library import MusicLibrary

    library = MusicLibrary()
    stats = library.stats()

    if stats.total_tracks == 0:
        click.echo("Music library is empty.")
        click.echo()
        click.echo("Scan your music folder first:")
        click.echo("  voicemode dj library scan --path ~/Audio/music")
        return

    click.echo("Music Library Statistics")
    click.echo("========================")
    click.echo(f"Total tracks:  {stats.total_tracks}")
    click.echo(f"Sidecars:      {stats.total_sidecars}")
    click.echo(f"Favorites:     {stats.total_favorites}")
    click.echo(f"Artists:       {stats.total_artists}")
    click.echo(f"Albums:        {stats.total_albums}")
    click.echo()
    click.echo(f"Database: {library.db_path}")


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--limit', '-l', default=20, type=int, help='Number of entries to show')
def history(limit: int):
    """Show recently played tracks.

    Displays the play history with timestamps, most recent first.
    Only shows tracks that are in the indexed music library.

    Examples:
        voicemode dj history              # Show last 20 plays
        voicemode dj history --limit 50   # Show last 50 plays
    """
    from voice_mode.dj.library import MusicLibrary

    library = MusicLibrary()
    entries = library.get_history(limit=limit)

    if not entries:
        click.echo("No play history yet.")
        click.echo()
        click.echo("Play some tracks from your library:")
        click.echo("  voicemode dj find <search term>")
        return

    click.echo("Play History")
    click.echo("============")
    click.echo()

    for track, played_at in entries:
        artist = track.artist or "(unknown)"
        title = track.title
        fav = "*" if track.is_favorite else ""
        # Format the timestamp nicely if possible
        timestamp = played_at[:19] if played_at else ""  # Trim to YYYY-MM-DD HH:MM:SS
        click.echo(f"[{timestamp}] {fav}{artist} - {title}")

    click.echo()
    click.echo(f"Showing {len(entries)} play(s)")


@dj.command()
@click.help_option('-h', '--help', help='Show this message and exit')
def favorite():
    """Toggle favorite status of the currently playing track.

    Marks the currently playing track as a favorite (or removes it from favorites
    if already marked). The track must be in the indexed music library.

    Examples:
        voicemode dj favorite    # Toggle favorite on current track
    """
    from pathlib import Path
    from voice_mode.dj import DJController
    from voice_mode.dj.library import MusicLibrary

    controller = DJController()
    status = controller.status()

    if not status:
        click.echo("DJ is not running", err=True)
        return

    if not status.path:
        click.echo("No track path available", err=True)
        return

    library = MusicLibrary()

    # Try to find the track in the library
    # The status.path might be an absolute path, so try to match it
    track_path = Path(status.path)

    # First, try looking up by the path as-is (might be relative)
    track = library.get_track_by_path(status.path)

    # If not found and it's an absolute path under music_root, try relative
    if not track and track_path.is_absolute():
        try:
            rel_path = str(track_path.relative_to(library.music_root))
            track = library.get_track_by_path(rel_path)
        except ValueError:
            pass

    if not track:
        click.echo(f"Track not found in library: {status.path}", err=True)
        click.echo()
        click.echo("Make sure the track is indexed:")
        click.echo("  voicemode dj library scan")
        return

    is_favorite = library.toggle_favorite(track.id)
    status_str = "added to" if is_favorite else "removed from"

    artist = track.artist or "(unknown)"
    click.echo(f"{artist} - {track.title} {status_str} favorites")


