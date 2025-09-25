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
    logging.getLogger("voice-mode").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Service management CLI - runs MCP server by default, subcommands override
@click.group(invoke_without_command=True)
@click.version_option()
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
        logging.getLogger("voice-mode").setLevel(logging.INFO)

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


# Audio group for audio-related commands
@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def audio():
    """Audio transcription and playback commands."""
    pass


# Service group commands
@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def kokoro():
    """Manage Kokoro TTS service."""
    pass


@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper():
    """Manage Whisper STT service."""
    pass


@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def livekit():
    """Manage LiveKit RTC service."""
    pass


# Service functions are imported lazily in their respective command handlers to improve startup time


# Kokoro service commands
@kokoro.command()
def status():
    """Show Kokoro service status."""
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("kokoro"))
    click.echo(result)


@kokoro.command()
def start():
    """Start Kokoro service."""
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("kokoro"))
    click.echo(result)


@kokoro.command()
def stop():
    """Stop Kokoro service."""
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("kokoro"))
    click.echo(result)


@kokoro.command()
def restart():
    """Restart Kokoro service."""
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("kokoro"))
    click.echo(result)


@kokoro.command()
def enable():
    """Enable Kokoro service to start at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("kokoro"))
    click.echo(result)


@kokoro.command()
def disable():
    """Disable Kokoro service from starting at boot/login."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("kokoro"))
    click.echo(result)


@kokoro.command()
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def logs(lines):
    """View Kokoro service logs."""
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("kokoro", lines))
    click.echo(result)


@kokoro.command("update-service-files")
def kokoro_update_service_files():
    """Update Kokoro service files to latest version."""
    from voice_mode.tools.service import update_service_files
    result = asyncio.run(update_service_files("kokoro"))
    click.echo(result)


@kokoro.command()
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
def install(install_dir, port, force, version, auto_enable):
    """Install kokoro-fastapi TTS service."""
    from voice_mode.tools.kokoro.install import kokoro_install
    result = asyncio.run(kokoro_install.fn(
        install_dir=install_dir,
        port=port,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable
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


# Whisper service commands  
@whisper.command()
def status():
    """Show Whisper service status."""
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("whisper"))
    click.echo(result)


@whisper.command()
def start():
    """Start Whisper service."""
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("whisper"))
    click.echo(result)


@whisper.command()
def stop():
    """Stop Whisper service."""
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("whisper"))
    click.echo(result)


@whisper.command()
def restart():
    """Restart Whisper service."""
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("whisper"))
    click.echo(result)


@whisper.command()
def enable():
    """Enable Whisper service to start at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("whisper"))
    click.echo(result)


@whisper.command()
def disable():
    """Disable Whisper service from starting at boot/login."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("whisper"))
    click.echo(result)


@whisper.command()
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def logs(lines):
    """View Whisper service logs."""
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("whisper", lines))
    click.echo(result)


@whisper.command("update-service-files")
def whisper_update_service_files():
    """Update Whisper service files to latest version."""
    from voice_mode.tools.service import update_service_files
    result = asyncio.run(update_service_files("whisper"))
    click.echo(result)


@whisper.command()
def health():
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


