#!/usr/bin/env python3
"""Quick test of the compact pronunciation format."""

import os
import sys

# Add voice_mode to path
sys.path.insert(0, '/Users/admin/Code/github.com/mbailey/voicemode')

from voice_mode.pronounce import parse_compact_rules, PronounceManager

def test_parser():
    """Test the compact format parser."""
    print("Testing compact format parser...\n")

    test_rules = """
    # This is a comment - disabled rule
    TTS \\bTali\\b Tar-lee # Dog name
    TTS \\b3M\\b "three M" # Company name
    STT "me tool" metool # Whisper correction
    # TTS \\btest\\b TEST # Disabled rule
    """

    rules = parse_compact_rules(test_rules)

    print(f"TTS rules: {len(rules['tts'])}")
    for rule in rules['tts']:
        print(f"  Pattern: {rule.pattern}")
        print(f"  Replacement: {rule.replacement}")
        print(f"  Description: {rule.description}")
        print()

    print(f"STT rules: {len(rules['stt'])}")
    for rule in rules['stt']:
        print(f"  Pattern: {rule.pattern}")
        print(f"  Replacement: {rule.replacement}")
        print(f"  Description: {rule.description}")
        print()

def test_manager():
    """Test the PronounceManager with environment variables."""
    print("\nTesting PronounceManager with environment variables...\n")

    # Set environment variables
    # Note: Each rule MUST start with TTS or STT direction
    os.environ['VOICEMODE_PRONOUNCE'] = 'TTS \\bTali\\b Tar-lee # Dog name'
    os.environ['VOICEMODE_PRONOUNCE_NETWORKING'] = '''TTS \\bPoE\\b "P O E" # Power over Ethernet
TTS \\bGbE\\b "gigabit ethernet" # Network speed'''

    print("Example of INCORRECT format (missing direction):")
    print("  WRONG: 'bag carrier # joke'")
    print("  RIGHT: 'TTS bag carrier # joke'")
    print()

    manager = PronounceManager()

    print(f"Loaded {len(manager.rules['tts'])} TTS rules")
    print(f"Loaded {len(manager.rules['stt'])} STT rules\n")

    # Test TTS processing
    test_text = "Tali needs PoE for 2.5GbE"
    result = manager.process_tts(test_text)
    print(f"TTS Input:  {test_text}")
    print(f"TTS Output: {result}\n")

    # List all rules
    print("All rules:")
    for rule in manager.list_rules():
        print(f"  [{rule['direction'].upper()}] {rule['pattern']} → {rule['replacement']}")
        if rule['description']:
            print(f"       # {rule['description']}")

if __name__ == '__main__':
    test_parser()
    test_manager()
