"""Agent management commands for VoiceMode.

Agents are Claude Code instances that can be controlled remotely.
The default agent is 'operator' - accessible from the iOS app and web interface.
"""

import subprocess
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


def is_claude_running_in_pane(window: str) -> bool:
    """Check if Claude Code appears to be running in a tmux pane.

    Examines the pane content for Claude Code indicators.

    Args:
        window: Window identifier in format 'session:window_name'

    Returns:
        True if Claude Code appears to be running, False otherwise
    """
    # Capture recent pane content
    result = subprocess.run(
        ['tmux', 'capture-pane', '-t', window, '-p', '-S', '-20'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False

    content = result.stdout

    # Look for Claude Code indicators:
    # - "Claude" in the output (startup message, prompts)
    # - The prompt pattern "> " or "claude>"
    # - "claude code" text
    if 'Claude' in content or 'claude' in content.lower():
        return True

    # Also check for the prompt pattern with some content
    if '> ' in content and len(content.strip()) > 10:
        return True

    return False


def build_claude_command(agent_dir: Path, extra_args: str | None = None) -> str:
    """Build the Claude Code command to run.

    Args:
        agent_dir: Path to the agent's directory
        extra_args: Optional extra arguments for Claude

    Returns:
        Command string to execute
    """
    cmd = f"cd {agent_dir} && claude --dangerously-skip-permissions"

    if extra_args:
        cmd = f"{cmd} {extra_args}"

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
      start   Start the operator agent
      stop    Stop the operator agent
      status  Show operator status
      send    Send a message to the operator

    \b
    Quick Start:
      voicemode agent start     # Start operator in tmux
      voicemode agent send "hello"  # Send a message
      voicemode agent stop      # Stop the agent
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


@agent.command('start')
@click.option('--session', default='voicemode', help='Tmux session name')
@click.help_option('-h', '--help')
def start(session: str):
    """Start the operator agent.

    Starts a Claude Code instance in a tmux session. The agent runs
    in the operator directory (~/.voicemode/agents/operator) and
    loads its CLAUDE.md configuration.

    This command is idempotent - if the agent is already running,
    it reports success without restarting.

    \b
    Examples:
      voicemode agent start              # Start in 'voicemode' session
      voicemode agent start --session vm # Start in 'vm' session
    """
    agent_name = 'operator'
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
    if is_claude_running_in_pane(window):
        click.echo(f"✓ Operator already running in tmux session '{session}'")
        return

    # 6. Start Claude Code
    claude_cmd = build_claude_command(agent_dir)

    result = subprocess.run(
        ['tmux', 'send-keys', '-t', window, claude_cmd, 'Enter'],
        capture_output=True
    )

    if result.returncode != 0:
        click.echo("Error: Failed to start Claude Code", err=True)
        raise SystemExit(1)

    click.echo(f"✓ Operator started in tmux session '{session}'")


@agent.command('status')
@click.option('--session', default='voicemode', help='Tmux session name')
@click.help_option('-h', '--help')
def status(session: str):
    """Show operator status.

    Checks the tmux session, window, and Claude Code process status.

    \b
    Status values:
      running  - Claude Code is active in the operator window
      stopped  - Agent is not running (various reasons shown)

    \b
    Examples:
      voicemode agent status              # Check default session
      voicemode agent status --session vm # Check 'vm' session
    """
    agent_name = 'operator'
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
    if is_claude_running_in_pane(window):
        click.echo("running")
    else:
        click.echo("stopped - Claude not running in window")
