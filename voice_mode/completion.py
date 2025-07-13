"""
Shell completion support for voice-mode-cli.
"""

import os
import click
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple

from voice_mode.exchanges import ExchangeReader
from voice_mode.__version__ import __version__


def complete_conversation_ids(ctx, param, incomplete: str):
    """Complete conversation IDs from recent exchanges."""
    try:
        reader = ExchangeReader()
        # Get recent exchanges to find conversation IDs
        recent_exchanges = list(reader.read_recent(7))
        
        # Get unique conversation IDs
        conv_ids = set()
        for exchange in recent_exchanges:
            if exchange.conversation_id.startswith(incomplete):
                conv_ids.add(exchange.conversation_id)
        
        return sorted(list(conv_ids))[:20]  # Limit to 20 suggestions
    except Exception:
        return []


def complete_dates(ctx, param, incomplete: str):
    """Complete dates in YYYY-MM-DD format."""
    try:
        # Suggest dates from last 30 days
        dates = []
        today = datetime.now().date()
        
        for i in range(30):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            if date_str.startswith(incomplete):
                dates.append(date_str)
        
        return dates[:10]  # Limit to 10 suggestions
    except Exception:
        return []


def complete_providers(ctx, param, incomplete: str):
    """Complete provider names from recent exchanges."""
    try:
        reader = ExchangeReader()
        recent_exchanges = list(reader.read_recent(7))
        
        providers = set()
        for exchange in recent_exchanges:
            if exchange.metadata and exchange.metadata.provider:
                provider = exchange.metadata.provider
                if provider.startswith(incomplete):
                    providers.add(provider)
        
        return sorted(list(providers))
    except Exception:
        return ["openai", "kokoro", "whisper-local"]  # Default fallback


def complete_voices(ctx, param, incomplete: str):
    """Complete voice names from recent exchanges."""
    try:
        reader = ExchangeReader()
        recent_exchanges = list(reader.read_recent(7))
        
        voices = set()
        for exchange in recent_exchanges:
            if exchange.metadata and exchange.metadata.voice:
                voice = exchange.metadata.voice
                if voice.startswith(incomplete):
                    voices.add(voice)
        
        return sorted(list(voices))
    except Exception:
        return ["alloy", "nova", "shimmer", "af_sky", "am_adam"]  # Default fallback


def complete_transports(ctx, param, incomplete: str):
    """Complete transport types."""
    transports = ["local", "livekit", "speak-only"]
    return [t for t in transports if t.startswith(incomplete)]


def complete_models(ctx, param, incomplete: str):
    """Complete model names from recent exchanges."""
    try:
        reader = ExchangeReader()
        recent_exchanges = list(reader.read_recent(7))
        
        models = set()
        for exchange in recent_exchanges:
            if exchange.metadata and exchange.metadata.model:
                model = exchange.metadata.model
                if model.startswith(incomplete):
                    models.add(model)
        
        return sorted(list(models))
    except Exception:
        return ["whisper-1", "tts-1", "tts-1-hd", "gpt-4o-mini-tts"]  # Default fallback


def complete_file_extensions(ctx, param, incomplete: str):
    """Complete file extensions for export formats."""
    extensions = {
        "json": ".json",
        "csv": ".csv", 
        "markdown": ".md",
        "html": ".html"
    }
    
    # Get the format from context if available
    format_param = ctx.params.get('format', 'json')
    ext = extensions.get(format_param, '.json')
    
    if incomplete.endswith(ext):
        return [incomplete]
    elif '.' not in incomplete:
        return [incomplete + ext]
    else:
        return [incomplete]


def complete_output_files(ctx, param, incomplete: str):
    """Complete output file paths with appropriate extensions."""
    try:
        # Get the format from context
        format_param = ctx.params.get('format', 'json')
        extensions = {
            "json": ".json",
            "csv": ".csv",
            "markdown": ".md", 
            "html": ".html"
        }
        
        # If incomplete doesn't have extension, suggest with extension
        if '.' not in incomplete:
            ext = extensions.get(format_param, '.json')
            suggestions = [
                f"exchanges_{datetime.now().strftime('%Y%m%d')}{ext}",
                f"conversations_{datetime.now().strftime('%Y%m%d')}{ext}",
                f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            ]
            return [s for s in suggestions if s.startswith(incomplete)]
        
        return [incomplete]
    except Exception:
        return [incomplete]


