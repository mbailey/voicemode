"""CLI commands for soundfonts toggle.

Provides `voicemode soundfonts on/off/status` commands
for enabling/disabling soundfont playback during Claude Code sessions.

Soundfonts are enabled by default. Disabling creates a sentinel file
at ~/.voicemode/soundfonts-disabled which the hook receiver checks
before playing any sounds.
"""

from pathlib import Path

import click


SENTINEL_FILE = Path.home() / '.voicemode' / 'soundfonts-disabled'


@click.group(name='soundfonts')
@click.help_option('-h', '--help', help='Show this message and exit')
def soundfonts():
    """Toggle soundfont playback for Claude Code hooks.

    Soundfonts provide audio feedback during Claude Code sessions.
    They require Claude Code hooks to be installed first:

        voicemode claude hooks add

    By default, soundfonts are enabled. Use 'off' to disable
    and 'on' to re-enable.

    Examples:
        voicemode soundfonts status
        voicemode soundfonts off
        voicemode soundfonts on
    """
    pass


@soundfonts.command('on')
def soundfonts_on():
    """Enable soundfont playback (default).

    Removes the sentinel file so the hook receiver plays sounds.
    """
    if SENTINEL_FILE.exists():
        SENTINEL_FILE.unlink()
        click.echo("Soundfonts enabled.")
    else:
        click.echo("Soundfonts are already enabled.")


@soundfonts.command('off')
def soundfonts_off():
    """Disable soundfont playback.

    Creates a sentinel file that the hook receiver checks
    before playing any sounds.
    """
    if SENTINEL_FILE.exists():
        click.echo("Soundfonts are already disabled.")
    else:
        SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_FILE.touch()
        click.echo("Soundfonts disabled.")


@soundfonts.command('status')
def soundfonts_status():
    """Show whether soundfonts are enabled or disabled."""
    if SENTINEL_FILE.exists():
        click.echo("Soundfonts: disabled")
        click.echo(f"  Sentinel file: {SENTINEL_FILE}")
    else:
        click.echo("Soundfonts: enabled")
    click.echo()
    click.echo("Tip: Soundfonts require Claude Code hooks:")
    click.echo("  voicemode claude hooks add")
