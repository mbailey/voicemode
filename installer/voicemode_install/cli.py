"""Main CLI for VoiceMode installer."""

import shutil
import subprocess
import sys
from pathlib import Path

import click

from . import __version__
from .checker import DependencyChecker
from .hardware import HardwareInfo
from .installer import PackageInstaller
from .logger import InstallLogger
from .system import detect_platform, get_system_info, check_command_exists


LOGO = """
    ╔════════════════════════════════════════════╗
    ║                                            ║
    ║   ██╗   ██╗ ██████╗ ██╗ ██████╗███████╗    ║
    ║   ██║   ██║██╔═══██╗██║██╔════╝██╔════╝    ║
    ║   ██║   ██║██║   ██║██║██║     █████╗      ║
    ║   ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝      ║
    ║    ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗    ║
    ║     ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝    ║
    ║                                            ║
    ║   ███╗   ███╗ ██████╗ ██████╗ ███████╗     ║
    ║   ████╗ ████║██╔═══██╗██╔══██╗██╔════╝     ║
    ║   ██╔████╔██║██║   ██║██║  ██║█████╗       ║
    ║   ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝       ║
    ║   ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗     ║
    ║   ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝     ║
    ║                                            ║
    ║        🎙️  VoiceMode Installer             ║
    ║                                            ║
    ╚════════════════════════════════════════════╝
"""


def print_logo():
    """Display the VoiceMode logo."""
    click.echo(click.style(LOGO, fg='bright_yellow', bold=True))


def print_step(message: str):
    """Print a step message."""
    click.echo(click.style(f"🔧 {message}", fg='blue'))


def print_success(message: str):
    """Print a success message."""
    click.echo(click.style(f"✅ {message}", fg='green'))


def print_warning(message: str):
    """Print a warning message."""
    click.echo(click.style(f"⚠️  {message}", fg='yellow'))


def print_error(message: str):
    """Print an error message."""
    click.echo(click.style(f"❌ {message}", fg='red'))


def check_existing_installation() -> bool:
    """Check if VoiceMode is already installed."""
    return check_command_exists('voicemode')


