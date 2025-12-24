"""Main CLI for VoiceMode installer."""

import json
import os
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
from .system import detect_platform, get_system_info, check_command_exists, check_homebrew_installed


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
    ║            VoiceMode Installer             ║
    ║                                            ║
    ╚════════════════════════════════════════════╝
"""


def print_logo():
    """Display the VoiceMode logo in Claude Code orange."""
    # Use ANSI 256-color code 208 (dark orange) which matches Claude Code orange (RGB 208, 128, 0)
    # This works on xterm-256color and other 256-color terminals
    click.echo('\033[38;5;208m' + '\033[1m' + LOGO + '\033[0m')


def print_step(message: str):
    """Print a step message."""
    click.echo(click.style(f"🔧 {message}", fg='blue'))


def print_success(message: str):
    """Print a success message."""
    click.echo(click.style(f"✅ {message}", fg='green'))


def print_warning(message: str):
    """Print a warning message in Claude Code orange."""
    # Use ANSI 256-color code 208 (dark orange)
    click.echo('\033[38;5;208m' + f"⚠️  {message}" + '\033[0m')


def print_error(message: str):
    """Print an error message."""
    click.echo(click.style(f"❌ {message}", fg='red'))


def get_installed_version() -> str | None:
    """Get the currently installed VoiceMode version."""
    try:
        result = subprocess.run(
            ['voicemode', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Output is like "VoiceMode version 6.0.1" or just "6.0.1"
            version = result.stdout.strip().split()[-1]
            return version
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_latest_version() -> str | None:
    """Get the latest VoiceMode version from PyPI."""
    try:
        # Use PyPI JSON API to get latest version
        result = subprocess.run(
            ['curl', '-s', 'https://pypi.org/pypi/voice-mode/json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data['info']['version']
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        pass
    return None


def check_existing_installation() -> bool:
    """Check if VoiceMode is already installed."""
    return check_command_exists('voicemode')


def ensure_homebrew_on_macos(platform_info, dry_run: bool, non_interactive: bool) -> bool:
    """
    Ensure Homebrew is installed on macOS before checking dependencies.

    Returns True if Homebrew is available or successfully installed, False otherwise.
    """
    # Only needed on macOS
    if platform_info.distribution != 'darwin':
        return True

    # Check if already installed
    if check_homebrew_installed():
        return True

    # Not installed
    print_warning("Homebrew is not installed")
    click.echo("Homebrew is the package manager required to install system dependencies on macOS.")
    click.echo("Visit: https://brew.sh")
    click.echo()

    if dry_run:
        print_step("[DRY RUN] Would install Homebrew (macOS package manager)")
        return True

    if non_interactive:
        # Auto-install Homebrew in non-interactive mode using NONINTERACTIVE=1
        print_step("Installing Homebrew (non-interactive)...")
    else:
        # Prompt user
        if not click.confirm("Install Homebrew now?", default=True):
            print_error("Homebrew installation declined")
            click.echo("Please install Homebrew manually and run the installer again.")
            return False
        print_step("Installing Homebrew...")
        click.echo("This may take a few minutes and will require your password.")

    click.echo()

    try:
        # Use NONINTERACTIVE=1 for unattended installation
        env = os.environ.copy()
        if non_interactive:
            env['NONINTERACTIVE'] = '1'
        install_script = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        result = subprocess.run(install_script, shell=True, check=True, env=env)

        if result.returncode == 0:
            print_success("Homebrew installed successfully")

            # Verify
            if check_homebrew_installed():
                return True
            else:
                print_warning("Homebrew was installed but 'brew' command not found in PATH")
                click.echo("You may need to add Homebrew to your PATH. Check the installation output above.")
                return False
        else:
            print_error("Homebrew installation returned non-zero exit code")
            return False

    except subprocess.CalledProcessError as e:
        print_error(f"Error installing Homebrew: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error installing Homebrew: {e}")
        return False


EPILOG = """
\b
Examples:
  # Normal installation
  voice-mode-install

  # Non-interactive installation (auto-accept all prompts)
  voice-mode-install --yes
  voice-mode-install -y

  # Dry run (see what would be installed)
  voice-mode-install --dry-run

  # Install specific version
  voice-mode-install --voice-mode-version=5.1.3

  # Skip service installation
  voice-mode-install --skip-services

  # Install with specific Whisper model
  voice-mode-install --yes --model large-v2
