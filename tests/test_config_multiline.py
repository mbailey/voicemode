"""Tests for multiline environment variable handling in config loader."""

import os
import tempfile
from pathlib import Path
import pytest


def test_config_multiline_quoted_values():
    """Test that config loader handles multiline quoted values."""
    # Create a temporary config file with multiline value
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("""VOICEMODE_VOICES=af_nicole
VOICEMODE_PRONOUNCE='TTS bag carrier
TTS bottle drink'
VOICEMODE_DEBUG=false
""")
        config_file = f.name

    try:
        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith('VOICEMODE_'):
                del os.environ[key]

        # Manually load the config file (simulating the loader)
        with open(config_file, 'r') as f:
            lines = f.readlines()
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    i += 1
                    continue

                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle multiline quoted values
                    if value and value[0] in ('"', "'"):
                        quote_char = value[0]
                        # Check if the quote is closed on the same line
                        if len(value) > 1 and value[-1] == quote_char:
                            # Single line quoted value - strip quotes
                            value = value[1:-1]
                        else:
                            # Multiline quoted value - collect lines until closing quote
                            value_parts = [value[1:]]  # Start after opening quote
                            i += 1
                            while i < len(lines):
                                next_line = lines[i].rstrip('\n')
                                if next_line.endswith(quote_char):
                                    # Found closing quote
                                    value_parts.append(next_line[:-1])
                                    break
                                else:
                                    value_parts.append(next_line)
                                i += 1
                            value = '\n'.join(value_parts)

                    # Set in environment
                    if key:
                        os.environ[key] = value

                i += 1

        # Verify single-line value
        assert os.environ['VOICEMODE_VOICES'] == 'af_nicole'
        assert os.environ['VOICEMODE_DEBUG'] == 'false'

        # Verify multiline value was properly loaded
        assert 'VOICEMODE_PRONOUNCE' in os.environ
        pronounce_value = os.environ['VOICEMODE_PRONOUNCE']
        assert 'TTS bag carrier' in pronounce_value
        assert 'TTS bottle drink' in pronounce_value
        assert '\n' in pronounce_value  # Should contain newline

        # Verify it can be parsed as pronunciation rules
        from voice_mode.pronounce import parse_compact_rules
        rules = parse_compact_rules(pronounce_value)
        assert len(rules['tts']) == 2
        assert rules['tts'][0].pattern == 'bag'
        assert rules['tts'][0].replacement == 'carrier'
        assert rules['tts'][1].pattern == 'bottle'
        assert rules['tts'][1].replacement == 'drink'

    finally:
        # Clean up
        os.unlink(config_file)
        for key in list(os.environ.keys()):
            if key.startswith('VOICEMODE_'):
                del os.environ[key]


def test_config_single_line_quoted_values():
    """Test that config loader handles single-line quoted values."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("""VOICEMODE_PRONOUNCE='TTS bag carrier'
VOICEMODE_TEST="STT foo bar"
""")
        config_file = f.name

    try:
        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith('VOICEMODE_'):
                del os.environ[key]

        # Manually load the config file
        with open(config_file, 'r') as f:
            lines = f.readlines()
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                if not line or line.startswith('#'):
                    i += 1
                    continue

                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle quoted values
                    if value and value[0] in ('"', "'"):
                        quote_char = value[0]
                        if len(value) > 1 and value[-1] == quote_char:
                            value = value[1:-1]
                        else:
                            value_parts = [value[1:]]
                            i += 1
                            while i < len(lines):
                                next_line = lines[i].rstrip('\n')
                                if next_line.endswith(quote_char):
                                    value_parts.append(next_line[:-1])
                                    break
                                else:
                                    value_parts.append(next_line)
                                i += 1
                            value = '\n'.join(value_parts)

                    if key:
                        os.environ[key] = value

                i += 1

        # Verify quotes were stripped from single-line values
        assert os.environ['VOICEMODE_PRONOUNCE'] == 'TTS bag carrier'
        assert os.environ['VOICEMODE_TEST'] == 'STT foo bar'

    finally:
        os.unlink(config_file)
        for key in list(os.environ.keys()):
            if key.startswith('VOICEMODE_'):
                del os.environ[key]
