"""MCP tools for managing pronunciation rules."""

import json
import yaml
from typing import Optional, Literal, List, Dict

from voice_mode.server import mcp
from voice_mode.pronounce import get_manager, is_enabled


@mcp.tool()
async def pronounce(
    action: Literal["list", "add", "remove", "enable", "disable", "test", "reload"],
    pattern: Optional[str] = None,
    replacement: Optional[str] = None,
    rule_type: Literal["tts", "stt"] = "tts",
    description: Optional[str] = None,
    name: Optional[str] = None,
    test_text: Optional[str] = None
) -> str:
    """
    Manage pronunciation rules for TTS/STT text processing.
    
    This tool allows managing pronunciation rules that improve TTS pronunciation
    and correct STT transcription errors. Rules are applied automatically when
    text is processed.
    
    Actions:
    - list: Show all non-private rules (returns count of private rules)
    - add: Add a new rule (requires pattern, replacement, rule_type)
    - remove: Remove a rule by name (requires name, rule_type)
    - enable: Enable a disabled rule (requires name, rule_type)
    - disable: Disable an enabled rule (requires name, rule_type)
    - test: Test rules on text (requires test_text, rule_type)
    - reload: Reload rules from configuration files
    
    Examples:
    - List all TTS rules:
      pronunciation_rules(action="list", rule_type="tts")
    
    - Add a rule to pronounce "3M" correctly:
      pronunciation_rules(
          action="add",
          pattern=r"\b3M\b",
          replacement="three em",
          rule_type="tts",
          description="Pronounce 3M company name"
      )
    
    - Test how text would be pronounced:
      pronunciation_rules(
          action="test",
          test_text="I work at 3M",
          rule_type="tts"
      )
    
    - Correct common Whisper mishearing:
      pronunciation_rules(
          action="add",
          pattern="me tool",
          replacement="metool",
          rule_type="stt",
          description="Correct 'me tool' to 'metool'"
      )
    
    Args:
        action: The action to perform
        pattern: Regex pattern for add action
        replacement: Replacement text for add action
        rule_type: Type of rule (tts for text-to-speech, stt for speech-to-text)
        description: Human-readable description for add action
        name: Rule name for remove/enable/disable actions
        test_text: Text to test for test action
    
    Returns:
        Result of the action as a formatted string
    """
    manager = get_manager()
    
    if action == "list":
        # List rules (excluding private ones)
        all_rules = manager.list_rules(include_private=True)
        public_rules = manager.list_rules(include_private=False)
        
        # Filter by type if specified
        if rule_type:
            public_rules = [r for r in public_rules if r['direction'] == rule_type]
            all_rules = [r for r in all_rules if r['direction'] == rule_type]
        
        # Format the response
        if not public_rules:
            private_count = len(all_rules)
            if private_count > 0:
                return f"No public {rule_type} rules found. ({private_count} private rules hidden)"
            else:
                return f"No {rule_type} rules found."
        
        # Build response
        result = f"Pronunciation Rules ({rule_type.upper()}):\n\n"
        
        for rule in public_rules:
            status = "✓" if rule['enabled'] else "✗"
            result += f"{status} {rule['name']}: \n"
            result += f"  Pattern: {rule['pattern']}\n"
            result += f"  Replace: {rule['replacement']}\n"
            if rule['description']:
                result += f"  Desc: {rule['description']}\n"
            result += "\n"
        
        # Add private rule count if any
        private_count = len(all_rules) - len(public_rules)
        if private_count > 0:
            result += f"({private_count} private rules hidden from view)\n"
        
        return result
    
    elif action == "add":
        if not pattern or not replacement:
            return "Error: 'add' action requires pattern and replacement"
        
        success = manager.add_rule(
            direction=rule_type,
            pattern=pattern,
            replacement=replacement,
            name=name,
            description=description or "",
            enabled=True,
            private=False  # MCP-created rules are public
        )
        
        if success:
            return f"✓ Rule added successfully for {rule_type.upper()}"
        else:
            return "✗ Failed to add rule. Check if the regex pattern is valid."
    
    elif action == "remove":
        if not name:
            return "Error: 'remove' action requires rule name"
        
        success = manager.remove_rule(rule_type, name)
        
        if success:
            return f"✓ Rule '{name}' removed from {rule_type.upper()}"
        else:
            return f"✗ Rule '{name}' not found in {rule_type.upper()} rules (may be private)"
    
    elif action == "enable":
        if not name:
            return "Error: 'enable' action requires rule name"
        
        success = manager.enable_rule(rule_type, name)
        
        if success:
            return f"✓ Rule '{name}' enabled in {rule_type.upper()}"
        else:
            return f"✗ Failed to enable rule '{name}' (not found or private)"
    
    elif action == "disable":
        if not name:
            return "Error: 'disable' action requires rule name"
        
        success = manager.disable_rule(rule_type, name)
        
        if success:
            return f"✓ Rule '{name}' disabled in {rule_type.upper()}"
        else:
            return f"✗ Failed to disable rule '{name}' (not found or private)"
    
    elif action == "test":
        if not test_text:
            return "Error: 'test' action requires test_text"
        
        result = manager.test_rule(test_text, rule_type)
        
        if test_text != result:
            return f"Original: {test_text}\nModified: {result}\n\nRules were applied to transform the text."
        else:
            return f"No changes: {test_text}\n\nNo rules matched or all rules are disabled."
    
    elif action == "reload":
        manager.reload_rules()
        
        # Get counts
        all_rules = manager.list_rules(include_private=True)
        tts_count = len([r for r in all_rules if r['direction'] == 'tts'])
        stt_count = len([r for r in all_rules if r['direction'] == 'stt'])
        
        return f"✓ Pronunciation rules reloaded\nLoaded {tts_count} TTS rules and {stt_count} STT rules"
    
    else:
        return f"Error: Unknown action '{action}'. Use: list, add, remove, enable, disable, test, reload"