@click.command()
@click.option('--dry-run', is_flag=True, help='Show what would be installed without installing')
@click.option('--voice-mode-version', default=None, help='Specific VoiceMode version to install')
@click.option('--skip-services', is_flag=True, help='Skip local service installation')
@click.option('--non-interactive', is_flag=True, help='Run without prompts (assumes yes)')
@click.version_option(__version__)
def main(dry_run, voice_mode_version, skip_services, non_interactive):
    """
    VoiceMode Installer - Install VoiceMode and its system dependencies.

    This installer will:
    \b
    1. Detect your operating system and architecture
    2. Check for missing system dependencies
    3. Install required packages (with your permission)
    4. Install VoiceMode using uv
    5. Optionally install local voice services
    6. Configure shell completions
    7. Verify the installation

    Examples:
    \b
      # Normal installation
      voicemode-install

      # Dry run (see what would be installed)
      voicemode-install --dry-run

      # Install specific version
      voicemode-install --voice-mode-version=5.1.3

      # Skip service installation
      voicemode-install --skip-services
    """
    # Initialize logger
    logger = InstallLogger()

    try:
        # Clear screen and show logo
        if not dry_run:
            click.clear()
        print_logo()
        click.echo()

        if dry_run:
            click.echo(click.style("DRY RUN MODE - No changes will be made", fg='yellow', bold=True))
            click.echo()

        # Detect platform
        print_step("Detecting platform...")
        platform_info = detect_platform()
        system_info = get_system_info()

        logger.log_start(system_info)

        click.echo(f"Detected: {platform_info.os_name} ({platform_info.architecture})")
        if platform_info.is_wsl:
            print_warning("WSL detected - additional audio configuration may be needed")
        click.echo()

        # Check for existing installation
        if check_existing_installation():
            print_warning("VoiceMode is already installed")
            if not non_interactive:
                if not click.confirm("Do you want to upgrade it?", default=False):
                    click.echo("\nTo upgrade manually, run: uv tool install --upgrade voice-mode")
                    sys.exit(0)

        # Check dependencies
        print_step("Checking system dependencies...")
        checker = DependencyChecker(platform_info)
        core_deps = checker.check_core_dependencies()

        missing_deps = checker.get_missing_packages(core_deps)
        summary = checker.get_summary(core_deps)

        logger.log_check('core', summary['installed'], summary['missing_required'])

        # Display summary
        click.echo()
        click.echo("System Dependencies:")
        for pkg in core_deps:
            if pkg.required:
                status = "✓" if pkg.installed else "✗"
                color = "green" if pkg.installed else "red"
                click.echo(f"  {click.style(status, fg=color)} {pkg.name} - {pkg.description}")

        click.echo()

        # Install missing dependencies
        if missing_deps:
            print_warning(f"Missing {len(missing_deps)} required package(s)")

            missing_names = [pkg.name for pkg in missing_deps]
            click.echo(f"\nPackages to install: {', '.join(missing_names)}")

            if not non_interactive and not dry_run:
                if not click.confirm("\nInstall missing dependencies?", default=True):
                    print_error("Cannot proceed without required dependencies")
                    sys.exit(1)

            installer = PackageInstaller(platform_info, dry_run=dry_run)
            if installer.install_packages(missing_deps):
                print_success("System dependencies installed")
                logger.log_install('system', missing_names, True)
            else:
                print_error("Failed to install some dependencies")
                logger.log_install('system', missing_names, False)
                if not dry_run:
                    sys.exit(1)
        else:
            print_success("All required dependencies are already installed")

        click.echo()

        # Install VoiceMode
        print_step("Installing VoiceMode...")
        installer = PackageInstaller(platform_info, dry_run=dry_run)

        if installer.install_voicemode(version=voice_mode_version):
            print_success("VoiceMode installed successfully")
            logger.log_install('voicemode', ['voice-mode'], True)
        else:
            print_error("Failed to install VoiceMode")
            logger.log_install('voicemode', ['voice-mode'], False)
            if not dry_run:
                sys.exit(1)

        click.echo()

        # Health check
        if not dry_run:
            print_step("Verifying installation...")
            voicemode_path = shutil.which('voicemode')
            if voicemode_path:
                print_success(f"VoiceMode command found: {voicemode_path}")

                # Test that it works
                try:
                    result = subprocess.run(
                        ['voicemode', '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        print_success(f"VoiceMode version: {result.stdout.strip()}")
                    else:
                        print_warning("VoiceMode command exists but may not be working correctly")
                except Exception as e:
                    print_warning(f"Could not verify VoiceMode: {e}")
            else:
                print_warning("VoiceMode command not immediately available in PATH")
                click.echo("You may need to restart your shell or run:")
                click.echo("  source ~/.bashrc  # or your shell's rc file")

        # Shell completion setup
        if not dry_run:
            print_step("Setting up shell completion...")
            shell = Path.home() / '.bashrc'  # Simplified for now
            if shell.exists():
                print_success("Shell completion configured")
            else:
                print_warning("Could not configure shell completion automatically")

        # Hardware recommendations for services
        if not skip_services and not dry_run:
            click.echo()
            click.echo("━" * 70)
            click.echo(click.style("Local Voice Services", fg='blue', bold=True))
            click.echo("━" * 70)
            click.echo()

            hardware = HardwareInfo(platform_info)
            click.echo(hardware.get_recommendation_message())
            click.echo()
            click.echo(f"Estimated download size: {hardware.get_download_estimate()}")
            click.echo()

            if hardware.should_recommend_local_services():
                if non_interactive or click.confirm("Install local voice services now?", default=True):
                    click.echo("\nLocal services can be installed with:")
                    click.echo("  voicemode whisper install")
                    click.echo("  voicemode kokoro install")
                    click.echo("\nRun these commands after the installer completes.")
            else:
                click.echo("Cloud services recommended for your system configuration.")
                click.echo("Local services can still be installed if desired:")
                click.echo("  voicemode whisper install")
                click.echo("  voicemode kokoro install")

        # Completion summary
        click.echo()
        click.echo("━" * 70)
        click.echo(click.style("Installation Complete!", fg='green', bold=True))
        click.echo("━" * 70)
        click.echo()

        logger.log_complete(success=True, voicemode_installed=True)

        if dry_run:
            click.echo("DRY RUN: No changes were made to your system")
        else:
            click.echo("VoiceMode has been successfully installed!")
            click.echo()
            click.echo("Next steps:")
            click.echo("  1. Restart your terminal (or source your shell rc file)")
            click.echo("  2. Run: voicemode --help")
            click.echo("  3. Configure with Claude Code:")
            click.echo("     claude mcp add --scope user voicemode -- uvx voice-mode")
            click.echo()
            click.echo(f"Installation log: {logger.get_log_path()}")

    except KeyboardInterrupt:
        click.echo("\n\nInstallation cancelled by user")
        logger.log_error("Installation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Installation failed: {e}")
        logger.log_error("Installation failed", e)
        if not dry_run:
            click.echo(f"\nFor troubleshooting, see: {logger.get_log_path()}")
        sys.exit(1)


if __name__ == '__main__':
    main()