@whisper.command()
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install whisper.cpp')
@click.option('--model', default='large-v2', help='Whisper model to download (default: large-v2)')
@click.option('--use-gpu/--no-gpu', default=None, help='Enable GPU support if available')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
def install(install_dir, model, use_gpu, force, version, auto_enable):
    """Install whisper.cpp STT service with automatic system detection."""
    from voice_mode.tools.whisper.install import whisper_install
    result = asyncio.run(whisper_install.fn(
        install_dir=install_dir,
        model=model,
        use_gpu=use_gpu,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable
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
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@whisper.command()
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Whisper models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Whisper data including logs and transcriptions')
@click.confirmation_option(prompt='Are you sure you want to uninstall Whisper?')
def uninstall(remove_models, remove_all_data):
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


@whisper.group("model")
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper_model():
    """Manage Whisper models.
    
    Subcommands:
      active   - Show or set the active model
      install  - Download and install models
      remove   - Remove installed models
    """
    pass


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


@whisper.command("models")
def whisper_models():
    """List available Whisper models and their installation status."""
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
@click.argument('model', default='large-v2')
@click.option('--force', '-f', is_flag=True, help='Re-download even if model exists')
@click.option('--skip-core-ml', is_flag=True, help='Skip Core ML conversion on Apple Silicon')
@click.option('--install-torch', is_flag=True, help='Install PyTorch for Core ML conversion (~2.5GB)')
def whisper_model_install(model, force, skip_core_ml, install_torch):
    """Install Whisper model(s) with optional Core ML conversion.
    
    MODEL can be a model name (e.g., 'large-v2'), 'all' to download all models,
    or omitted to use the default (large-v2).
    
    Available models: tiny, tiny.en, base, base.en, small, small.en,
    medium, medium.en, large-v1, large-v2, large-v3, large-v3-turbo
    """
    import json
    import voice_mode.tools.whisper.model_install as install_module
    # Get the actual function from the MCP tool wrapper
    tool = install_module.whisper_model_install
    install_func = tool.fn if hasattr(tool, 'fn') else tool
    
    # First attempt without install_torch to check if it's needed
    result = asyncio.run(install_func(
        model=model,
        force_download=force,
        skip_core_ml=skip_core_ml,
        install_torch=install_torch,
        auto_confirm=install_torch  # If user passed --install-torch, skip confirmation
    ))
    
    try:
        # Parse JSON response
        data = json.loads(result)
        
        # Check if PyTorch installation is required for Core ML
        if data.get('requires_confirmation') and not install_torch and not skip_core_ml:
            click.echo("\n" + data.get('message', 'Core ML requires PyTorch (~2.5GB)'))
            if data.get('recommendation'):
                click.echo(f"💡 {data['recommendation']}")
            
            if click.confirm("\nWould you like to install PyTorch for Core ML acceleration?"):
                # Retry with install_torch=True
                result = asyncio.run(install_func(
                    model=model,
                    force_download=force,
                    skip_core_ml=skip_core_ml,
                    install_torch=True,
                    auto_confirm=True
                ))
                data = json.loads(result)
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


# LiveKit service commands
@livekit.command()
def status():
    """Show LiveKit service status."""
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("livekit"))
    click.echo(result)


@livekit.command()
def start():
    """Start LiveKit service."""
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("livekit"))
    click.echo(result)


@livekit.command()
def stop():
    """Stop LiveKit service."""
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("livekit"))
    click.echo(result)


@livekit.command()
def restart():
    """Restart LiveKit service."""
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("livekit"))
    click.echo(result)


@livekit.command()
def enable():
    """Enable LiveKit service to start at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("livekit"))
    click.echo(result)


@livekit.command()
def disable():
    """Disable LiveKit service from starting at boot/login."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("livekit"))
    click.echo(result)


@livekit.command()
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def logs(lines):
    """View LiveKit service logs."""
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("livekit", lines))
    click.echo(result)


@livekit.command()
def update():
    """Update LiveKit service files to the latest version."""
    from voice_mode.tools.service import update_service_files
    result = asyncio.run(update_service_files("livekit"))
    
    if result.get("success"):
        click.echo("✅ LiveKit service files updated successfully")
        if result.get("message"):
            click.echo(f"   {result['message']}")
    else:
        click.echo(f"❌ {result.get('message', 'Update failed')}")


