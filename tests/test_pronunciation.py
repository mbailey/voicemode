"""Tests for pronunciation rules parsing."""

import os
import pytest
from voice_mode.pronounce import parse_compact_rules, PronounceManager


def test_parse_basic_tts_rule():
    """Test parsing a basic TTS rule."""
    rules = parse_compact_rules('TTS bag carrier')
    assert len(rules['tts']) == 1
    assert len(rules['stt']) == 0
    assert rules['tts'][0].pattern == 'bag'
    assert rules['tts'][0].replacement == 'carrier'


def test_parse_basic_stt_rule():
    """Test parsing a basic STT rule."""
    rules = parse_compact_rules('STT bag carrier')
    assert len(rules['stt']) == 1
    assert len(rules['tts']) == 0
    assert rules['stt'][0].pattern == 'bag'
    assert rules['stt'][0].replacement == 'carrier'


def test_parse_with_description():
    """Test parsing rule with description."""
    rules = parse_compact_rules('TTS bag carrier # test description')
    assert len(rules['tts']) == 1
    assert rules['tts'][0].pattern == 'bag'
    assert rules['tts'][0].replacement == 'carrier'
    assert rules['tts'][0].description == 'test description'


def test_parse_with_quoted_replacement():
    """Test parsing rule with spaces in replacement."""
    rules = parse_compact_rules('TTS bag "bag carrier" # test')
    assert len(rules['tts']) == 1
    assert rules['tts'][0].pattern == 'bag'
    assert rules['tts'][0].replacement == 'bag carrier'


def test_parse_with_regex_pattern():
    """Test parsing rule with regex pattern."""
    rules = parse_compact_rules(r'TTS \bbag\b carrier # word boundary')
    assert len(rules['tts']) == 1
    assert rules['tts'][0].pattern == r'\bbag\b'
    assert rules['tts'][0].replacement == 'carrier'


def test_parse_multiple_rules():
    """Test parsing multiple rules."""
    text = '''TTS bag carrier # first
STT carrier bag # second
TTS foo bar # third'''
    rules = parse_compact_rules(text)
    assert len(rules['tts']) == 2
    assert len(rules['stt']) == 1


def test_parse_case_insensitive_direction():
    """Test that direction is case insensitive."""
    for direction in ['TTS', 'tts', 'Tts']:
        rules = parse_compact_rules(f'{direction} bag carrier')
        assert len(rules['tts']) == 1

    # Test STT variants
    for direction in ['STT', 'stt', 'Stt']:
        rules = parse_compact_rules(f'{direction} bag carrier')
        assert len(rules['stt']) == 1


def test_parse_skips_comments():
    """Test that comment lines are skipped."""
    text = '''# This is a comment
TTS bag carrier # real rule
# TTS commented out # disabled'''
    rules = parse_compact_rules(text)
    assert len(rules['tts']) == 1
    assert len(rules['stt']) == 0


def test_parse_skips_empty_lines():
    """Test that empty lines are skipped."""
    text = '''TTS bag carrier

TTS foo bar

'''
    rules = parse_compact_rules(text)
    assert len(rules['tts']) == 2


def test_parse_invalid_direction():
    """Test that invalid direction is rejected."""
    rules = parse_compact_rules('INVALID bag carrier')
    assert len(rules['tts']) == 0
    assert len(rules['stt']) == 0


def test_parse_insufficient_fields():
    """Test that rules with < 3 fields are rejected."""
    rules = parse_compact_rules('TTS bag')  # Only 2 fields
    assert len(rules['tts']) == 0
    assert len(rules['stt']) == 0


def test_manager_loads_from_env():
    """Test PronounceManager loads from environment variables."""
    # Save original env
    original = os.environ.get('VOICEMODE_PRONOUNCE')

    try:
        os.environ['VOICEMODE_PRONOUNCE'] = 'TTS bag carrier'
        manager = PronounceManager()
        assert len(manager.rules['tts']) == 1
        assert manager.rules['tts'][0].pattern == 'bag'
    finally:
        # Restore original env
        if original:
            os.environ['VOICEMODE_PRONOUNCE'] = original
        else:
            os.environ.pop('VOICEMODE_PRONOUNCE', None)


def test_manager_strips_quotes():
    """Test that manager strips quotes from env var values."""
    # Save original env
    original = os.environ.get('VOICEMODE_PRONOUNCE')

    try:
        # Simulate what .env file loading does - keeps quotes
        os.environ['VOICEMODE_PRONOUNCE'] = "'STT bag carrier'"
        manager = PronounceManager()
        assert len(manager.rules['stt']) == 1
        assert manager.rules['stt'][0].pattern == 'bag'

        # Test with double quotes
        os.environ['VOICEMODE_PRONOUNCE'] = '"STT bag carrier"'
        manager = PronounceManager()
        assert len(manager.rules['stt']) == 1
        assert manager.rules['stt'][0].pattern == 'bag'
    finally:
        # Restore original env
        if original:
            os.environ['VOICEMODE_PRONOUNCE'] = original
        else:
            os.environ.pop('VOICEMODE_PRONOUNCE', None)


def test_manager_multiple_env_vars():
    """Test loading from multiple VOICEMODE_PRONOUNCE_* variables."""
    # Save original env
    originals = {
        'VOICEMODE_PRONOUNCE': os.environ.get('VOICEMODE_PRONOUNCE'),
        'VOICEMODE_PRONOUNCE_TEST': os.environ.get('VOICEMODE_PRONOUNCE_TEST')
    }

    try:
        os.environ['VOICEMODE_PRONOUNCE'] = 'TTS bag carrier'
        os.environ['VOICEMODE_PRONOUNCE_TEST'] = 'STT carrier bag'
        manager = PronounceManager()
        assert len(manager.rules['tts']) == 1
        assert len(manager.rules['stt']) == 1
    finally:
        # Restore original env
        for key, value in originals.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)


def test_tts_processing():
    """Test TTS text processing."""
    # Save original env
    original = os.environ.get('VOICEMODE_PRONOUNCE')

    try:
        os.environ['VOICEMODE_PRONOUNCE'] = 'TTS bag carrier'
        manager = PronounceManager()

        result = manager.process_tts('where is my bag')
        assert result == 'where is my carrier'

        # Should not match partial words
        os.environ['VOICEMODE_PRONOUNCE'] = r'TTS \bbag\b carrier'
        manager = PronounceManager()
        result = manager.process_tts('bagging')
        assert result == 'bagging'  # Unchanged
    finally:
        # Restore original env
        if original:
            os.environ['VOICEMODE_PRONOUNCE'] = original
        else:
            os.environ.pop('VOICEMODE_PRONOUNCE', None)


def test_stt_processing():
    """Test STT text processing."""
    # Save original env
    original = os.environ.get('VOICEMODE_PRONOUNCE')

    try:
        os.environ['VOICEMODE_PRONOUNCE'] = 'STT bag carrier'
        manager = PronounceManager()

        result = manager.process_stt('where is my bag')
        assert result == 'where is my carrier'
    finally:
        # Restore original env
        if original:
            os.environ['VOICEMODE_PRONOUNCE'] = original
        else:
            os.environ.pop('VOICEMODE_PRONOUNCE', None)