# Custom completion for search patterns
def complete_search_patterns(ctx, param, incomplete: str):
    """Complete common search patterns."""
    common_patterns = [
        "error", "warning", "failed", "success", "hello", "help", "please",
        "thank", "sorry", "yes", "no", "ok", "done", "start", "stop",
        "create", "update", "delete", "get", "set", "fix", "implement"
    ]
    
    return [p for p in common_patterns if p.startswith(incomplete.lower())]


def install_completion_command():
    """Create a command to install shell completion."""
    
    @click.command()
    @click.option('--shell', type=click.Choice(['bash', 'zsh', 'fish']), 
                  help='Shell type (auto-detected if not specified)')
    @click.option('--show', is_flag=True, help='Show completion script instead of installing')
    @click.option('--static', is_flag=True, help='Generate static completion script (much faster, recommended)')
    def completion(shell, show, static):
        """Install shell completion for voice-mode-cli.
        
        Static completion (--static) is much faster as it generates a completion
        script once using current data. Dynamic completion calls voice-mode-cli
        on every tab press, which is slower but always up-to-date.
        
        Recommended: Use --static for better performance.
        """
        import subprocess
        import sys
        
        # Auto-detect shell if not specified
        if not shell:
            try:
                shell_path = subprocess.check_output(['ps', '-p', str(os.getppid()), '-o', 'comm=']).decode().strip()
                if 'bash' in shell_path:
                    shell = 'bash'
                elif 'zsh' in shell_path:
                    shell = 'zsh'
                elif 'fish' in shell_path:
                    shell = 'fish'
                else:
                    click.echo("Could not auto-detect shell. Please specify with --shell", err=True)
                    sys.exit(1)
            except Exception:
                click.echo("Could not auto-detect shell. Please specify with --shell", err=True)
                sys.exit(1)
        
        if static:
            # Generate static completion script
            script = generate_static_completion_script(shell)
            
            if show:
                click.echo(script)
            else:
                # Install static completion
                install_static_completion(shell, script)
        elif show:
            # Show dynamic completion instructions
            click.echo(f"To enable {shell} completion for voice-mode-cli, add this to your shell config:")
            click.echo()
            if shell == 'bash':
                click.echo("# Add to ~/.bashrc:")
                click.echo('eval "$(_VOICE_MODE_CLI_COMPLETE=bash_source voice-mode-cli)"')
            elif shell == 'zsh':
                click.echo("# Add to ~/.zshrc:")
                click.echo('eval "$(_VOICE_MODE_CLI_COMPLETE=zsh_source voice-mode-cli)"')
            elif shell == 'fish':
                click.echo("# Add to ~/.config/fish/config.fish:")
                click.echo('_VOICE_MODE_CLI_COMPLETE=fish_source voice-mode-cli | source')
        else:
            # Install dynamic completion (slower but always up-to-date)
            install_dynamic_completion(shell)
    
    return completion


def generate_static_completion_script(shell: str) -> str:
    """Generate a static completion script for the specified shell."""
    
    # Use standard completion values only - no private data from logs
    conversation_ids = set()  # Empty - don't include private conversation IDs
    providers = {'openai', 'kokoro', 'whisper-local'}
    voices = {'alloy', 'nova', 'shimmer', 'echo', 'fable', 'onyx', 'af_sky', 'af_sarah', 'am_adam'}
    models = {'whisper-1', 'tts-1', 'tts-1-hd', 'gpt-4o-mini-tts'}
    transports = {'local', 'livekit', 'speak-only'}
    
    # Generate dates for the last 30 days
    dates = []
    today = datetime.now().date()
    for i in range(30):
        date = today - timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    
    if shell == 'bash':
        return generate_bash_completion_script(
            conversation_ids, providers, voices, models, transports, dates
        )
    elif shell == 'zsh':
        return generate_zsh_completion_script(
            conversation_ids, providers, voices, models, transports, dates
        )
    elif shell == 'fish':
        return generate_fish_completion_script(
            conversation_ids, providers, voices, models, transports, dates
        )
    else:
        raise ValueError(f"Unsupported shell: {shell}")


