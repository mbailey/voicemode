"""Agent management commands for VoiceMode.

Agents are Claude Code instances that can be controlled remotely.
The default agent is 'operator' - accessible from the iOS app and web interface.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

import click

# =============================================================================
# Agent Template Strings
# =============================================================================

# Base AGENT.md - Entry point for any AI
BASE_AGENT_MD = """Always load CLAUDE.md
"""

# Base CLAUDE.md - Claude-specific entry
BASE_CLAUDE_MD = """# VoiceMode Agent

Load @SKILL.md for instructions.
"""

# Base SKILL.md - Shared behavior for all agents
BASE_SKILL_MD = """# VoiceMode Agent

You are a VoiceMode agent - an AI assistant accessible via voice.

## Core Responsibilities
- Respond to voice conversations via the converse MCP tool
- Help users with their requests
- Remember context within the session

## Available Tools
- VoiceMode MCP provides voice conversation capabilities
- Use `converse` tool for speaking and listening

## Behavior
- Be conversational and natural
- Keep responses concise for voice
- Ask clarifying questions when needed
"""

# Base voicemode.env - Shared default settings
BASE_ENV = """# Base agent configuration
# VOICEMODE_VOICE=nova
# VOICEMODE_SPEED=1.0
"""

# Operator AGENT.md - Entry point
OPERATOR_AGENT_MD = """Always load CLAUDE.md
"""

# Operator CLAUDE.md - Claude entry
OPERATOR_CLAUDE_MD = """# VoiceMode Operator

Load @SKILL.md for operator instructions.
"""

# Operator SKILL.md - Operator-specific instructions
OPERATOR_SKILL_MD = """# Operator Agent

You are the VoiceMode Operator - the default agent woken by remote requests.

## On Wake
When activated via remote connection:
1. Greet the user warmly
2. Ask how you can help
3. Engage in voice conversation

## Your Role
Think of yourself like a phone operator - you're there to help when called.
"""

# Operator voicemode.env - Operator-specific settings
OPERATOR_ENV = """# Operator agent configuration
VOICEMODE_AGENT_REMOTE=true
# VOICEMODE_AGENT_STARTUP_MESSAGE=
# VOICEMODE_AGENT_CLAUDE_ARGS=
"""


# =============================================================================
# Helper Functions
# =============================================================================

def get_agents_base_dir() -> Path:
    """Get the base directory for all agents."""
    return Path.home() / '.voicemode' / 'agents'


def get_agent_names() -> list[str]:
    """Get list of available agent names for shell completion.

    Discovers agents from ~/.voicemode/agents/ directories.
    Always includes 'operator' as the default agent.

    Returns:
        List of agent names (directory names)
    """
    base = get_agents_base_dir()
    agents = ['operator']  # Always include operator

    if base.exists():
        for item in sorted(base.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                if item.name not in agents:
                    agents.append(item.name)

    return agents


def get_agent_dir(name: str) -> Path:
    """Get the home directory for a named agent.

    Args:
        name: Agent name

    Returns:
        Path to the agent's directory
    """
    return get_agents_base_dir() / name


def agent_name_completion(ctx, param, incomplete: str) -> list[str]:
    """Shell completion callback for agent names.

    Returns agent names that start with the incomplete string.
    """
    agents = get_agent_names()
    return [a for a in agents if a.startswith(incomplete)]


def init_agent_directory(name: str = 'operator') -> Path:
    """Create agent directory structure if it doesn't exist.

    Creates:
    - ~/.voicemode/agents/ base directory
    - Shared AGENT.md, CLAUDE.md, SKILL.md, voicemode.env in base
    - Agent-specific subdirectory with its own files

    Args:
        name: Agent name (default: 'operator')

    Returns:
        Path to the agent's directory
    """
    base = get_agents_base_dir()
    agent_dir = base / name

    # Create directories
    base.mkdir(parents=True, exist_ok=True)
    agent_dir.mkdir(exist_ok=True)

    # Create base files if they don't exist
    if not (base / 'AGENT.md').exists():
        (base / 'AGENT.md').write_text(BASE_AGENT_MD)

    if not (base / 'CLAUDE.md').exists():
        (base / 'CLAUDE.md').write_text(BASE_CLAUDE_MD)

    if not (base / 'SKILL.md').exists():
        (base / 'SKILL.md').write_text(BASE_SKILL_MD)

    if not (base / 'voicemode.env').exists():
        (base / 'voicemode.env').write_text(BASE_ENV)

    # Create agent-specific files based on agent name
    if name == 'operator':
        # Operator gets specific templates
        if not (agent_dir / 'AGENT.md').exists():
            (agent_dir / 'AGENT.md').write_text(OPERATOR_AGENT_MD)

        if not (agent_dir / 'CLAUDE.md').exists():
            (agent_dir / 'CLAUDE.md').write_text(OPERATOR_CLAUDE_MD)

        if not (agent_dir / 'SKILL.md').exists():
            (agent_dir / 'SKILL.md').write_text(OPERATOR_SKILL_MD)

        if not (agent_dir / 'voicemode.env').exists():
            (agent_dir / 'voicemode.env').write_text(OPERATOR_ENV)
    else:
        # Other agents get generic templates
        if not (agent_dir / 'AGENT.md').exists():
            (agent_dir / 'AGENT.md').write_text(BASE_AGENT_MD)

        if not (agent_dir / 'CLAUDE.md').exists():
            (agent_dir / 'CLAUDE.md').write_text(f"# VoiceMode Agent: {name}\n\nLoad @SKILL.md for instructions.\n")

        if not (agent_dir / 'SKILL.md').exists():
            (agent_dir / 'SKILL.md').write_text(BASE_SKILL_MD)

        if not (agent_dir / 'voicemode.env').exists():
            (agent_dir / 'voicemode.env').write_text(f"# {name} agent configuration\n")

    return agent_dir


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a voicemode.env file and return key-value pairs.

    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - KEY=value format
    - Quoted values
    """
    env = {}
    if not path.exists():
        return env

    for line in path.read_text().splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue

        # Parse KEY=value
        if '=' in line:
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes if present
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            env[key] = value

    return env