@livekit.command()
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install LiveKit')
@click.option('--port', default=7880, help='Port for LiveKit server (default: 7880)')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
def install(install_dir, port, force, version, auto_enable):
    """Install LiveKit server with development configuration."""
    from voice_mode.tools.livekit.install import livekit_install
    result = asyncio.run(livekit_install.fn(
        install_dir=install_dir,
        port=port,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable
    ))
    
    if result.get('success'):
        if result.get('already_installed'):
            click.echo(f"✅ LiveKit already installed at {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
        else:
            click.echo("✅ LiveKit installed successfully!")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
            click.echo(f"   Install path: {result['install_path']}")
            click.echo(f"   Config: {result['config_path']}")
            click.echo(f"   Port: {result['port']}")
            click.echo(f"   URL: {result['url']}")
            click.echo(f"   Dev credentials: {result['dev_key']} / {result['dev_secret']}")
            
            if result.get('service_installed'):
                click.echo("   Service installed")
                if result.get('service_enabled'):
                    click.echo("   Service enabled (will start at boot/login)")
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@livekit.command()
@click.help_option('-h', '--help')
@click.option('--remove-config', is_flag=True, help='Also remove LiveKit configuration files')
@click.option('--remove-all-data', is_flag=True, help='Remove all LiveKit data including logs')
@click.confirmation_option(prompt='Are you sure you want to uninstall LiveKit?')
def uninstall(remove_config, remove_all_data):
    """Uninstall LiveKit server and optionally remove configuration and data."""
    from voice_mode.tools.livekit.uninstall import livekit_uninstall
    result = asyncio.run(livekit_uninstall.fn(
        remove_config=remove_config,
        remove_all_data=remove_all_data
    ))
    
    if result.get('success'):
        click.echo("✅ LiveKit uninstalled successfully!")
        
        if result.get('removed_items'):
            click.echo("\n📦 Removed:")
            for item in result['removed_items']:
                click.echo(f"   ✓ {item}")
                
        if result.get('warnings'):
            click.echo("\n⚠️  Warnings:")
            for warning in result['warnings']:
                click.echo(f"   - {warning}")
    else:
        click.echo(f"❌ Uninstall failed: {result.get('error', 'Unknown error')}")


# LiveKit frontend subcommands
@livekit.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def frontend():
    """Manage LiveKit Voice Assistant Frontend."""
    pass


@frontend.command("install")
@click.help_option('-h', '--help')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service after installation (default: from config)')
def frontend_install(auto_enable):
    """Install and setup LiveKit Voice Assistant Frontend."""
    from voice_mode.tools.livekit.frontend import livekit_frontend_install
    result = asyncio.run(livekit_frontend_install.fn(auto_enable=auto_enable))
    
    if result.get('success'):
        click.echo("✅ LiveKit Frontend setup completed!")
        click.echo(f"   Frontend directory: {result['frontend_dir']}")
        click.echo(f"   Log directory: {result['log_dir']}")
        click.echo(f"   Node.js available: {result['node_available']}")
        if result.get('node_path'):
            click.echo(f"   Node.js path: {result['node_path']}")
        click.echo(f"   Service installed: {result['service_installed']}")
        click.echo(f"   Service enabled: {result['service_enabled']}")
        click.echo(f"   URL: {result['url']}")
        click.echo(f"   Password: {result['password']}")
        
        if result.get('service_enabled'):
            click.echo("\n💡 Frontend service is enabled and will start automatically at boot/login")
        else:
            click.echo("\n💡 Run 'voicemode livekit frontend enable' to start automatically at boot/login")
    else:
        click.echo(f"❌ Frontend installation failed: {result.get('error', 'Unknown error')}")


@frontend.command("start")
@click.help_option('-h', '--help')
@click.option('--port', default=3000, help='Port to run frontend on (default: 3000)')
@click.option('--host', default='127.0.0.1', help='Host to bind to (default: 127.0.0.1)')
def frontend_start(port, host):
    """Start the LiveKit Voice Assistant Frontend."""
    from voice_mode.tools.livekit.frontend import livekit_frontend_start
    result = asyncio.run(livekit_frontend_start.fn(port=port, host=host))
    
    if result.get('success'):
        click.echo("✅ LiveKit Frontend started successfully!")
        click.echo(f"   URL: {result['url']}")
        click.echo(f"   Password: {result['password']}")
        click.echo(f"   PID: {result['pid']}")
        click.echo(f"   Directory: {result['directory']}")
    else:
        error_msg = result.get('error', 'Unknown error')
        click.echo(f"❌ Failed to start frontend: {error_msg}")
        if "Cannot find module" in error_msg or "dependencies" in error_msg.lower():
            click.echo("")
            click.echo("💡 Try fixing dependencies with:")
            click.echo("   ./bin/fix-frontend-deps.sh")
            click.echo("   or manually: cd vendor/livekit-voice-assistant/voice-assistant-frontend && pnpm install")


@frontend.command("stop")
def frontend_stop():
    """Stop the LiveKit Voice Assistant Frontend."""
    from voice_mode.tools.livekit.frontend import livekit_frontend_stop
    result = asyncio.run(livekit_frontend_stop.fn())
    
    if result.get('success'):
        click.echo(f"✅ {result['message']}")
    else:
        click.echo(f"❌ Failed to stop frontend: {result.get('error', 'Unknown error')}")


@frontend.command("status")
def frontend_status():
    """Check status of the LiveKit Voice Assistant Frontend."""
    from voice_mode.tools.livekit.frontend import livekit_frontend_status
    result = asyncio.run(livekit_frontend_status.fn())
    
    if 'error' in result:
        click.echo(f"❌ Error: {result['error']}")
        return
    
    if result.get('running'):
        click.echo("✅ Frontend is running")
        click.echo(f"   PID: {result['pid']}")
        click.echo(f"   URL: {result['url']}")
    else:
        click.echo("❌ Frontend is not running")
    
    click.echo(f"   Directory: {result.get('directory', 'Not found')}")
    
    if result.get('configuration'):
        click.echo("   Configuration:")
        for key, value in result['configuration'].items():
            click.echo(f"     {key}: {value}")


@frontend.command("open")
def frontend_open():
    """Open the LiveKit Voice Assistant Frontend in your browser.
    
    Starts the frontend if not already running, then opens it in the default browser.
    """
    from voice_mode.tools.livekit.frontend import livekit_frontend_open
    result = asyncio.run(livekit_frontend_open.fn())
    
    if result.get('success'):
        click.echo("✅ Frontend opened in browser!")
        click.echo(f"   URL: {result['url']}")
        click.echo(f"   Password: {result['password']}")
        if result.get('hint'):
            click.echo(f"   💡 {result['hint']}")
    else:
        click.echo(f"❌ Failed to open frontend: {result.get('error', 'Unknown error')}")


@frontend.command("logs")
@click.help_option('-h', '--help')
@click.option("--lines", "-n", default=50, help="Number of lines to show (default: 50)")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (tail -f)")
def frontend_logs(lines, follow):
    """View LiveKit Voice Assistant Frontend logs.
    
    Shows the last N lines of frontend logs. Use --follow to tail the logs.
    """
    if follow:
        # For following, run tail -f directly
        from voice_mode.tools.livekit.frontend import livekit_frontend_logs
        result = asyncio.run(livekit_frontend_logs.fn(follow=True))
        if result.get('success'):
            click.echo(f"📂 Log file: {result['log_file']}")
            click.echo("🔄 Following logs (press Ctrl+C to stop)...")
            try:
                import subprocess
                subprocess.run(["tail", "-f", result['log_file']])
            except KeyboardInterrupt:
                click.echo("\n✅ Stopped following logs")
        else:
            click.echo(f"❌ Error: {result.get('error', 'Unknown error')}")
    else:
        # Show last N lines
        from voice_mode.tools.livekit.frontend import livekit_frontend_logs
        result = asyncio.run(livekit_frontend_logs.fn(lines=lines, follow=False))
        if result.get('success'):
            click.echo(f"📂 Log file: {result['log_file']}")
            click.echo(f"📄 Showing last {result['lines_shown']} lines:")
            click.echo("─" * 60)
            click.echo(result['logs'])
        else:
            click.echo(f"❌ Error: {result.get('error', 'Unknown error')}")


@frontend.command("enable")
def frontend_enable():
    """Enable frontend service to start automatically at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("frontend"))
    # enable_service returns a string, not a dict
    click.echo(result)


@frontend.command("disable")
def frontend_disable():
    """Disable frontend service from starting automatically."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("frontend"))
    # disable_service returns a string, not a dict
    click.echo(result)


@frontend.command("build")
@click.help_option('-h', '--help')
@click.option('--force', '-f', is_flag=True, help='Force rebuild even if build exists')
def frontend_build(force):
    """Build frontend for production (requires Node.js)."""
    import subprocess
    from pathlib import Path
    
    frontend_dir = Path(__file__).parent / "frontend"
    if not frontend_dir.exists():
        click.echo("❌ Frontend directory not found")
        return
    
    build_dir = frontend_dir / ".next"
    if build_dir.exists() and not force:
        click.echo("✅ Frontend already built. Use --force to rebuild.")
        click.echo(f"   Build directory: {build_dir}")
        return
    
    click.echo("🔨 Building frontend for production...")
    
    # Check Node.js availability
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        click.echo("❌ Node.js not found. Please install Node.js to build the frontend.")
        return
    
    # Change to frontend directory and build
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(frontend_dir)
        
        # Install dependencies if needed
        if not (frontend_dir / "node_modules").exists():
            click.echo("📦 Installing dependencies...")
            subprocess.run(["npm", "install"], check=True)
        
        # Build with production settings
        click.echo("🏗️  Building standalone production version...")
        env = os.environ.copy()
        env["BUILD_STANDALONE"] = "true"
        subprocess.run(["npm", "run", "build:standalone"], check=True, env=env)
        
        click.echo("✅ Frontend built successfully!")
        click.echo(f"   Build directory: {build_dir}")
        click.echo("   Frontend will now start in production mode.")
        
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Build failed: {e}")
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
    finally:
        os.chdir(original_cwd)


# Configuration management group
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
from voice_mode.cli_commands import pronounce_commands
from voice_mode.cli_commands import claude
from voice_mode.cli_commands import hook as hook_cmd

# Add subcommands to legacy CLI
cli.add_command(exchanges_cmd.exchanges)
cli.add_command(transcribe_cmd.transcribe)
cli.add_command(pronounce_commands.pronounce_group)
cli.add_command(claude.claude_group)

# Add exchanges to main CLI
voice_mode_main_cli.add_command(exchanges_cmd.exchanges)
voice_mode_main_cli.add_command(claude.claude_group)

# Note: We'll add these commands after the groups are defined
# audio group will get transcribe and play commands
# claude group will get hook command  
# config group will get pronounce command


# Now add the subcommands to their respective groups
# Add transcribe command to audio group
transcribe_audio_cmd = transcribe_cmd.transcribe.commands['audio']
transcribe_audio_cmd.name = 'transcribe'
audio.add_command(transcribe_audio_cmd)

# Add hooks command under claude group
from voice_mode.cli_commands.hook import hooks
claude.claude_group.add_command(hooks)

# Add pronounce under config group
config.add_command(pronounce_commands.pronounce_group)

# Converse command - direct voice conversation from CLI
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--message', '-m', default="Hello! How can I help you today?", help='Initial message to speak')
@click.option('--wait/--no-wait', default=True, help='Wait for response after speaking')
@click.option('--duration', '-d', type=float, default=30.0, help='Listen duration in seconds')
@click.option('--min-duration', type=float, default=2.0, help='Minimum listen duration before silence detection')
@click.option('--transport', type=click.Choice(['auto', 'local', 'livekit']), default='auto', help='Transport method')
@click.option('--room-name', default='', help='LiveKit room name (for livekit transport)')
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
def converse(message, wait, duration, min_duration, transport, room_name, voice, tts_provider, 
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
    from voice_mode.tools.converse import converse as converse_fn
    
    async def run_conversation():
        """Run the conversation asynchronously."""
        # Suppress the spurious aiohttp warning that appears on startup
        # This warning is a false positive from asyncio detecting an unclosed
        # session that was likely created during module import
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)

        try:
            if continuous:
                # Continuous conversation mode
                click.echo("🎤 Starting continuous conversation mode...")
                click.echo("   Press Ctrl+C to exit\n")
                
                # First message
                result = await converse_fn.fn(
                    message=message,
                    wait_for_response=True,
                    listen_duration=duration,
                    min_listen_duration=min_duration,
                    transport=transport,
                    room_name=room_name,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    audio_feedback=audio_feedback,
                    audio_feedback_style=None,
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
                        listen_duration=duration,
                        min_listen_duration=min_duration,
                        transport=transport,
                        room_name=room_name,
                        voice=voice,
                        tts_provider=tts_provider,
                        tts_model=tts_model,
                        tts_instructions=tts_instructions,
                        audio_feedback=audio_feedback,
                        audio_feedback_style=None,
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
                    listen_duration=duration,
                    min_listen_duration=min_duration,
                    transport=transport,
                    room_name=room_name,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    audio_feedback=audio_feedback,
                    audio_feedback_style=None,
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


# Version command
@voice_mode_main_cli.command()
def version():
    """Show Voice Mode version and check for updates."""
    import requests
    from importlib.metadata import version as get_version, PackageNotFoundError
    
    try:
        current_version = get_version("voice-mode")
    except PackageNotFoundError:
        # Fallback for development installations
        current_version = "development"
    
    click.echo(f"Voice Mode version: {current_version}")
    
    # Check for updates if not in development mode
    if current_version != "development":
        try:
            response = requests.get(
                "https://pypi.org/pypi/voice-mode/json",
                timeout=2
            )
            if response.status_code == 200:
                latest_version = response.json()["info"]["version"]
                
                # Simple version comparison (works for semantic versioning)
                if latest_version != current_version:
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


# Sound Fonts command
@audio.command("play")
@click.help_option('-h', '--help')
@click.option('-t', '--tool', help='Tool name for direct command-line usage')
@click.option('-a', '--action', default='start', type=click.Choice(['start', 'end']), help='Action type')
@click.option('-s', '--subagent', help='Subagent type (for Task tool)')
def play_sound(tool, action, subagent):
    """Play sound based on tool events (primarily for Claude Code hooks).
    
    This command is designed to be called by Claude Code hooks to play sounds
    when tools are used. It reads hook data from stdin by default, or can be
    used directly with command-line options.
    
    Examples:
        echo '{"tool_name":"Task","tool_input":{"subagent_type":"mama-bear"}}' | voicemode play-sound
        voicemode play-sound --tool Task --action start --subagent mama-bear
    """
    import sys
    from .tools.sound_fonts.player import AudioPlayer
    from .tools.sound_fonts.hook_handler import (
        read_hook_data_from_stdin,
        parse_claude_code_hook
    )
    
    # Try to read hook data from stdin first
    hook_data = None
    if not sys.stdin.isatty():
        hook_data = read_hook_data_from_stdin()
    
    if hook_data:
        # Parse Claude Code hook format
        parsed_data = parse_claude_code_hook(hook_data)
        if not parsed_data:
            sys.exit(1)
            
        tool_name = parsed_data["tool_name"]
        action_type = parsed_data["action"]
        subagent_type = parsed_data["subagent_type"]
        metadata = parsed_data["metadata"]
    else:
        # Use command-line arguments
        if not tool:
            click.echo("Error: --tool is required when not reading from stdin", err=True)
            sys.exit(1)
            
        tool_name = tool
        action_type = action
        subagent_type = subagent
        metadata = {}
    
    # Play the sound
    player = AudioPlayer()
    success = player.play_sound_for_event(
        tool_name=tool_name,
        action=action_type,
        subagent_type=subagent_type,
        metadata=metadata
    )
    
    # Silent exit for hooks - don't clutter Claude Code output
    sys.exit(0 if success else 1)


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


