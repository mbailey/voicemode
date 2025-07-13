"""
CLI entry points for voice-mode package.
"""
import sys
import click
from .server import main as voice_mode_main

def voice_mode() -> None:
    """Entry point for voicemode command - starts the MCP server."""
    voice_mode_main()


# New Click-based CLI
@click.group()
@click.version_option()
@click.help_option('-h', '--help')
def cli():
    """Voice Mode CLI - Manage conversations, view logs, and analyze voice interactions."""
    pass


# Import subcommand groups
from voice_mode.cli_commands import exchanges as exchanges_cmd

# Add subcommands
cli.add_command(exchanges_cmd.exchanges)