def generate_bash_completion_script(conversation_ids, providers, voices, models, transports, dates) -> str:
    """Generate a bash completion script."""
    
    # For privacy, we don't include actual conversation IDs
    conv_ids_str = ''  # Empty - no private data
    providers_str = ' '.join(sorted(providers))
    voices_str = ' '.join(sorted(voices))
    models_str = ' '.join(sorted(models))
    transports_str = ' '.join(sorted(transports))
    dates_str = ' '.join(dates[:10])  # Last 10 days
    
    return f'''# Bash completion for voice-mode-cli
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by voice-mode v{__version__}
# TODO: Implement version check notification for outdated completion scripts

_voice_mode_cli_completion() {{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    
    # Main commands
    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        opts="completion exchanges"
        COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) )
        return 0
    fi
    
    # exchanges subcommands
    if [[ ${{COMP_WORDS[1]}} == "exchanges" ]] && [[ ${{COMP_CWORD}} -eq 2 ]]; then
        opts="export search stats tail view"
        COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) )
        return 0
    fi
    
    # Option completions
    case "${{prev}}" in
        --conversation|-c)
            COMPREPLY=( $(compgen -W "{conv_ids_str}" -- ${{cur}}) )
            ;;
        --provider)
            COMPREPLY=( $(compgen -W "{providers_str}" -- ${{cur}}) )
            ;;
        --voice)
            COMPREPLY=( $(compgen -W "{voices_str}" -- ${{cur}}) )
            ;;
        --model)
            COMPREPLY=( $(compgen -W "{models_str}" -- ${{cur}}) )
            ;;
        --transport)
            COMPREPLY=( $(compgen -W "{transports_str}" -- ${{cur}}) )
            ;;
        --date|-d)
            COMPREPLY=( $(compgen -W "{dates_str}" -- ${{cur}}) )
            ;;
        --format|-f)
            COMPREPLY=( $(compgen -W "simple pretty json csv markdown html" -- ${{cur}}) )
            ;;
        --shell)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- ${{cur}}) )
            ;;
        *)
            # Default to showing available options
            if [[ ${{cur}} == -* ]]; then
                opts="--help --format --provider --transport --voice --model --conversation --date --shell"
                COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) )
            fi
            ;;
    esac
}}

complete -F _voice_mode_cli_completion voice-mode-cli
'''


