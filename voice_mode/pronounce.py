"""
Pronunciation middleware for TTS and STT text processing.

This module provides regex-based text substitutions to improve TTS pronunciation
and correct STT transcription errors.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)


@dataclass
class PronounceRule:
    """A single pronunciation rule."""
    name: str
    pattern: str
    replacement: str
    order: int = 100
    enabled: bool = True
    description: str = ""
    private: bool = True  # Default to private for security
    _compiled: Optional[re.Pattern] = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Compile the regex pattern after initialization."""
        try:
            self._compiled = re.compile(self.pattern)
        except re.error as e:
            logger.error(f"Invalid regex pattern in rule '{self.name}': {e}")
            self._compiled = None
    
    def apply(self, text: str) -> Tuple[str, bool]:
        """Apply this rule to text. Returns (modified_text, was_applied)."""
        if not self.enabled or not self._compiled:
            return text, False
        
        original = text
        try:
            text = self._compiled.sub(self.replacement, text)
            return text, text != original
        except Exception as e:
            logger.error(f"Error applying rule '{self.name}': {e}")
            return original, False


class PronounceManager:
    """Manages pronunciation rules for TTS and STT corrections."""
    
    def __init__(self, config_paths: Optional[List[Path]] = None):
        """
        Initialize the pronunciation rule manager.
        
        Args:
            config_paths: List of config file paths. If None, uses default locations.
        """
        self.rules: Dict[str, List[PronounceRule]] = {
            'tts': [],
            'stt': []
        }
        self.config_paths = config_paths or self._get_default_config_paths()
        self._load_all_rules()
    
    def _get_default_config_paths(self) -> List[Path]:
        """Get default configuration file paths."""
        paths = []
        
        # System defaults
        default_path = Path(__file__).parent / 'data' / 'default_pronunciation.yaml'
        if default_path.exists():
            paths.append(default_path)
        
        # User config
        user_config = Path.home() / '.voicemode' / 'config' / 'pronunciation.yaml'
        if user_config.exists():
            paths.append(user_config)
        
        # Project config (like Claude Code hooks)
        project_config = Path.cwd() / '.pronunciation.yaml'
        if project_config.exists():
            paths.append(project_config)
        
        # Environment variable paths
        env_paths = os.environ.get('VOICEMODE_PRONUNCIATION_CONFIG', '')
        if env_paths:
            for path_str in env_paths.split(':'):
                path = Path(path_str).expanduser()
                if path.exists():
                    paths.append(path)
        
        return paths
    
    def _load_all_rules(self):
        """Load rules from all configured paths."""
        self.rules = {'tts': [], 'stt': []}
        
        for config_path in self.config_paths:
            try:
                self._load_rules_from_file(config_path)
                logger.info(f"Loaded pronunciation rules from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load rules from {config_path}: {e}")
    
    def _load_rules_from_file(self, config_path: Path):
        """Load rules from a single YAML file."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if not config:
            return
        
        # Load TTS rules
        for rule_dict in config.get('tts_rules', []):
            rule = self._dict_to_rule(rule_dict)
            if rule:
                # Check for duplicate names and override
                self.rules['tts'] = [r for r in self.rules['tts'] if r.name != rule.name]
                self.rules['tts'].append(rule)
        
        # Load STT rules
        for rule_dict in config.get('stt_rules', []):
            rule = self._dict_to_rule(rule_dict)
            if rule:
                # Check for duplicate names and override
                self.rules['stt'] = [r for r in self.rules['stt'] if r.name != rule.name]
                self.rules['stt'].append(rule)
        
        # Sort rules by order
        self.rules['tts'].sort(key=lambda r: r.order)
        self.rules['stt'].sort(key=lambda r: r.order)
    
    def _dict_to_rule(self, rule_dict: dict) -> Optional[PronounceRule]:
        """Convert a dictionary to a PronounceRule."""
        try:
            return PronounceRule(
                name=rule_dict['name'],
                pattern=rule_dict['pattern'],
                replacement=rule_dict['replacement'],
                order=rule_dict.get('order', 100),
                enabled=rule_dict.get('enabled', True),
                description=rule_dict.get('description', ''),
                private=rule_dict.get('private', True)  # Default to private
            )
        except (KeyError, TypeError) as e:
            logger.error(f"Invalid rule configuration: {e}")
            return None
    
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
                logger.info(f"Pronunciation TTS: Applied rule '{rule.name}': \"{original}\" → \"{text}\"")
        
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
                logger.info(f"Pronunciation STT: Applied rule '{rule.name}': \"{original}\" → \"{text}\"")
        
        return text
    
    # CRUD Operations
    def add_rule(self, direction: str, pattern: str, replacement: str,
                 name: Optional[str] = None, description: str = "",
                 enabled: bool = True, order: int = 100,
                 private: bool = False) -> bool:
        """
        Add a new pronunciation rule.
        
        Args:
            direction: 'tts' or 'stt'
            pattern: Regex pattern to match
            replacement: Replacement text
            name: Rule name (auto-generated if not provided)
            description: Human-readable description
            enabled: Whether rule is active
            order: Processing order
            private: Whether rule is hidden from LLM
            
        Returns:
            True if rule was added successfully
        """
        if direction not in ['tts', 'stt']:
            logger.error(f"Invalid direction: {direction}")
            return False
        
        # Auto-generate name if not provided
        if not name:
            name = f"{direction}_rule_{len(self.rules[direction])}"
        
        # Check for duplicate names
        if any(r.name == name for r in self.rules[direction]):
            logger.error(f"Rule with name '{name}' already exists")
            return False
        
        rule = PronounceRule(
            name=name,
            pattern=pattern,
            replacement=replacement,
            order=order,
            enabled=enabled,
            description=description,
            private=private
        )
        
        if not rule._compiled:
            return False
        
        self.rules[direction].append(rule)
        self.rules[direction].sort(key=lambda r: r.order)
        
        # Save to user config
        self._save_user_rules()
        return True
    
    def remove_rule(self, direction: str, name: str) -> bool:
        """Remove a pronunciation rule by name."""
        if direction not in ['tts', 'stt']:
            return False
        
        original_count = len(self.rules[direction])
        self.rules[direction] = [r for r in self.rules[direction] if r.name != name]
        
        if len(self.rules[direction]) < original_count:
            self._save_user_rules()
            return True
        return False
    
    def list_rules(self, direction: Optional[str] = None, 
                   include_private: bool = False) -> List[dict]:
        """
        List all rules or rules for specific direction.
        
        Args:
            direction: 'tts', 'stt', or None for all
            include_private: Whether to include private rules (for CLI, not MCP)
            
        Returns:
            List of rule dictionaries
        """
        rules = []
        
        directions = [direction] if direction else ['tts', 'stt']
        
        for dir in directions:
            if dir not in self.rules:
                continue
            
            for rule in self.rules[dir]:
                # Skip private rules unless explicitly requested
                if rule.private and not include_private:
                    continue
                
                rules.append({
                    'direction': dir,
                    'name': rule.name,
                    'pattern': rule.pattern,
                    'replacement': rule.replacement,
                    'order': rule.order,
                    'enabled': rule.enabled,
                    'description': rule.description,
                    'private': rule.private
                })
        
        return rules
    
    def enable_rule(self, direction: str, name: str) -> bool:
        """Enable a specific rule."""
        if direction not in ['tts', 'stt']:
            return False
        
        for rule in self.rules[direction]:
            if rule.name == name:
                if rule.private:
                    logger.warning(f"Cannot enable private rule '{name}' via API")
                    return False
                rule.enabled = True
                self._save_user_rules()
                return True
        return False
    
    def disable_rule(self, direction: str, name: str) -> bool:
        """Disable a specific rule."""
        if direction not in ['tts', 'stt']:
            return False
        
        for rule in self.rules[direction]:
            if rule.name == name:
                if rule.private:
                    logger.warning(f"Cannot disable private rule '{name}' via API")
                    return False
                rule.enabled = False
                self._save_user_rules()
                return True
        return False
    
    def test_rule(self, text: str, direction: str = "tts") -> str:
        """Test what a text would become after applying rules."""
        if direction == 'tts':
            return self.process_tts(text)
        elif direction == 'stt':
            return self.process_stt(text)
        else:
            return text
    
    def reload_rules(self):
        """Reload all rules from configuration files."""
        self._load_all_rules()
        logger.info("Reloaded pronunciation rules")
    
    def _save_user_rules(self):
        """Save current rules to user config file."""
        user_config = Path.home() / '.voicemode' / 'config' / 'pronunciation.yaml'
        user_config.parent.mkdir(parents=True, exist_ok=True)
        
        # Only save non-default rules
        config = {
            'version': 1,
            'tts_rules': [],
            'stt_rules': []
        }
        
        for rule in self.rules['tts']:
            config['tts_rules'].append({
                'name': rule.name,
                'order': rule.order,
                'pattern': rule.pattern,
                'replacement': rule.replacement,
                'enabled': rule.enabled,
                'description': rule.description,
                'private': rule.private
            })
        
        for rule in self.rules['stt']:
            config['stt_rules'].append({
                'name': rule.name,
                'order': rule.order,
                'pattern': rule.pattern,
                'replacement': rule.replacement,
                'enabled': rule.enabled,
                'description': rule.description,
                'private': rule.private
            })
        
        with open(user_config, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Saved pronunciation rules to {user_config}")


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