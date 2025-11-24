# Pronunciation Customization

VoiceMode allows you to customize how words and phrases are pronounced through pronunciation rules configured via environment variables.

## Quick Start

Add pronunciation rules to your `~/.voicemode/voicemode.env` file:

```bash
# Basic pronunciation rule
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Dog name'

# Multiple rules in one variable
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Dog name
TTS \b3M\b "three M" # Company name'

# Organize rules by category
export VOICEMODE_PRONOUNCE_NETWORKING='TTS \bPoE\b "P O E" # Power over Ethernet
TTS \bGbE\b "gigabit ethernet" # Network speed'

export VOICEMODE_PRONOUNCE_STT='STT "me tool" metool # Whisper correction'
```

## Format Specification

Each pronunciation rule follows this format:

```
DIRECTION pattern replacement # description
```

- **DIRECTION**: `TTS` (text-to-speech) or `STT` (speech-to-text)
- **pattern**: Regular expression pattern to match
- **replacement**: Text to replace the match with
- **description**: Optional comment describing the rule

### Field Details

#### Direction
- `TTS`: Applies before text is spoken (improves pronunciation)
- `STT`: Applies after speech is transcribed (corrects misheard words)
- Case insensitive: `TTS`, `tts`, and `Tts` all work

#### Pattern
- Standard Python regular expressions
- Use `\b` for word boundaries
- Use `\d+` for digits
- Use `()` for capture groups
- Quote patterns containing spaces

#### Replacement
- Plain text replacement
- Use `$1` or `\1` to reference capture groups
- Quote replacements containing spaces

#### Description
- Everything after `#` is treated as a comment
- Helps document why the rule exists
- Not processed by the system

## Examples

### Basic Word Replacement

```bash
# Replace "Tali" with phonetic pronunciation
TTS \bTali\b Tar-lee # Dog's name
```

### Company/Brand Names

```bash
# 3M company name
TTS \b3M\b "three M" # Avoid "3 million"

# AWS
TTS \bAWS\b "A W S" # Amazon Web Services
```

### Technical Acronyms

```bash
# Networking terms
TTS \bPoE\b "P O E" # Power over Ethernet
TTS \bTCP/IP\b "T C P I P" # Protocol
TTS \bSSH\b "S S H" # Secure Shell
```

### Units and Measurements

```bash
# Network speeds with capture groups
TTS \b(\d+(?:\.\d+)?)\s*GbE\b "$1 gigabit ethernet" # e.g., "2.5GbE"
TTS \b(\d+)\s*GB\b "$1 gigabytes" # Storage
```

### STT Corrections

```bash
# Fix common Whisper misrecognitions
STT "me tool" metool # Whisper hears this wrong
STT "cora 7" "Cora 7" # Fix capitalization
STT "(tally|tahlee|tolly)" Tali # Multiple variations
```

## Environment Variables

### Single Variable

Load all rules from one variable:

```bash
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Dog name
TTS \b3M\b "three M" # Company name
STT "me tool" metool # Correction'
```

### Multiple Variables

Organize rules by category using the `VOICEMODE_PRONOUNCE_*` pattern:

```bash
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Dog name'
export VOICEMODE_PRONOUNCE_NETWORKING='TTS \bPoE\b "P O E"'
export VOICEMODE_PRONOUNCE_TECH='TTS \bAWS\b "A W S"'
```

All variables matching `VOICEMODE_PRONOUNCE` or `VOICEMODE_PRONOUNCE_*` will be loaded and combined.

## Disabling Rules

Comment out rules with `#` to disable them:

```bash
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Active rule
# TTS \b3M\b "three M" # Disabled rule'
```

## Testing Rules

Test your pronunciation rules:

```python
from voice_mode.pronounce import PronounceManager

manager = PronounceManager()

# Test TTS processing
text = "Tali needs PoE for 2.5GbE"
result = manager.process_tts(text)
print(f"Input:  {text}")
print(f"Output: {result}")

# List all loaded rules
for rule in manager.list_rules():
    print(f"[{rule['direction'].upper()}] {rule['pattern']} → {rule['replacement']}")
    if rule['description']:
        print(f"  # {rule['description']}")
```

## Regex Tips

### Word Boundaries

Use `\b` to match whole words only:

```bash
# Matches "AWS" but not "JAWS"
TTS \bAWS\b "A W S"
```

### Case Insensitive

Patterns are case-sensitive by default. For case-insensitive matching, use `(?i)`:

```bash
TTS (?i)\baws\b "A W S" # Matches AWS, aws, Aws, etc.
```

### Capture Groups

Capture parts of the pattern and reuse them:

```bash
# Capture the number and preserve it
TTS \b(\d+)\s*GB\b "$1 gigabytes"
# "16GB" becomes "16 gigabytes"
```

### Multiple Alternatives

Match any of several variations:

```bash
STT "(tally|tahlee|tolly)" Tali # Matches any variation
```

## Common Use Cases

### Pet Names

```bash
TTS \bTali\b Tar-lee # Dog's name
TTS \bMochi\b Mow-chee # Cat's name
```

### Client/Company Names

```bash
# Maintain privacy - use generic names
TTS "Client A" "Acme Corporation" # Real name in speech
STT "Acme Corporation" "Client A" # Generic in transcripts
```

### Technical Terms

```bash
TTS \bPoE\+\b "P O E plus" # PoE+
TTS \bGbE\b "gigabit ethernet"
TTS \bNVMe\b "N V M E"
```

### Model Numbers

```bash
TTS \bU7\b "U seven" # UniFi model
TTS \bGPT-4\b "G P T four"
```

## Troubleshooting

### Rules Not Applying

1. Check regex syntax: Test patterns at https://regex101.com (Python flavor)
2. Verify quoting: Quote patterns/replacements with spaces
3. Check escape sequences: Use raw strings in shell: `export VAR=$'pattern'`
4. Enable logging: `export VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS=true`

### Escape Sequence Issues

In bash, backslashes can be tricky. Use one of these approaches:

```bash
# Method 1: Double backslashes
export VOICEMODE_PRONOUNCE='TTS \\bword\\b replacement'

# Method 2: Single quotes with escaped backslashes
export VOICEMODE_PRONOUNCE='TTS \bword\b replacement'

# Method 3: $'...' syntax (recommended)
export VOICEMODE_PRONOUNCE=$'TTS \\bword\\b replacement'
```

### Debugging

Enable pronunciation logging to see which rules are being applied:

```bash
export VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS=true
```

Then check the VoiceMode event logs at `~/.voicemode/logs/events/`.

## Configuration Location

Pronunciation rules should be defined in your voicemode configuration file:

- User-level: `~/.voicemode/voicemode.env`
- Project-level: `./.voicemode.env` (in your project directory)

The voicemode configuration system automatically loads these files and sets the environment variables.

## Migration from v5.x

If you used the old YAML-based pronunciation system:

**Old format** (`~/.voicemode/config/pronunciation.yaml`):
```yaml
tts_rules:
  - name: "tali_name"
    pattern: '\bTali\b'
    replacement: 'Tar-lee'
    description: "Dog's name"
```

**New format** (`~/.voicemode/voicemode.env`):
```bash
export VOICEMODE_PRONOUNCE='TTS \bTali\b Tar-lee # Dog name'
```

The new format is simpler, more flexible, and doesn't require separate YAML files.
