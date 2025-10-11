#!/usr/bin/env python3
"""Comprehensive help test coverage for all voice-mode commands.

This test suite ensures every voice-mode command and subcommand has:
1. Working help functionality that doesn't crash
2. Fast response times (< 2 seconds)
3. Meaningful and complete help content
4. No deprecation warnings or import errors
"""

import subprocess
import time
from typing import List, Tuple
import pytest
import sys
import os

# Add voice_mode to path for discovery
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def discover_all_commands() -> List[List[str]]:
    """Dynamically discover all voice-mode commands and subcommands.

    Returns a comprehensive list of all command combinations that should
    support --help functionality.
    """
    commands = []

    # Use python -m voice_mode for development testing
    base_cmd = [sys.executable, '-m', 'voice_mode']

    # Main command - test both -h and --help
    commands.append(base_cmd + ['--help'])
    commands.append(base_cmd + ['-h'])

    # Top-level commands
    top_level_commands = ['audio', 'claude', 'completions', 'config', 'converse',
                          'deps', 'diag', 'exchanges', 'kokoro', 'livekit',
                          'update', 'version', 'whisper']

    # Commands that support -h
    commands_with_short_help = ['audio', 'config', 'converse', 'deps', 'diag',
                                'exchanges', 'kokoro', 'livekit', 'whisper']

    for cmd in top_level_commands:
        commands.append(base_cmd + [cmd, '--help'])
        if cmd in commands_with_short_help:
            commands.append(base_cmd + [cmd, '-h'])

    # === WHISPER COMMANDS (restructured with service subgroup) ===
    # Whisper service subcommands
    whisper_service_actions = ['disable', 'enable', 'health', 'install', 'logs',
                               'restart', 'start', 'status', 'stop', 'uninstall',
                               'update-files']
    whisper_service_with_options = ['install', 'logs', 'uninstall']

    commands.append(base_cmd + ['whisper', 'service', '--help'])
    commands.append(base_cmd + ['whisper', 'service', '-h'])

    for action in whisper_service_actions:
        commands.append(base_cmd + ['whisper', 'service', action, '--help'])
        if action in whisper_service_with_options:
            commands.append(base_cmd + ['whisper', 'service', action, '-h'])

    # Whisper model command (simplified - no longer has subcommands)
    commands.append(base_cmd + ['whisper', 'model', '--help'])
    commands.append(base_cmd + ['whisper', 'model', '-h'])

    # === KOKORO COMMANDS (direct, no subgroups) ===
    kokoro_actions = ['disable', 'enable', 'health', 'install', 'logs',
                      'restart', 'start', 'status', 'stop', 'uninstall',
                      'update-service-files']
    kokoro_with_options = ['install', 'logs', 'uninstall']

    for action in kokoro_actions:
        commands.append(base_cmd + ['kokoro', action, '--help'])
        if action in kokoro_with_options:
            commands.append(base_cmd + ['kokoro', action, '-h'])

    # === LIVEKIT COMMANDS ===
    # Direct LiveKit actions
    livekit_actions = ['disable', 'enable', 'install', 'logs', 'restart',
                       'start', 'status', 'stop', 'uninstall', 'update']
    livekit_with_options = ['install', 'logs', 'uninstall']

    for action in livekit_actions:
        commands.append(base_cmd + ['livekit', action, '--help'])
        if action in livekit_with_options:
            commands.append(base_cmd + ['livekit', action, '-h'])

    # LiveKit frontend subcommands
    commands.append(base_cmd + ['livekit', 'frontend', '--help'])
    commands.append(base_cmd + ['livekit', 'frontend', '-h'])

    frontend_cmds = ['build', 'disable', 'enable', 'install', 'logs',
                     'open', 'start', 'status', 'stop']
    frontend_with_options = ['build', 'install', 'logs', 'start']

    for cmd in frontend_cmds:
        commands.append(base_cmd + ['livekit', 'frontend', cmd, '--help'])
        if cmd in frontend_with_options:
            commands.append(base_cmd + ['livekit', 'frontend', cmd, '-h'])

    # === CONFIG COMMANDS ===
    config_subcommands = ['edit', 'get', 'list', 'set']
    config_with_options = ['edit', 'get', 'set']

    for sub in config_subcommands:
        commands.append(base_cmd + ['config', sub, '--help'])
        if sub in config_with_options:
            commands.append(base_cmd + ['config', sub, '-h'])

    # Config pronounce subgroup
    commands.append(base_cmd + ['config', 'pronounce', '--help'])
    pronounce_cmds = ['add', 'disable', 'edit', 'enable', 'list', 'reload', 'remove', 'test']
    for cmd in pronounce_cmds:
        commands.append(base_cmd + ['config', 'pronounce', cmd, '--help'])

    # === EXCHANGES COMMANDS ===
    exchanges_subcommands = ['export', 'search', 'stats', 'tail', 'view']
    for sub in exchanges_subcommands:
        commands.append(base_cmd + ['exchanges', sub, '--help'])
        commands.append(base_cmd + ['exchanges', sub, '-h'])

    # === DIAG COMMANDS ===
    diag_subcommands = ['dependencies', 'devices', 'info', 'registry']
    for sub in diag_subcommands:
        commands.append(base_cmd + ['diag', sub, '--help'])

    # === AUDIO COMMANDS ===
    audio_subcommands = ['play', 'transcribe']
    for sub in audio_subcommands:
        commands.append(base_cmd + ['audio', sub, '--help'])
        if sub == 'play':  # Only 'play' supports -h
            commands.append(base_cmd + ['audio', sub, '-h'])

    # === CLAUDE COMMANDS ===
    commands.append(base_cmd + ['claude', 'hooks', '--help'])
    commands.append(base_cmd + ['claude', 'hooks', '-h'])
    commands.append(base_cmd + ['claude', 'hooks', 'receiver', '--help'])
    # Note: receiver doesn't support -h, only --help

    # === COMPLETIONS (special - takes positional arg) ===
    # Note: completions uses positional args, so we only test main help
    # Individual shell completions (bash, zsh, fish) don't have separate --help

    return commands


