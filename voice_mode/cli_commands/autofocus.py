"""CLI commands for tmux autofocus toggle.

Provides `voicemode autofocus on/off/status` commands for enabling
and disabling auto-focus of the agent's tmux pane on converse.

Two mechanisms control auto-focus:
1. Sentinel file (~/.voicemode/autofocus-disabled) — quick toggle / circuit breaker
2. Env var (VOICEMODE_AUTO_FOCUS_PANE) — persistent config in voicemode.env

The sentinel file forces-disable when present, regardless of the env var.
When the sentinel is absent, the env var decides. Default (neither set) is
disabled (consistent with VOICEMODE_AUTO_FOCUS_PANE defaulting to false in
voice_mode/config.py).

Mirrors the soundfonts toggle pattern (voice_mode/cli_commands/soundfonts.py)
so users have one mental model for "quick toggle" feature switches.
"""

import os
from pathlib import Path

import click


SENTINEL_FILE = Path.home() / '.voicemode' / 'autofocus-disabled'
VOICEMODE_ENV_FILE = Path.home() / '.voicemode' / 'voicemode.env'


def is_autofocus_disabled_by_sentinel() -> bool:
    """Return True if the quick-toggle sentinel file exists.

    Called from focus_tmux_pane() in voice_mode/tools/converse.py to
    short-circuit auto-focus regardless of VOICEMODE_AUTO_FOCUS_PANE.
    """
    return SENTINEL_FILE.exists()


def _get_env_var_state() -> tuple:
    """Check VOICEMODE_AUTO_FOCUS_PANE from config file and env.

    Returns:
        (enabled: bool | None, source: str | None)
        source is 'file' (voicemode.env), 'env' (shell only), or None (not set)
    """
    # Check voicemode.env file first — more actionable source
    file_val = None
    if VOICEMODE_ENV_FILE.exists():
        for line in VOICEMODE_ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if stripped.startswith('VOICEMODE_AUTO_FOCUS_PANE='):
                val = stripped.split('=', 1)[1].strip().strip('"').strip("'")
                file_val = val.lower() in ('true', '1', 'yes', 'on')
                break

    # Check shell environment
    env_val = os.environ.get('VOICEMODE_AUTO_FOCUS_PANE')

    if file_val is not None:
        # File value exists — report it as the source
        return file_val, 'file'

    if env_val is not None:
        # Only in shell env (not from our file) — less common
        return env_val.lower() in ('true', '1', 'yes', 'on'), 'env'

    # Not set anywhere — default is false
    return None, None


def _update_env_file(enabled: bool) -> None:
    """Update VOICEMODE_AUTO_FOCUS_PANE in ~/.voicemode/voicemode.env.

    Also syncs os.environ so the current process sees the new value
    (voicemode's config.py loads voicemode.env into os.environ at startup,
    which can leave stale values if we only update the file).
    """
    value = 'true' if enabled else 'false'
    os.environ['VOICEMODE_AUTO_FOCUS_PANE'] = value
    env_file = VOICEMODE_ENV_FILE

    if not env_file.exists():
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(f'VOICEMODE_AUTO_FOCUS_PANE={value}\n')
        return

    lines = env_file.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if stripped.startswith('VOICEMODE_AUTO_FOCUS_PANE='):
            lines[i] = f'VOICEMODE_AUTO_FOCUS_PANE={value}'
            found = True
            break

    if not found:
        lines.append(f'VOICEMODE_AUTO_FOCUS_PANE={value}')

    env_file.write_text('\n'.join(lines) + '\n')


def _hint_env_var_off() -> None:
    """Print a hint if the env var would keep autofocus off after removing sentinel."""
    enabled, source = _get_env_var_state()
    if enabled is not True:
        click.echo()
        click.echo("Note: VOICEMODE_AUTO_FOCUS_PANE is not set to true.")
        if source == 'file':
            click.echo(f"  Currently: false in {VOICEMODE_ENV_FILE}")
        elif source == 'env':
            click.echo("  Currently: false in shell environment")
        else:
            click.echo("  Currently: unset (default is false)")
        click.echo("  Auto-focus will only run when VOICEMODE_AUTO_FOCUS_PANE=true.")
        click.echo("  Persist with: voicemode autofocus on --config")


@click.group(name='autofocus')
@click.help_option('-h', '--help', help='Show this message and exit')
def autofocus():
    """Toggle tmux auto-focus on converse.

    When auto-focus is enabled, voicemode brings the agent's tmux pane into
    view as it speaks (without stealing your active pane). Useful in multi-
    agent setups where you want to see who's talking.

    Quick toggle (session-scoped via sentinel file):
        voicemode autofocus off        # Disable immediately
        voicemode autofocus on         # Remove sentinel

    Persistent config change (~/.voicemode/voicemode.env):
        voicemode autofocus on --config    # Enable + update voicemode.env
        voicemode autofocus off --config   # Disable + update voicemode.env
    """
    pass


@autofocus.command('on')
@click.option('--config', is_flag=True,
              help='Also update VOICEMODE_AUTO_FOCUS_PANE in voicemode.env')
