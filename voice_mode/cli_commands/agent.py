"""Agent management commands for VoiceMode.

Agents are Claude Code instances that can be controlled remotely.
The default agent is 'operator' - accessible from the iOS app and web interface.
"""

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