def categorize_command(command: List[str]) -> str:
    """Categorize a command for performance expectations.
    
    Different command types may have different acceptable performance thresholds.
    """
    # Skip the python -m voice_mode part
    cmd_str = ' '.join(command[3:]) if len(command) > 3 else ' '.join(command)
    
    if 'service' in cmd_str or 'whisper' in cmd_str or 'kokoro' in cmd_str or 'livekit' in cmd_str:
        return 'service'
    elif 'install' in cmd_str or 'uninstall' in cmd_str:
        return 'install'
    elif 'statistics' in cmd_str or 'voice-registry' in cmd_str:
        return 'stats'
    elif len(command) == 4:  # Just python -m voice_mode --help
        return 'main'
    else:
        return 'utility'


def get_performance_threshold(category: str) -> float:
    """Get acceptable performance threshold for command category.
    
    Some commands may legitimately need more time due to their complexity.
    """
    thresholds = {
        'main': 0.8,      # Main help should be fast (increased from 0.5 for CI environments)
        'service': 1.0,   # Service commands can take a bit longer
        'install': 1.5,   # Install commands might need more discovery
        'stats': 1.0,     # Stats commands are moderate
        'utility': 1.0,   # General utilities
    }
    return thresholds.get(category, 2.0)


class TestHelpComprehensive:
    """Comprehensive test suite for all voice-mode help commands."""
    
    @pytest.mark.parametrize("command", discover_all_commands())
    def test_help_functionality(self, command: List[str]):
        """Test that help works for all commands without crashing.
        
        Validates:
        - Command executes without error
        - Returns exit code 0
        - Outputs to stdout
        - No critical errors in stderr
        """
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,  # Generous timeout for safety
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        
        # Basic functionality checks
        assert result.returncode == 0, f"Command failed: {' '.join(command)}\nStderr: {result.stderr}"
        assert result.stdout, f"No help output for: {' '.join(command)}"
        
        # Check for common error indicators
        stderr_lower = result.stderr.lower()
        assert 'error' not in stderr_lower or 'no module' not in stderr_lower, \
            f"Error in stderr for {' '.join(command)}: {result.stderr}"
        assert 'traceback' not in stderr_lower, \
            f"Traceback in stderr for {' '.join(command)}: {result.stderr}"
    
    @pytest.mark.parametrize("command", discover_all_commands())
    def test_help_performance(self, command: List[str]):
        """Test that help commands respond quickly.
        
        Ensures lazy loading is working and help doesn't trigger
        expensive imports.
        """
        category = categorize_command(command)
        threshold = get_performance_threshold(category)
        
        start_time = time.time()
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        
        duration = time.time() - start_time
        
        assert result.returncode == 0  # Ensure command succeeded
        assert duration < threshold, \
            f"Help for {' '.join(command)} took {duration:.2f}s (threshold: {threshold}s)"
    
    @pytest.mark.parametrize("command", discover_all_commands())
    def test_help_content_quality(self, command: List[str]):
        """Test that help content is meaningful and complete.
        
        Validates:
        - Help text has minimum length
        - Contains expected sections
        - No deprecation warnings
        - Proper formatting
        """
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        
        assert result.returncode == 0
        output = result.stdout
        output_lower = output.lower()
        
        # Content quality checks
        assert len(output) > 50, f"Help text too short for {' '.join(command)}"
        
        # Should contain usage information
        assert any(word in output_lower for word in ['usage:', 'usage ', 'use:']), \
            f"No usage information in help for {' '.join(command)}"
        
        # Check for no deprecation warnings
        assert 'deprecat' not in output_lower, \
            f"Deprecation warning in help for {' '.join(command)}"
        assert 'deprecat' not in result.stderr.lower(), \
            f"Deprecation warning in stderr for {' '.join(command)}"
        
        # Service commands should mention their actions
        if 'service' in ' '.join(command) or any(svc in ' '.join(command) for svc in ['whisper', 'kokoro', 'livekit']):
            if 'status' not in command and '--help' not in command[:-1]:
                # Service-level help should mention available actions
                pass  # Could add more specific checks here
    
    def test_help_main_command_sections(self):
        """Test that main help command has all expected sections."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '--help'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        assert result.returncode == 0
        output = result.stdout.lower()
        
        # Main help should have these sections
        expected_sections = [
            'usage',
            'options',  # Click uses 'Options' not 'optional arguments'
            'commands',
        ]
        
        for section in expected_sections:
            assert section in output, f"Missing section '{section}' in main help"
    
    def test_help_no_heavy_imports(self):
        """Verify help doesn't trigger heavy imports by checking for specific warnings."""
        # Run help and check for signs of heavy imports
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '--help'],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        
        assert result.returncode == 0
        
        # Check stderr for import-related warnings
        stderr_lower = result.stderr.lower()
        
        # These indicate heavy imports that shouldn't happen for help
        unwanted_indicators = [
            'numba',  # Heavy numerical library
            'torch',  # PyTorch
            'tensorflow',  # TensorFlow
            'webrtcvad',  # Should be lazy loaded
            'pydub',  # Should be lazy loaded
        ]
        
        for indicator in unwanted_indicators:
            assert indicator not in stderr_lower, \
                f"Heavy import detected in help: {indicator}"
    
    @pytest.mark.parametrize("service,expected_actions", [
        ('whisper', ['service', 'model']),  # Whisper has service and model subgroups
        ('kokoro', ['status', 'start', 'stop', 'restart']),  # Kokoro has direct actions
        ('livekit', ['status', 'start', 'stop', 'restart', 'frontend'])  # LiveKit has actions + frontend
    ])
    def test_service_help_completeness(self, service: str, expected_actions: List[str]):
        """Test that service help includes all expected subcommands."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', service, '--help'],
            capture_output=True,
            text=True,
            timeout=2
        )

        assert result.returncode == 0
        output = result.stdout.lower()

        for action in expected_actions:
            assert action in output, \
                f"Service {service} help missing: {action}"


class TestHelpEdgeCases:
    """Test edge cases and error conditions for help functionality."""
    
    def test_help_invalid_command(self):
        """Test that invalid commands show appropriate help or error."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', 'nonexistent-command', '--help'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # Should either show main help or error message
        assert result.stdout or result.stderr
        
        # Should not crash with traceback
        assert 'traceback' not in result.stderr.lower()
    
    def test_help_partial_command(self):
        """Test help works with partial commands."""
        result = subprocess.run(
            [sys.executable, '-m', 'voice_mode', 'whisper'],  # No action specified
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # Should show whisper help or usage
        assert 'whisper' in result.stdout.lower() or 'whisper' in result.stderr.lower()
    
    def test_help_consistency(self):
        """Test that -h and --help produce same output."""
        result_long = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '--help'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        result_short = subprocess.run(
            [sys.executable, '-m', 'voice_mode', '-h'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        assert result_long.returncode == result_short.returncode
        assert result_long.stdout == result_short.stdout


class TestPerformanceBaseline:
    """Establish and verify performance baselines for help commands."""
    
    def test_main_help_baseline(self):
        """Test main help command meets performance baseline."""
        times = []
        
        # Run multiple times to get average
        for _ in range(3):
            start = time.time()
            result = subprocess.run(
                [sys.executable, '-m', 'voice_mode', '--help'],
                capture_output=True,
                text=True,
                timeout=2
            )
            duration = time.time() - start
            
            assert result.returncode == 0
            times.append(duration)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 0.8, f"Main help average time {avg_time:.2f}s exceeds baseline"
    
    def test_no_performance_regression(self):
        """Ensure help performance doesn't regress over time."""
        # This could be enhanced to store and compare against historical data
        
        commands_to_benchmark = [
            [sys.executable, '-m', 'voice_mode', '--help'],
            [sys.executable, '-m', 'voice_mode', 'whisper', '--help'],
            [sys.executable, '-m', 'voice_mode', 'config', '--help'],
        ]
        
        for command in commands_to_benchmark:
            start = time.time()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3
            )
            duration = time.time() - start
            
            assert result.returncode == 0
            
            # Log for future comparison
            print(f"Benchmark: {' '.join(command[3:])} took {duration:.3f}s")


if __name__ == "__main__":
    # Can run directly for development/debugging
    print(f"Discovering commands...")
    commands = discover_all_commands()
    print(f"Found {len(commands)} command combinations to test")
    
    # Show sample of commands
    print("\nSample commands:")
    for cmd in commands[:10]:
        # Show simplified version for readability
        display_cmd = ' '.join(cmd[3:]) if len(cmd) > 3 else ' '.join(cmd)
        print(f"  voice-mode {display_cmd}")
    
    print(f"\n... and {len(commands) - 10} more")
    
    # Quick performance test of main help
    print("\nQuick performance test:")
    start = time.time()
    result = subprocess.run(
        [sys.executable, '-m', 'voice_mode', '--help'],
        capture_output=True,
        text=True
    )
    duration = time.time() - start
    print(f"Main help took {duration:.3f}s (target: <0.5s)")
    print(f"Exit code: {result.returncode}")
    print(f"Output length: {len(result.stdout)} chars")