def load_agent_env(name: str) -> Dict[str, str]:
    """Load environment from base and agent-specific voicemode.env files.

    Loads in order (later overrides earlier):
    1. ~/.voicemode/agents/voicemode.env (base defaults)
    2. ~/.voicemode/agents/{name}/voicemode.env (agent-specific)

    Args:
        name: Agent name

    Returns:
        Merged environment dictionary
    """
    base = get_agents_base_dir()
    agent_dir = base / name

    env = {}

    # Load base config first
    base_env = base / 'voicemode.env'
    if base_env.exists():
        env.update(parse_env_file(base_env))

    # Override with agent-specific
    agent_env = agent_dir / 'voicemode.env'
    if agent_env.exists():
        env.update(parse_env_file(agent_env))

    return env


# =============================================================================
# Tmux Helper Functions
# =============================================================================

def tmux_session_exists(session: str) -> bool:
    """Check if a tmux session exists.

    Args:
        session: Name of the tmux session

    Returns:
        True if session exists, False otherwise
    """
    result = subprocess.run(
        ['tmux', 'has-session', '-t', session],
        capture_output=True
    )
    return result.returncode == 0


def tmux_window_exists(window: str) -> bool:
    """Check if a tmux window exists.

    Args:
        window: Window identifier in format 'session:window_name'

    Returns:
        True if window exists, False otherwise
    """
    if ':' not in window:
        return False

    session, name = window.split(':', 1)

    result = subprocess.run(
        ['tmux', 'list-windows', '-t', session, '-F', '#{window_name}'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False

    return name in result.stdout.splitlines()


def is_agent_running_in_pane(window: str, pane: int = 0) -> bool:
    """Check if an AI agent is running in a tmux pane.

    Uses pane_current_command to detect if something other than a shell
    is running. This is more reliable than checking pane content.

    Args:
        window: Window identifier in format 'session:window_name'
        pane: Pane index (default: 0)

    Returns:
        True if an agent appears to be running, False otherwise
    """
    target = f"{window}.{pane}"

    # Get the current command running in the pane
    result = subprocess.run(
        ['tmux', 'display-message', '-t', target, '-p', '#{pane_current_command}'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False

    current_command = result.stdout.strip()

    # If it's a shell, no agent is running
    # Common shells: bash, zsh, sh, fish, tcsh, csh, dash
    shell_names = {'bash', 'zsh', 'sh', 'fish', 'tcsh', 'csh', 'dash', '-bash', '-zsh', '-sh'}
    if current_command.lower() in shell_names:
        return False

    # If we got here, something other than a shell is running
    # This could be Claude Code (shows version like "2.1.25"), OpenCode, etc.
    return bool(current_command)


def build_claude_command(agent_dir: Path, initial_prompt: str | None = None, extra_args: str | None = None) -> str:
    """Build the Claude Code command to run.

    Args:
        agent_dir: Path to the agent's directory
        initial_prompt: Optional initial prompt to send to Claude
        extra_args: Optional extra arguments for Claude

    Returns:
        Command string to execute
    """
    cmd = f"cd {agent_dir} && claude --dangerously-skip-permissions"

    if extra_args:
        cmd = f"{cmd} {extra_args}"

    if initial_prompt:
        # Escape single quotes in the prompt and wrap in single quotes
        escaped = initial_prompt.replace("'", "'\"'\"'")
        cmd = f"{cmd} '{escaped}'"

    return cmd


# =============================================================================
# CLI Command Group
# =============================================================================

@click.group()
@click.help_option('-h', '--help')
def agent():
    """Manage VoiceMode agents.

    Agents are Claude Code instances that can be controlled remotely.
    The default agent is 'operator' - accessible from the iOS app.

    \b
    Commands:
      start   Start an agent
      stop    Stop an agent
      status  Show agent status
      send    Send a message to an agent
      list    List all agents and their status

    \b
    Quick Start:
      voicemode agent start            # Start operator (default)
      voicemode agent start research   # Start research agent
      voicemode agent list             # See all agents
      voicemode agent send "hello"     # Send to operator
      voicemode agent send -a research "help"  # Send to research
    """
    pass


@agent.command('init')
@click.argument('name', default='operator')
@click.help_option('-h', '--help')
def init_cmd(name: str):
    """Initialize agent directory structure.

    Creates the ~/.voicemode/agents/ directory with templates.
    This is automatically called by 'agent start', but can be
    run manually to set up the directory structure.

    NAME is the agent name (default: operator)
    """
    agent_dir = init_agent_directory(name)
    click.echo(f"✓ Initialized agent '{name}' at {agent_dir}")


@agent.command('start',
    context_settings={'help_option_names': ['-h', '--help']},
    epilog="""
\b
Examples:
  voicemode agent start             # Start operator (default)
  voicemode agent start research    # Start research agent
  voicemode agent start tesi        # Start tesi agent
  voicemode agent start -s vm       # Start in 'vm' session
  voicemode agent start -p "hello"  # Start with initial prompt
""")
@click.argument('agent_name', default='operator', required=False,
                shell_complete=agent_name_completion)
@click.option('-s', '--session', default='voicemode', help='Tmux session name')
@click.option('-p', '--prompt', help='Initial prompt to send to the agent')
def start(agent_name: str, session: str, prompt: str | None):
    """Start an agent.

    Starts a Claude Code instance in a tmux session. The agent runs
    in its directory (~/.voicemode/agents/<name>) and loads its
    CLAUDE.md configuration.

    This command is idempotent - if the agent is already running,
    it reports success without restarting.
    """
    window = f'{session}:{agent_name}'

    # 1. Initialize agent directory structure if needed
    agent_dir = init_agent_directory(agent_name)

    # 2. Load environment (for potential future use)
    load_agent_env(agent_name)

    # 3. Check/create tmux session
    if not tmux_session_exists(session):
        result = subprocess.run(
            ['tmux', 'new-session', '-d', '-s', session],
            capture_output=True
        )
        if result.returncode != 0:
            click.echo(f"Error: Failed to create tmux session '{session}'", err=True)
            raise SystemExit(1)
        click.echo(f"Created tmux session '{session}'")

    # 4. Check/create window for agent
    if not tmux_window_exists(window):
        result = subprocess.run(
            ['tmux', 'new-window', '-t', session, '-n', agent_name],
            capture_output=True
        )
        if result.returncode != 0:
            click.echo(f"Error: Failed to create tmux window '{agent_name}'", err=True)
            raise SystemExit(1)
        click.echo(f"Created tmux window '{agent_name}'")

    # 5. Check if Claude Code is already running
    if is_agent_running_in_pane(window):
        click.echo(f"✓ Agent '{agent_name}' already running in tmux session '{session}'")
        return

    # 6. Start Claude Code
    claude_cmd = build_claude_command(agent_dir, initial_prompt=prompt)

    result = subprocess.run(
        ['tmux', 'send-keys', '-t', window, claude_cmd, 'Enter'],
        capture_output=True
    )

    if result.returncode != 0:
        click.echo("Error: Failed to start Claude Code", err=True)
        raise SystemExit(1)

    click.echo(f"✓ Agent '{agent_name}' started in tmux session '{session}'")


@agent.command('status',
    context_settings={'help_option_names': ['-h', '--help']},
    epilog="""
\b
Status values:
  running  - Claude Code is active in the agent window
  stopped  - Agent is not running (various reasons shown)

Examples:
  voicemode agent status             # Check operator (default)
  voicemode agent status research    # Check research agent
  voicemode agent status -s vm       # Check 'vm' session
""")
@click.argument('agent_name', default='operator', required=False,
                shell_complete=agent_name_completion)
@click.option('-s', '--session', default='voicemode', help='Tmux session name')
def status(agent_name: str, session: str):
    """Show agent status.

    Checks the tmux session, window, and Claude Code process status.
    """
    window = f'{session}:{agent_name}'

    # Check if session exists
    if not tmux_session_exists(session):
        click.echo(f"stopped - no tmux session '{session}'")
        return

    # Check if window exists
    if not tmux_window_exists(window):
        click.echo(f"stopped - no '{agent_name}' window in session '{session}'")
        return

    # Check if Claude Code is running
    if is_agent_running_in_pane(window):
        click.echo("running")
    else:
        click.echo("stopped - Claude not running in window")


@agent.command('stop',
    context_settings={'help_option_names': ['-h', '--help']},
    epilog="""
\b
Examples:
  voicemode agent stop             # Stop operator (default)
  voicemode agent stop research    # Stop research agent
  voicemode agent stop --kill      # Kill the tmux window
  voicemode agent stop -s vm       # Stop agent in 'vm' session
""")
@click.argument('agent_name', default='operator', required=False,
                shell_complete=agent_name_completion)
@click.option('-s', '--session', default='voicemode', help='Tmux session name')
@click.option('--kill', is_flag=True, help='Kill the tmux window instead of just stopping Claude')
def stop(agent_name: str, session: str, kill: bool):
    """Stop an agent.

    Sends Ctrl-C to gracefully stop Claude Code. Use --kill to
    remove the entire tmux window.
    """
    window = f'{session}:{agent_name}'

    # Check if window exists
    if not tmux_window_exists(window):
        click.echo(f"Agent '{agent_name}' not running (no window in session '{session}')")
        return

    if kill:
        # Kill the whole window
        result = subprocess.run(
            ['tmux', 'kill-window', '-t', window],
            capture_output=True
        )
        if result.returncode != 0:
            click.echo(f"Error: Failed to kill window '{window}'", err=True)
            raise SystemExit(1)
        click.echo(f"✓ Agent '{agent_name}' window killed")
    else:
        # Send multiple Ctrl-C signals to stop Claude gracefully
        # Claude Code often needs 2-3 Ctrl-C signals to fully stop
        for i in range(3):
            result = subprocess.run(
                ['tmux', 'send-keys', '-t', window, 'C-c'],
                capture_output=True
            )
            if result.returncode != 0:
                click.echo(f"Error: Failed to send stop signal", err=True)
                raise SystemExit(1)
            if i < 2:  # Don't sleep after the last signal
                time.sleep(0.3)
        click.echo(f"✓ Sent stop signal to agent '{agent_name}'")


def escape_for_tmux(message: str) -> str:
    """Escape a message for safe transmission via tmux send-keys.

    Args:
        message: The message to escape

    Returns:
        Escaped message safe for tmux
    """
    # tmux send-keys -l (literal) handles most escaping, but we use it
    # by default. For messages without special characters, no escaping needed.
    # The -l flag tells tmux to interpret the string literally.
    return message


def is_agent_running(agent_name: str = 'operator', session: str = 'voicemode') -> bool:
    """Check if an agent is running.

    Args:
        agent_name: Name of the agent to check
        session: Tmux session name

    Returns:
        True if agent is running in the session
    """
    window = f'{session}:{agent_name}'
    return tmux_window_exists(window) and is_agent_running_in_pane(window)


# Keep is_operator_running for backwards compatibility
def is_operator_running(session: str = 'voicemode') -> bool:
    """Check if the operator agent is running (backwards compatible).

    Args:
        session: Tmux session name

    Returns:
        True if operator is running in the session
    """
    return is_agent_running('operator', session)


@agent.command('send',
    context_settings={'help_option_names': ['-h', '--help']},
    epilog="""
\b
Examples:
  voicemode agent send "Hello, how can I help?"
  voicemode agent send --agent research "Help with paper"
  voicemode agent send -a tesi "Quick question"
  voicemode agent send --no-start "Quick question"
  voicemode agent send  # Prompts for message
""")
@click.argument('message', required=False)
@click.option('--agent', '-a', 'agent_name', default='operator',
              shell_complete=agent_name_completion,
              help='Agent name (default: operator)')
@click.option('-s', '--session', default='voicemode', help='Tmux session name')
@click.option('--no-start', is_flag=True, help='Fail if agent not running instead of auto-starting')
@click.pass_context
def send(ctx, message: str | None, agent_name: str, session: str, no_start: bool):
    """Send a message to an agent.

    Sends a message to the agent in the tmux session. By default,
    if the agent is not running, it will be started automatically.

    Use --no-start to fail if the agent is not running instead of
    auto-starting it.
    """
    window = f'{session}:{agent_name}'
    target = f'{window}.0'  # Always target pane 0 where the agent runs

    # Get message first (needed before potential auto-start)
    if not message:
        message = click.prompt("Message")

    # Check if agent is running
    running = is_agent_running(agent_name, session)

    if not running:
        if no_start:
            click.echo(f"Error: Agent '{agent_name}' not running (use 'voicemode agent start --agent {agent_name}')", err=True)
            sys.exit(1)
        else:
            # Auto-start the agent with the message as initial prompt
            # This passes the message directly to claude command, avoiding timing issues
            click.echo(f"Starting agent '{agent_name}' with message...")
            ctx.invoke(start, agent_name=agent_name, session=session, prompt=message)

            # Truncate message for display if too long
            display_msg = message[:50] + '...' if len(message) > 50 else message
            click.echo(f"✓ Started with: {display_msg}")
            return

    # Agent is already running - send message via tmux
    # Send message to pane 0 using -l for literal interpretation
    result = subprocess.run(
        ['tmux', 'send-keys', '-t', target, '-l', message],
        capture_output=True
    )

    if result.returncode != 0:
        click.echo("Error: Failed to send message", err=True)
        sys.exit(1)

    # Send Enter key separately
    result = subprocess.run(
        ['tmux', 'send-keys', '-t', target, 'Enter'],
        capture_output=True
    )

    if result.returncode != 0:
        click.echo("Error: Failed to send Enter key", err=True)
        sys.exit(1)

    # Truncate message for display if too long
    display_msg = message[:50] + '...' if len(message) > 50 else message
    click.echo(f"✓ Sent to '{agent_name}': {display_msg}")


def list_agents() -> list[dict]:
    """List all agent directories and their running status.

    Returns:
        List of dicts with 'name' and 'status' keys
    """
    base = get_agents_base_dir()
    agents = []

    if not base.exists():
        return agents

    for item in sorted(base.iterdir()):
        if item.is_dir() and not item.name.startswith('.'):
            # Check running status in default session
            window = f'voicemode:{item.name}'
            if tmux_window_exists(window) and is_agent_running_in_pane(window):
                status = 'running'
            else:
                status = 'stopped'

            agents.append({'name': item.name, 'status': status})

    return agents


def scan_tmux_for_agents() -> list[dict]:
    """Scan all tmux panes for running AI agents.

    Returns a list of dicts with pane info for any pane that appears
    to be running an AI agent (not a shell).

    Returns:
        List of dicts with keys: pane_id, session, window, pane_index,
                                 command, title, path
    """
    result = subprocess.run(
        ['tmux', 'list-panes', '-a', '-F',
         '#{pane_id}\t#{session_name}\t#{window_name}\t#{pane_index}\t'
         '#{pane_current_command}\t#{pane_title}\t#{pane_current_path}'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return []

    agents = []
    shell_names = {'bash', 'zsh', 'sh', 'fish', 'tcsh', 'csh', 'dash',
                   '-bash', '-zsh', '-sh'}

    for line in result.stdout.strip().splitlines():
        parts = line.split('\t')
        if len(parts) >= 7:
            pane_id, session, window, pane_idx, command, title, path = parts[:7]

            # Skip shells - they're not agents
            if command.lower() in shell_names:
                continue

            # Skip common non-agent processes
            skip_commands = {'nvim', 'vim', 'nano', 'less', 'more', 'man',
                             'htop', 'top', 'watch', 'tail', 'ssh'}
            if command.lower() in skip_commands:
                continue

            agents.append({
                'pane_id': pane_id,
                'session': session,
                'window': window,
                'pane_index': pane_idx,
                'command': command,
                'title': title,
                'path': path
            })

    return agents


@agent.command('list')
@click.option('--all', 'show_all', is_flag=True,
              help='Show all agent-like processes in tmux')
@click.help_option('-h', '--help')
def list_cmd(show_all: bool):
    """List all agents and their status.

    Without --all: Shows configured VoiceMode agents and their status.
    With --all: Scans all tmux sessions for running AI agents.

    \b
    Examples:
      voicemode agent list        # List configured agents
      voicemode agent list --all  # List all agent-like processes in tmux
    """
    import sys

    base = get_agents_base_dir()
    is_tty = sys.stdout.isatty()

    if show_all:
        # Scan tmux for all agent-like processes
        running_agents = scan_tmux_for_agents()

        if not running_agents:
            click.echo("No running agents found in tmux")
            return

        # Get list of managed agent names
        managed_names = set()
        if base.exists():
            for item in base.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    managed_names.add(item.name)

        if is_tty:
            # Calculate column widths dynamically
            max_id = max(len(a['pane_id']) for a in running_agents)
            max_loc = max(len(f"{a['session']}:{a['window']}.{a['pane_index']}")
                          for a in running_agents)
            max_cmd = max(len(a['command'][:10]) for a in running_agents)
            max_title = min(30, max(len(a['title'][:30]) for a in running_agents))

            # Build format string
            header = (f"{'ID'.rjust(max_id)}  {'Location'.ljust(max_loc)}  "
                      f"{'Command'.ljust(max_cmd)}  {'Title'.ljust(max_title)}  Managed")
            separator = (f"{'-' * max_id}  {'-' * max_loc}  "
                        f"{'-' * max_cmd}  {'-' * max_title}  -------")

            click.echo(header)
            click.echo(separator)
            for a in running_agents:
                pane_id = a['pane_id'].rjust(max_id)
                location = f"{a['session']}:{a['window']}.{a['pane_index']}".ljust(max_loc)
                cmd = a['command'][:10].ljust(max_cmd)
                title = a['title'][:30].ljust(max_title)
                managed = "yes" if a['window'] in managed_names else "no"
                click.echo(f"{pane_id}  {location}  {cmd}  {title}  {managed}")
        else:
            # Machine-readable: tab-separated values
            for a in running_agents:
                managed = "managed" if a['window'] in managed_names else "unmanaged"
                click.echo(f"{a['pane_id']}\t{a['session']}:{a['window']}.{a['pane_index']}\t"
                          f"{a['command']}\t{a['title']}\t{managed}")
    else:
        # Original behavior: show configured agents
        if not base.exists():
            click.echo("No agents configured (run 'voicemode agent start' first)")
            return

        agents = []
        for item in sorted(base.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                # Check running status in default voicemode session
                window = f'voicemode:{item.name}'
                if tmux_window_exists(window) and is_agent_running_in_pane(window):
                    status = 'running'
                else:
                    status = 'stopped'

                agents.append({'name': item.name, 'status': status})

        if not agents:
            click.echo("No agents configured (run 'voicemode agent start' first)")
            return

        if is_tty:
            # Pretty table format
            click.echo("Agent       Status")
            click.echo("----------  -------")
            for agent_info in agents:
                name = agent_info['name'].ljust(10)
                status = agent_info['status']
                click.echo(f"{name}  {status}")
        else:
            # Machine-readable
            for agent_info in agents:
                click.echo(f"{agent_info['name']}\t{agent_info['status']}")