def generate_zsh_completion_script(conversation_ids, providers, voices, models, transports, dates) -> str:
    """Generate a zsh completion script."""
    
    # For privacy, we don't include actual conversation IDs
    conv_ids_list = ''  # Empty - no private data
    providers_list = '\\n        '.join(f'"{p}:provider {p}"' for p in sorted(providers))
    voices_list = '\\n        '.join(f'"{v}:voice {v}"' for v in sorted(voices))
    models_list = '\\n        '.join(f'"{m}:model {m}"' for m in sorted(models))
    transports_list = '\\n        '.join(f'"{t}:transport {t}"' for t in sorted(transports))
    dates_list = '\\n        '.join(f'"{d}:date {d}"' for d in dates[:10])
    
    return f'''#compdef voice-mode-cli
# Zsh completion for voice-mode-cli
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by voice-mode v{__version__}
# TODO: Implement version check notification for outdated completion scripts

_voice_mode_cli() {{
    local context curcontext="$curcontext" state line
    typeset -A opt_args
    
    _arguments -C \\
        '1: :_voice_mode_cli_commands' \\
        '*::arg:->args'
    
    case $line[1] in
        exchanges)
            _voice_mode_cli_exchanges
            ;;
        completion)
            _voice_mode_cli_completion
            ;;
    esac
}}

_voice_mode_cli_commands() {{
    local commands
    commands=(
        'exchanges:Manage and view conversation exchange logs'
        'completion:Install shell completion'
    )
    _describe 'command' commands
}}

_voice_mode_cli_exchanges() {{
    local context curcontext="$curcontext" state line
    typeset -A opt_args
    
    _arguments -C \\
        '1: :_voice_mode_cli_exchanges_commands' \\
        '*::arg:->args'
    
    case $line[1] in
        view|tail|search|stats|export)
            _voice_mode_cli_exchanges_options
            ;;
    esac
}}

_voice_mode_cli_exchanges_commands() {{
    local commands
    commands=(
        'view:View recent exchanges'
        'tail:Real-time following of exchange logs'
        'search:Search through exchange logs'
        'stats:Show statistics about exchanges'
        'export:Export conversations in various formats'
    )
    _describe 'command' commands
}}

_voice_mode_cli_exchanges_options() {{
    _arguments \\
        '(-c --conversation){{-c,--conversation}}[Show specific conversation]:conversation:_voice_mode_cli_conversations' \\
        '(-d --date){{-d,--date}}[Show specific date]:date:_voice_mode_cli_dates' \\
        '--provider[Filter by provider]:provider:_voice_mode_cli_providers' \\
        '--transport[Filter by transport]:transport:_voice_mode_cli_transports' \\
        '--voice[Voice name]:voice:_voice_mode_cli_voices' \\
        '--model[Model name]:model:_voice_mode_cli_models' \\
        '(-f --format){{-f,--format}}[Output format]:format:(simple pretty json csv markdown html)' \\
        '--shell[Shell type]:shell:(bash zsh fish)' \\
        '--help[Show help]'
}}

_voice_mode_cli_conversations() {{
    local conversations
    conversations=(
        {conv_ids_list}
    )
    _describe 'conversation' conversations
}}

_voice_mode_cli_providers() {{
    local providers
    providers=(
        {providers_list}
    )
    _describe 'provider' providers
}}

_voice_mode_cli_voices() {{
    local voices
    voices=(
        {voices_list}
    )
    _describe 'voice' voices
}}

_voice_mode_cli_models() {{
    local models
    models=(
        {models_list}
    )
    _describe 'model' models
}}

_voice_mode_cli_transports() {{
    local transports
    transports=(
        {transports_list}
    )
    _describe 'transport' transports
}}

_voice_mode_cli_dates() {{
    local dates
    dates=(
        {dates_list}
    )
    _describe 'date' dates
}}

_voice_mode_cli_completion() {{
    _arguments \\
        '--shell[Shell type]:shell:(bash zsh fish)' \\
        '--show[Show completion script]' \\
        '--static[Generate static completion script]' \\
        '--help[Show help]'
}}

_voice_mode_cli "$@"
'''


def generate_fish_completion_script(conversation_ids, providers, voices, models, transports, dates) -> str:
    """Generate a fish completion script."""
    
    # For privacy, we don't include actual conversation IDs
    conv_ids_completions = ''  # Empty - no private data
    providers_completions = '\\n'.join(f'complete -c voice-mode-cli -f -a "{p}" -d "Provider {p}"' for p in sorted(providers))
    voices_completions = '\\n'.join(f'complete -c voice-mode-cli -f -a "{v}" -d "Voice {v}"' for v in sorted(voices))
    models_completions = '\\n'.join(f'complete -c voice-mode-cli -f -a "{m}" -d "Model {m}"' for m in sorted(models))
    transports_completions = '\\n'.join(f'complete -c voice-mode-cli -f -a "{t}" -d "Transport {t}"' for t in sorted(transports))
    dates_completions = '\\n'.join(f'complete -c voice-mode-cli -f -a "{d}" -d "Date {d}"' for d in dates[:10])
    
    return f'''# Fish completion for voice-mode-cli
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by voice-mode v{__version__}
# TODO: Implement version check notification for outdated completion scripts

# Main commands
complete -c voice-mode-cli -f -a "exchanges" -d "Manage and view conversation exchange logs"
complete -c voice-mode-cli -f -a "completion" -d "Install shell completion"

# exchanges subcommands
complete -c voice-mode-cli -f -n "__fish_seen_subcommand_from exchanges" -a "view" -d "View recent exchanges"
complete -c voice-mode-cli -f -n "__fish_seen_subcommand_from exchanges" -a "tail" -d "Real-time following of exchange logs"
complete -c voice-mode-cli -f -n "__fish_seen_subcommand_from exchanges" -a "search" -d "Search through exchange logs"
complete -c voice-mode-cli -f -n "__fish_seen_subcommand_from exchanges" -a "stats" -d "Show statistics about exchanges"
complete -c voice-mode-cli -f -n "__fish_seen_subcommand_from exchanges" -a "export" -d "Export conversations in various formats"

# Global options
complete -c voice-mode-cli -l help -d "Show help"
complete -c voice-mode-cli -l version -d "Show version"

# Format options
complete -c voice-mode-cli -l format -f -a "simple pretty json csv markdown html" -d "Output format"

# Shell options
complete -c voice-mode-cli -l shell -f -a "bash zsh fish" -d "Shell type"

# Provider completions
{providers_completions}

# Voice completions
{voices_completions}

# Model completions
{models_completions}

# Transport completions
{transports_completions}

# Date completions
{dates_completions}

# Conversation ID completions
{conv_ids_completions}
'''


