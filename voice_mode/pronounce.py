"""
Pronunciation middleware for TTS and STT text processing.

This module provides regex-based text substitutions to improve TTS pronunciation
and correct STT transcription errors.

Format: DIRECTION pattern replacement # description
Example: TTS \bTali\b Tar-lee # Dog name
         STT \b3M\b "three M" # Company name
"""

import logging
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)


@dataclass
class PronounceRule:
    """A single pronunciation rule."""
    pattern: str
    replacement: str
    description: str = ""
    _compiled: Optional[re.Pattern] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Compile the regex pattern after initialization."""
        try:
            self._compiled = re.compile(self.pattern)
        except re.error as e:
            logger.error(f"Invalid regex pattern '{self.pattern}': {e}")
            self._compiled = None

    def apply(self, text: str) -> Tuple[str, bool]:
        """Apply this rule to text. Returns (modified_text, was_applied)."""
        if not self._compiled:
            return text, False

        original = text
        try:
            text = self._compiled.sub(self.replacement, text)
            return text, text != original
        except Exception as e:
            logger.error(f"Error applying rule '{self.pattern}': {e}")
            return original, False


def parse_compact_rules(text: str) -> Dict[str, List[PronounceRule]]:
    """
    Parse pronunciation rules from compact format.

    Format: DIRECTION pattern replacement # description
    - Lines starting with # are comments (disabled rules)
    - Direction must be TTS or STT
    - Pattern and replacement can be quoted for spaces
    - Everything after # is the description

    Args:
        text: Multi-line string with pronunciation rules

    Returns:
        Dictionary with 'tts' and 'stt' lists of PronounceRule objects
    """
    rules = {'tts': [], 'stt': []}

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()

        # Skip empty lines and comment lines
        if not line or line.startswith('#'):
            continue

        # Split on # to separate rule from description
        parts = line.split('#', 1)
        rule_part = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        # Parse the rule part - split on whitespace but respect quotes
        # Use shlex for quote handling but keep backslashes raw
        try:
            tokens = shlex.split(rule_part, posix=False)
        except ValueError as e:
            logger.warning(f"Line {line_num}: Parse error in '{rule_part}': {e}")
            logger.warning(f"  Expected format: DIRECTION pattern replacement # description")
            logger.warning(f"  Example: TTS \\bword\\b replacement # comment")
            continue

        # Remove quotes from tokens but preserve content
        tokens = [t.strip('"').strip("'") for t in tokens]

        if len(tokens) < 3:
            logger.warning(f"Line {line_num}: Need at least 3 fields (direction, pattern, replacement), got {len(tokens)}")
            logger.warning(f"  Got: {rule_part}")
            logger.warning(f"  Expected format: DIRECTION pattern replacement # description")
            continue

        direction = tokens[0].lower()
        pattern = tokens[1]
        replacement = tokens[2]

        if direction not in ('tts', 'stt'):
            logger.warning(f"Line {line_num}: Direction must be TTS or STT (case insensitive), got '{tokens[0]}'")
            continue

        rule = PronounceRule(
            pattern=pattern,
            replacement=replacement,
            description=description
        )

        if rule._compiled:  # Only add if pattern compiled successfully
            rules[direction].append(rule)
        else:
            logger.warning(f"Line {line_num}: Invalid regex pattern '{pattern}'")

    return rules


class PronounceManager:
    """Manages pronunciation rules for TTS and STT corrections."""
    
    def __init__(self):
        """Initialize the pronunciation rule manager."""
        self.rules: Dict[str, List[PronounceRule]] = {
            'tts': [],
            'stt': []
        }
        self._load_all_rules()
    
    def _load_from_env_vars(self) -> List[str]:
        """Load pronunciation rules from environment variables.

        Looks for VOICEMODE_PRONOUNCE and VOICEMODE_PRONOUNCE_* variables.
        Returns list of rule texts to parse.
        """
        rule_texts = []

        # Collect all VOICEMODE_PRONOUNCE* environment variables
        for key, value in os.environ.items():
            if key == 'VOICEMODE_PRONOUNCE' or key.startswith('VOICEMODE_PRONOUNCE_'):
                if value.strip():
                    # Strip surrounding quotes if present (from .env file parsing)
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    rule_texts.append(value)

        return rule_texts
    
    def _load_all_rules(self):
        """Load rules from environment variables."""
        self.rules = {'tts': [], 'stt': []}

        # Load from environment variables
        rule_texts = self._load_from_env_vars()

        for rule_text in rule_texts:
            try:
                parsed_rules = parse_compact_rules(rule_text)
                self.rules['tts'].extend(parsed_rules['tts'])
                self.rules['stt'].extend(parsed_rules['stt'])
            except Exception as e:
                logger.error(f"Failed to parse pronunciation rules: {e}")

        logger.info(f"Loaded {len(self.rules['tts'])} TTS rules and {len(self.rules['stt'])} STT rules")
    
    def process_tts(self, text: str) -> str:
        """
        Apply TTS substitutions before speech generation.

        Args:
            text: Text to be spoken by TTS

        Returns:
            Modified text with pronunciation improvements
        """
        log_substitutions = os.environ.get('VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS', '').lower() == 'true'

        for rule in self.rules['tts']:
            original = text
            text, applied = rule.apply(text)
            if applied and log_substitutions:
                logger.info(f"Pronunciation TTS: {rule.pattern} → {rule.replacement}: \"{original}\" → \"{text}\"")

        return text

    def process_stt(self, text: str) -> str:
        """
        Apply STT corrections after transcription.

        Args:
            text: Text transcribed from speech

        Returns:
            Corrected text
        """
        log_substitutions = os.environ.get('VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS', '').lower() == 'true'

        for rule in self.rules['stt']:
            original = text
            text, applied = rule.apply(text)
            if applied and log_substitutions:
                logger.info(f"Pronunciation STT: {rule.pattern} → {rule.replacement}: \"{original}\" → \"{text}\"")

        return text

    def list_rules(self, direction: Optional[str] = None) -> List[dict]:
        """
        List all rules or rules for specific direction.

        Args:
            direction: 'tts', 'stt', or None for all

        Returns:
            List of rule dictionaries
        """
        rules = []

        directions = [direction] if direction else ['tts', 'stt']

        for dir in directions:
            if dir not in self.rules:
                continue

            for rule in self.rules[dir]:
                rules.append({
                    'direction': dir,
                    'pattern': rule.pattern,
                    'replacement': rule.replacement,
                    'description': rule.description
                })

        return rules
    
    def test_rule(self, text: str, direction: str = "tts") -> str:
        """Test what a text would become after applying rules."""
        if direction == 'tts':
            return self.process_tts(text)
        elif direction == 'stt':
            return self.process_stt(text)
        else:
            return text
    
    def reload_rules(self):
        """Reload all rules from environment variables."""
        self._load_all_rules()
        logger.info("Reloaded pronunciation rules")


# Global instance (lazy loaded)
_manager: Optional[PronounceManager] = None


def get_manager() -> PronounceManager:
    """Get or create the global pronunciation manager."""
    global _manager
    if _manager is None:
        _manager = PronounceManager()
    return _manager


def is_enabled() -> bool:
    """Check if pronunciation middleware is enabled."""
    return os.environ.get('VOICEMODE_PRONUNCIATION_ENABLED', 'true').lower() == 'true'