def autofocus_on(config):
    """Enable tmux auto-focus.

    Removes the quick-toggle sentinel file. Use --config to also
    set VOICEMODE_AUTO_FOCUS_PANE=true in ~/.voicemode/voicemode.env
    for persistent enablement (the underlying feature is off by
    default, so without --config you may also need to set the env
    var manually).
    """
    had_sentinel = SENTINEL_FILE.exists()

    if had_sentinel:
        SENTINEL_FILE.unlink()

    if config:
        env_enabled, _ = _get_env_var_state()
        config_changed = env_enabled is not True  # None (unset) or False
        if config_changed:
            _update_env_file(True)

        if had_sentinel and config_changed:
            click.echo("Auto-focus enabled.")
            click.echo("  Removed sentinel file.")
            click.echo(f"  Updated {VOICEMODE_ENV_FILE}: VOICEMODE_AUTO_FOCUS_PANE=true")
        elif had_sentinel:
            click.echo("Auto-focus enabled.")
            click.echo("  Removed sentinel file.")
        elif config_changed:
            click.echo("Auto-focus enabled.")
            click.echo(f"  Updated {VOICEMODE_ENV_FILE}: VOICEMODE_AUTO_FOCUS_PANE=true")
        else:
            click.echo("Auto-focus is already enabled.")
            return

    elif had_sentinel:
        click.echo("Auto-focus enabled.")
        _hint_env_var_off()
    else:
        env_enabled, _ = _get_env_var_state()
        if env_enabled is True:
            click.echo("Auto-focus is already enabled.")
        else:
            click.echo("Auto-focus is already enabled (no quick toggle active).")
            _hint_env_var_off()


@autofocus.command('off')
@click.option('--config', is_flag=True,
              help='Also update VOICEMODE_AUTO_FOCUS_PANE in voicemode.env')
def autofocus_off(config):
    """Disable tmux auto-focus.

    Creates a sentinel file that converse.py checks before focusing
    the tmux pane. Use --config to also set VOICEMODE_AUTO_FOCUS_PANE=false
    in ~/.voicemode/voicemode.env for persistent disablement.
    """
    had_sentinel = SENTINEL_FILE.exists()

    if not had_sentinel:
        SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_FILE.touch()

    if config:
        env_enabled, _ = _get_env_var_state()
        config_changed = env_enabled is not False  # None (unset) or True
        if config_changed:
            _update_env_file(False)

        if had_sentinel and config_changed:
            click.echo("Auto-focus disabled.")
            click.echo(f"  Updated {VOICEMODE_ENV_FILE}: VOICEMODE_AUTO_FOCUS_PANE=false")
        elif had_sentinel:
            click.echo("Auto-focus is already disabled.")
        elif config_changed:
            click.echo("Auto-focus disabled.")
            click.echo(f"  Updated {VOICEMODE_ENV_FILE}: VOICEMODE_AUTO_FOCUS_PANE=false")
        else:
            click.echo("Auto-focus is already disabled.")
    elif had_sentinel:
        click.echo("Auto-focus is already disabled.")
    else:
        click.echo("Auto-focus disabled (this session).")
        click.echo("  Re-enable with: voicemode autofocus on")


@autofocus.command('status')
def autofocus_status():
    """Show whether tmux auto-focus is enabled or disabled.

    Checks both the quick-toggle sentinel file and the
    VOICEMODE_AUTO_FOCUS_PANE configuration.
    """
    sentinel_exists = SENTINEL_FILE.exists()
    env_enabled, env_source = _get_env_var_state()

    if sentinel_exists:
        # Sentinel forces off regardless of env var
        click.echo("Auto-focus: disabled (quick toggle)")
        click.echo(f"  Sentinel file: {SENTINEL_FILE}")
        if env_enabled is True:
            click.echo("  Note: VOICEMODE_AUTO_FOCUS_PANE=true is being overridden by the sentinel.")
        click.echo("  Re-enable with: voicemode autofocus on")
    elif env_enabled is True:
        click.echo("Auto-focus: enabled")
        if env_source == 'file':
            click.echo(f"  VOICEMODE_AUTO_FOCUS_PANE=true in {VOICEMODE_ENV_FILE}")
        else:
            click.echo("  VOICEMODE_AUTO_FOCUS_PANE=true in shell environment")
    elif env_enabled is False:
        click.echo("Auto-focus: disabled (by config)")
        if env_source == 'file':
            click.echo(f"  VOICEMODE_AUTO_FOCUS_PANE=false in {VOICEMODE_ENV_FILE}")
        else:
            click.echo("  VOICEMODE_AUTO_FOCUS_PANE=false in shell environment")
        click.echo("  Enable with: voicemode autofocus on --config")
    else:
        # Not set anywhere — feature defaults off
        click.echo("Auto-focus: disabled (default)")
        click.echo("  VOICEMODE_AUTO_FOCUS_PANE is unset (default is false).")
        click.echo("  Enable with: voicemode autofocus on --config")
