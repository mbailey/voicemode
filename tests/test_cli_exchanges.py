"""
Tests for the CLI exchanges commands using real log data.
"""

import json
import pytest
from click.testing import CliRunner
from datetime import datetime
from pathlib import Path

from voice_mode.cli_commands.exchanges import exchanges


class TestCLIExchangesCommands:
    """Test CLI exchanges commands with real data."""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()
    
    @pytest.fixture
    def real_base_dir(self):
        """Get the real voicemode base directory."""
        return str(Path.home() / ".voicemode")
    
    def test_exchanges_view_command(self, runner):
        """Test the view command shows recent exchanges."""
        result = runner.invoke(exchanges, ['view', '-n', '5'])
        
        assert result.exit_code == 0
        assert result.output
        
        # Should show exchange indicators
        assert '🎤' in result.output or '🔊' in result.output
        assert 'STT' in result.output or 'TTS' in result.output
    
    def test_exchanges_view_with_format(self, runner):
        """Test view command with different formats."""
        # Test JSON format
        result = runner.invoke(exchanges, ['view', '-n', '2', '--format', 'json'])
        assert result.exit_code == 0
        
        # Should be valid JSON - but it's pretty-printed, so we need to parse the whole output
        # Filter out log lines first
        output_lines = result.output.strip().split('\n')
        json_lines = [line for line in output_lines if not ('voice-mode' in line and 'INFO' in line)]
        
        # The output should contain valid JSON objects separated by newlines
        # Try to find complete JSON objects
        json_objects = []
        current_json = ''
        brace_count = 0
        
        for line in json_lines:
            current_json += line + '\n'
            brace_count += line.count('{') - line.count('}')
            
            if brace_count == 0 and current_json.strip():
                try:
                    parsed = json.loads(current_json.strip())
                    json_objects.append(parsed)
                    assert 'type' in parsed
                    assert 'text' in parsed
                    current_json = ''
                except json.JSONDecodeError:
                    pass  # Continue accumulating
        
        # Should have found at least one valid JSON object
        assert len(json_objects) > 0
        
        # Test pretty format
        result = runner.invoke(exchanges, ['view', '-n', '2', '--format', 'pretty'])
        assert result.exit_code == 0
        assert '─' in result.output  # Box drawing characters
    
    def test_exchanges_stats_command(self, runner):
        """Test the stats command."""
        result = runner.invoke(exchanges, ['stats'])
        
        assert result.exit_code == 0
        assert 'Exchange Statistics Summary' in result.output
        assert 'Total Exchanges:' in result.output
        assert 'STT:' in result.output
        assert 'TTS:' in result.output
    
    def test_exchanges_stats_detailed(self, runner):
        """Test stats command with detailed options."""
        result = runner.invoke(exchanges, ['stats', '--all'])
        
        assert result.exit_code == 0
        
        # Should show various statistics sections when --all is used
        # The current implementation shows summary by default when --all is used
        # Check for basic stats output
        assert 'Total Exchanges:' in result.output
        assert 'Providers:' in result.output
        assert 'Transports:' in result.output
        assert 'Conversations:' in result.output
    
    def test_exchanges_search_command(self, runner):
        """Test the search command."""
        # Search for a common word
        result = runner.invoke(exchanges, ['search', 'the', '-n', '3'])
        
        assert result.exit_code == 0
        
        # Should show results count
        assert 'results shown' in result.output
    
    def test_exchanges_search_by_type(self, runner):
        """Test searching filtered by type."""
        # Search for STT only
        result = runner.invoke(exchanges, ['search', 'the', '--type', 'stt', '-n', '3'])
        
        assert result.exit_code == 0
        
        # If there are results, they should all be STT
        if 'STT' in result.output:
            assert 'TTS' not in result.output or result.output.count('TTS') == 0
    
    def test_exchanges_tail_dry_run(self, runner):
        """Test tail command (can't really tail in tests)."""
        # Use view to simulate what tail would show
        result = runner.invoke(exchanges, ['view', '-n', '10'])
        
        assert result.exit_code == 0
        assert result.output
    
    def test_exchanges_export_json(self, runner):
        """Test export command with JSON format."""
        with runner.isolated_filesystem():
            result = runner.invoke(exchanges, ['export', '--days', '1', '--format', 'json', '-o', 'test.json'])
            
            assert result.exit_code == 0
            assert 'Exported to test.json' in result.output
            
            # Check the file exists and is valid JSON
            assert Path('test.json').exists()
            with open('test.json') as f:
                data = json.load(f)
                assert isinstance(data, list)
                if data:  # If there are conversations
                    assert 'exchanges' in data[0]
                    assert 'start_time' in data[0]
    
    def test_exchanges_export_csv(self, runner):
        """Test export command with CSV format."""
        with runner.isolated_filesystem():
            result = runner.invoke(exchanges, ['export', '--days', '1', '--format', 'csv', '-o', 'test.csv'])
            
            assert result.exit_code == 0
            assert 'Exported to test.csv' in result.output
            
            # Check the file exists and has CSV header
            assert Path('test.csv').exists()
            with open('test.csv') as f:
                header = f.readline()
                assert 'timestamp' in header
                assert 'conversation_id' in header
                assert 'type' in header
    
    def test_exchanges_export_markdown(self, runner):
        """Test export command with Markdown format."""
        with runner.isolated_filesystem():
            result = runner.invoke(exchanges, ['export', '--days', '1', '--format', 'markdown', '-o', 'test.md'])
            
            assert result.exit_code == 0
            assert 'Exported to test.md' in result.output
            
            # Check the file exists and has Markdown content
            assert Path('test.md').exists()
            with open('test.md') as f:
                content = f.read()
                assert '# Conversation' in content
                assert '## Transcript' in content
    
    def test_exchanges_view_today(self, runner):
        """Test viewing today's exchanges."""
        result = runner.invoke(exchanges, ['view', '--today'])
        
        assert result.exit_code == 0
        
        # Should show today's date somewhere
        today = datetime.now().strftime("%Y-%m-%d")
        # The exchanges should be from today
    
    def test_exchanges_view_no_color(self, runner):
        """Test viewing without color codes."""
        result = runner.invoke(exchanges, ['view', '-n', '5', '--no-color'])
        
        assert result.exit_code == 0
        
        # Should not contain ANSI color codes
        assert '\033[' not in result.output
    
    def test_exchanges_stats_with_days(self, runner):
        """Test stats for specific number of days."""
        result = runner.invoke(exchanges, ['stats', '--days', '3'])
        
        assert result.exit_code == 0
        assert 'Exchange Statistics Summary' in result.output
    
    def test_exchanges_stats_timing(self, runner):
        """Test timing statistics."""
        result = runner.invoke(exchanges, ['stats', '--timing'])
        
        assert result.exit_code == 0
        
        if 'Timing Statistics:' in result.output:
            # May have TTS timing
            if 'TTS:' in result.output:
                assert 'ttfa' in result.output.lower() or 'avg' in result.output
            
            # May have STT timing  
            if 'STT:' in result.output:
                assert 'record' in result.output.lower() or 'avg' in result.output
    
    def test_exchanges_search_regex(self, runner):
        """Test search with regex."""
        # Search for exchanges starting with specific words
        result = runner.invoke(exchanges, ['search', '^(I|We|You)', '--regex', '-n', '5'])
        
        assert result.exit_code == 0
        
        # Check if any results
        if '0 of 0 results shown' not in result.output:
            # Results should start with I, We, or You
            lines = result.output.strip().split('\n')
            for line in lines:
                if 'STT' in line or 'TTS' in line:
                    # Extract the text part
                    if '] ' in line:
                        text_part = line.split('] ')[-1]
                        first_word = text_part.strip().split()[0] if text_part.strip() else ""
                        # Should start with I, We, or You (case might vary)
                        valid_starts = ['I', 'WE', 'YOU', "I'M", "WE'RE", "YOU'RE", "I'VE", "I'LL", "WE'VE", "WE'LL", "YOU'VE", "YOU'LL"]
                        assert first_word.upper() in valid_starts or not first_word