def install_static_completion(shell: str, script: str):
    """Install static completion script."""
    
    if shell == 'bash':
        comp_dir = Path.home() / '.local' / 'share' / 'bash-completion' / 'completions'
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_file = comp_dir / 'voice-mode-cli'
        
        comp_file.write_text(script)
        click.echo(f"Static bash completion installed to {comp_file}")
        click.echo("Restart your shell to enable completions")
        
    elif shell == 'zsh':
        comp_dir = Path.home() / '.local' / 'share' / 'zsh' / 'site-functions'
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_file = comp_dir / '_voice-mode-cli'
        
        comp_file.write_text(script)
        click.echo(f"Static zsh completion installed to {comp_file}")
        click.echo("Add this to your ~/.zshrc if not already present:")
        click.echo(f"fpath=(~/.local/share/zsh/site-functions $fpath)")
        click.echo("autoload -U compinit && compinit")
        click.echo("Then restart your shell")
        
    elif shell == 'fish':
        comp_dir = Path.home() / '.config' / 'fish' / 'completions'
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_file = comp_dir / 'voice-mode-cli.fish'
        
        comp_file.write_text(script)
        click.echo(f"Static fish completion installed to {comp_file}")
        click.echo("Restart your shell to enable completions")


def install_dynamic_completion(shell: str):
    """Install dynamic completion (slower but always up-to-date)."""
    
    if shell == 'bash':
        bashrc = Path.home() / '.bashrc'
        completion_line = 'eval "$(_VOICE_MODE_CLI_COMPLETE=bash_source voice-mode-cli)"'
        
        if bashrc.exists():
            content = bashrc.read_text()
            if completion_line not in content:
                with open(bashrc, 'a') as f:
                    f.write(f'\\n# voice-mode-cli completion\\n{completion_line}\\n')
                click.echo(f"Dynamic bash completion added to {bashrc}")
                click.echo("Restart your shell or run: source ~/.bashrc")
            else:
                click.echo("Dynamic bash completion already installed")
        else:
            click.echo(f"~/.bashrc not found. Please add this line manually:")
            click.echo(completion_line)
    
    elif shell == 'zsh':
        zshrc = Path.home() / '.zshrc'
        completion_line = 'eval "$(_VOICE_MODE_CLI_COMPLETE=zsh_source voice-mode-cli)"'
        
        if zshrc.exists():
            content = zshrc.read_text()
            if completion_line not in content:
                with open(zshrc, 'a') as f:
                    f.write(f'\\n# voice-mode-cli completion\\n{completion_line}\\n')
                click.echo(f"Dynamic zsh completion added to {zshrc}")
                click.echo("Restart your shell or run: source ~/.zshrc")
            else:
                click.echo("Dynamic zsh completion already installed")
        else:
            click.echo(f"~/.zshrc not found. Please add this line manually:")
            click.echo(completion_line)
    
    elif shell == 'fish':
        fish_config = Path.home() / '.config' / 'fish' / 'config.fish'
        completion_line = '_VOICE_MODE_CLI_COMPLETE=fish_source voice-mode-cli | source'
        
        # Create fish config directory if it doesn't exist
        fish_config.parent.mkdir(parents=True, exist_ok=True)
        
        if fish_config.exists():
            content = fish_config.read_text()
            if completion_line not in content:
                with open(fish_config, 'a') as f:
                    f.write(f'\\n# voice-mode-cli completion\\n{completion_line}\\n')
                click.echo(f"Dynamic fish completion added to {fish_config}")
                click.echo("Restart your shell to enable completions")
            else:
                click.echo("Dynamic fish completion already installed")
        else:
            fish_config.write_text(f'# voice-mode-cli completion\\n{completion_line}\\n')
            click.echo(f"Dynamic fish completion added to {fish_config}")
            click.echo("Restart your shell to enable completions")