"""


@click.command(epilog=EPILOG, context_settings={'help_option_names': ['-h', '--help']})
@click.option('-d', '--dry-run', is_flag=True, help='Show what would be installed without installing')
@click.option('-v', '--voice-mode-version', default=None, help='Specific VoiceMode version to install')
@click.option('-s', '--skip-services', is_flag=True, help='Skip local service installation')
@click.option('-y', '--yes', 'non_interactive', is_flag=True, help='Run without prompts (auto-accept all)')
@click.option('-n', '--non-interactive', is_flag=True, help='Run without prompts (deprecated: use --yes/-y)')
@click.option('-m', '--model', default='base', help='Whisper model to use (base, small, medium, large-v2)')
@click.version_option(__version__, '-V', '--version')
def main(dry_run, voice_mode_version, skip_services, non_interactive, model):
    """VoiceMode Installer - Install VoiceMode and its system dependencies.

    This installer will:

      1. Detect your operating system and architecture

      2. Check for missing system dependencies

      3. Install required packages (with your permission)

      4. Install VoiceMode using uv

      5. Optionally install local voice services

      6. Configure shell completions

      7. Verify the installation
    """
    # Detect non-interactive environment (no TTY)
    if not sys.stdin.isatty() and not non_interactive and not dry_run:
        click.echo("Error: Running in non-interactive environment without --yes flag", err=True)
        click.echo("Use --yes or -y to enable automatic installation", err=True)
        click.echo("Example: uvx voice-mode-install --yes", err=True)
        sys.exit(1)

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

        # Ensure Homebrew is installed on macOS (before checking dependencies)
        if not ensure_homebrew_on_macos(platform_info, dry_run, non_interactive):
            logger.log_error("Homebrew installation required but not available")
            sys.exit(1)

        # Check for existing installation
        if check_existing_installation():
            installed_version = get_installed_version()
            latest_version = get_latest_version()

            click.echo(click.style("✓ VoiceMode is currently installed", fg='green'))

            if installed_version:
                click.echo(f"  Installed version: {installed_version}")
            else:
                click.echo("  Installed version: (unable to detect)")

            if latest_version:
                click.echo(f"  Latest version:    {latest_version}")

                # Check if update is available
                if installed_version and latest_version and installed_version != latest_version:
                    click.echo()
                    if non_interactive:
                        print_step("Upgrading VoiceMode...")
                    elif not click.confirm(f"Upgrade to version {latest_version}?", default=True):
                        click.echo("\nTo upgrade manually later, run: uv tool install --upgrade voice-mode")
                        sys.exit(0)
                elif installed_version and latest_version and installed_version == latest_version:
                    click.echo()
                    click.echo(click.style("✓ VoiceMode is up-to-date", fg='green'))
                    if non_interactive:
                        click.echo("Reinstalling...")
                    elif not click.confirm("Reinstall anyway?", default=False):
                        click.echo("\nInstallation cancelled.")
                        sys.exit(0)
                else:
                    click.echo()
                    if not non_interactive:
                        if not click.confirm("Reinstall VoiceMode?", default=False):
                            click.echo("\nTo upgrade manually, run: uv tool install --upgrade voice-mode")
                            sys.exit(0)
            else:
                click.echo("  Latest version:    (unable to check)")
                click.echo()
                if not non_interactive:
                    if not click.confirm("Reinstall/upgrade VoiceMode?", default=False):
                        click.echo("\nTo upgrade manually, run: uv tool install --upgrade voice-mode")
                        sys.exit(0)

            click.echo()

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

            installer = PackageInstaller(platform_info, dry_run=dry_run, non_interactive=non_interactive)
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
        installer = PackageInstaller(platform_info, dry_run=dry_run, non_interactive=non_interactive)

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
                    model_flag = f" --model {model}" if model != 'base' else ''
                    click.echo("\nLocal services can be installed with:")
                    click.echo(f"  voicemode whisper install{model_flag}")
                    click.echo("  voicemode kokoro install")
                    click.echo("\nRun these commands after the installer completes.")
                    if non_interactive:
                        click.echo(f"\nNote: Whisper model '{model}' will be used (set via --model flag)")
            else:
                click.echo("Cloud services recommended for your system configuration.")
                click.echo("Local services can still be installed if desired:")
                model_flag = f" --model {model}" if model != 'base' else ''
                click.echo(f"  voicemode whisper install{model_flag}")
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