@mcp.tool()
async def pronounce_status() -> str:
    """
    Get the status of the pronunciation middleware.
    
    Shows whether pronunciation processing is enabled and provides
    statistics about loaded rules.
    
    Returns:
        Status information as a formatted string
    """
    enabled = is_enabled()
    manager = get_manager()
    
    # Get rule counts
    all_rules = manager.list_rules(include_private=True)
    public_rules = manager.list_rules(include_private=False)
    
    tts_all = len([r for r in all_rules if r['direction'] == 'tts'])
    tts_public = len([r for r in public_rules if r['direction'] == 'tts'])
    tts_enabled = len([r for r in all_rules if r['direction'] == 'tts' and r['enabled']])
    
    stt_all = len([r for r in all_rules if r['direction'] == 'stt'])
    stt_public = len([r for r in public_rules if r['direction'] == 'stt'])
    stt_enabled = len([r for r in all_rules if r['direction'] == 'stt' and r['enabled']])
    
    status = f"Pronunciation Middleware Status:\n"
    status += f"{'='*40}\n"
    status += f"Enabled: {'✓ Yes' if enabled else '✗ No'}\n\n"
    
    status += f"TTS Rules:\n"
    status += f"  Total: {tts_all} ({tts_public} public, {tts_all - tts_public} private)\n"
    status += f"  Enabled: {tts_enabled}\n\n"
    
    status += f"STT Rules:\n"
    status += f"  Total: {stt_all} ({stt_public} public, {stt_all - stt_public} private)\n"
    status += f"  Enabled: {stt_enabled}\n\n"
    
    status += f"Configuration:\n"
    import os
    log_enabled = os.environ.get('VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS', '').lower() == 'true'
    private_mode = os.environ.get('VOICEMODE_PRONUNCIATION_PRIVATE_MODE', '').lower() == 'true'
    
    status += f"  Logging: {'✓ Enabled' if log_enabled else '✗ Disabled'}\n"
    status += f"  Private Mode: {'✓ All rules private' if private_mode else '✗ Normal'}\n"
    
    # Show config file paths
    status += f"\nConfiguration Files:\n"
    for path in manager.config_paths:
        status += f"  - {path}\n"
    
    return status