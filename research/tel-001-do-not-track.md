# TEL-001: DO_NOT_TRACK and Telemetry Opt-Out Standards Research

**Date**: 2025-12-14
**Project**: VoiceMode Telemetry System
**Task**: VM-152 - Add telemetry and analytics system
**Author**: Research Report

## Executive Summary

This report examines the DO_NOT_TRACK environment variable standard and telemetry opt-out conventions for CLI tools. The findings recommend that VoiceMode implement a layered approach respecting both DO_NOT_TRACK (universal opt-out) and VOICEMODE_TELEMETRY (tool-specific control), with DO_NOT_TRACK taking precedence to honor user privacy preferences.

## 1. The DO_NOT_TRACK Environment Variable Standard

### 1.1 Overview

DO_NOT_TRACK is a proposed universal environment variable for CLI applications that mirrors the browser DNT (Do Not Track) HTTP header. It provides a single, standard way for users to opt out of telemetry across all supporting tools.

**Official Resources:**
- Primary specification: https://consoledonottrack.com/
- Additional documentation: https://do-not-track.dev/

### 1.2 Core Principle

From the Console Do Not Track proposal:

> "This is a proposal for a single, standard environment variable that plainly and unambiguously expresses LACK OF CONSENT by a user of that software to any non-essential-to-functionality requests of any kind to the creator of the software or other tracking services."

### 1.3 Accepted Values

**Implementation Pattern**: The standard specifies that DO_NOT_TRACK should be checked for **presence**, not a specific value.

According to the specification:
- **If the environment variable is set to any value**, telemetry should be disabled
- Common values used: `1`, `true`, or any non-empty string
- The mere presence of the variable indicates lack of consent

**Examples from the wild:**
```bash
DO_NOT_TRACK=1           # Most common
DO_NOT_TRACK=true        # Also acceptable
DO_NOT_TRACK=yes         # Also acceptable
DO_NOT_TRACK=anything    # Still indicates opt-out
```

### 1.4 Implementation Guidelines

**Basic check pattern:**
```python
import os

# Check if DO_NOT_TRACK is set (regardless of value)
if os.getenv('DO_NOT_TRACK'):
    # Disable all telemetry
    telemetry_enabled = False
```

**Important notes:**
- The presence of the variable is what matters, not its value
- An empty string (`DO_NOT_TRACK=`) may be interpreted differently by implementations
- Most tools treat any non-empty value as "do not track"

### 1.5 Relationship to Browser DNT Header

The browser DNT header historically used specific values:
- `"1"` = Do not track (DNT enabled)
- `"0"` = User consents to tracking
- `null` or `"unspecified"` = No preference set

However, the browser DNT specification has been **discontinued** as of 2024 because:
- It was a cooperative feature with no enforcement
- Advertisement websites ignored the header
- The mechanism design was fundamentally flawed

The CLI DO_NOT_TRACK convention learned from this by making the semantics simpler: **presence = opt-out**.

## 2. Other Common Telemetry Opt-Out Conventions

### 2.1 The NO_COLOR Pattern

**Standard**: https://no-color.org/

NO_COLOR provides an analogous pattern for disabling ANSI color output:

> "All command-line software which outputs text with ANSI color added should check for the presence of a NO_COLOR environment variable that, when present (regardless of its value), prevents the addition of ANSI color."

**Key similarities to DO_NOT_TRACK:**
- Checks for **presence**, not specific value
- Universal standard across tools
- Simple, clear semantics

**Related standards:**
- `FORCE_COLOR` - Forces color output even when piped
- `CLICOLOR` / `CLICOLOR_FORCE` - Older color control variables

**Adoption**: NO_COLOR is widely adopted since util-linux version 2.41 and many other tools.

### 2.2 Tool-Specific Environment Variables

Most CLI tools use tool-specific environment variables following common naming patterns:

#### Pattern 1: `[TOOL]_TELEMETRY_OPTOUT`
```bash
DOTNET_CLI_TELEMETRY_OPTOUT=1           # .NET SDK
PP_TOOLS_TELEMETRY_OPTOUT=1             # Microsoft Power Platform
DOTNET_UPGRADEASSISTANT_TELEMETRY_OPTOUT=1  # .NET Upgrade Assistant
```

#### Pattern 2: `[TOOL]_TELEMETRY_DISABLED`
```bash
NEXT_TELEMETRY_DISABLED=1               # Next.js
GATSBY_TELEMETRY_DISABLED=1             # Gatsby
NUXT_TELEMETRY_DISABLED=1               # Nuxt.js
STORYBOOK_DISABLE_TELEMETRY=1           # Storybook
ASTRO_TELEMETRY_DISABLED=1              # Astro
TURBO_TELEMETRY_DISABLED=1              # Turbo (also supports DO_NOT_TRACK)
```

#### Pattern 3: `[TOOL]_DISABLE_[FEATURE]`
```bash
CDK_DISABLE_CLI_TELEMETRY=true          # AWS CDK (starting Dec 2025)
```

#### Pattern 4: `[TOOL]_NO_[FEATURE]`
```bash
HOMEBREW_NO_ANALYTICS=1                 # Homebrew
```

#### Pattern 5: `[TOOL]_SEND_ANONYMOUS_USAGE_STATS`
```bash
DBT_SEND_ANONYMOUS_USAGE_STATS=False    # dbt (also supports DO_NOT_TRACK)
```

**Common value conventions:**
- `1` or `true` for boolean variables
- Some tools accept any truthy value
- Case sensitivity varies by tool

### 2.3 Configuration File Methods

Many tools also support disabling telemetry via configuration files:

**AWS CDK**: `cdk.json` or `~/.cdk.json`
```json
{
  "cli-telemetry": false
}
```

**Google Cloud Cortex**: `config.json`
```json
{
  "allowTelemetry": false
}
```

**Google Cloud SDK**: Command-based config
```bash
gcloud config set disable_usage_reporting true
```

### 2.4 Command-Line Flags

Some tools offer per-invocation opt-out:

```bash
netlify --telemetry-disable          # Netlify CLI
turbo telemetry disable              # Turbo (persistent)
```

## 3. Examples of Popular CLI Tools

### 3.1 Tools Supporting DO_NOT_TRACK

| Tool | DO_NOT_TRACK Support | Tool-Specific Variable | Notes |
|------|---------------------|------------------------|-------|
| **dbt** | Yes | `DBT_SEND_ANONYMOUS_USAGE_STATS=False` | DO_NOT_TRACK=1 equivalent to DBT variable |
| **Turbo (Vercel)** | Yes | `TURBO_TELEMETRY_DISABLED=1` | Supports both standards |
| **vLLM** | Yes | `VLLM_DO_NOT_TRACK` | Checks both VLLM and generic DO_NOT_TRACK |
| **Meteor** | Yes | - | Any truthy value disables stats |
| **FerretDB** | Yes | - | Respects DO_NOT_TRACK flag |
| **Bun** | Yes | - | Respects DO_NOT_TRACK flag |

### 3.2 Tools NOT Supporting DO_NOT_TRACK (Yet)

| Tool | Tool-Specific Variable | GitHub Issues |
|------|------------------------|---------------|
| **npm** | - | [npm/feedback#481](https://github.com/npm/feedback/discussions/481) - Requested |
| **Netlify CLI** | `--telemetry-disable` flag | [netlify/cli#737](https://github.com/netlify/cli/issues/737) - Requested |
| **Homebrew** | `HOMEBREW_NO_ANALYTICS=1` | Pre-dates DO_NOT_TRACK standard |
| **Next.js** | `NEXT_TELEMETRY_DISABLED=1` | - |
| **AWS CDK** | `CDK_DISABLE_CLI_TELEMETRY=true` | Starting Dec 12, 2025 |

### 3.3 Tool Adoption Timeline

- **2017-2021**: Most tools used tool-specific variables only
- **2021**: Console Do Not Track standard proposed ([Hacker News discussion](https://news.ycombinator.com/item?id=27746587))
- **2022-2024**: Gradual adoption by newer tools
- **2024-2025**: Increasing awareness but still not universal

**Key insight**: DO_NOT_TRACK is gaining traction but is not yet universally adopted. Tools should support both DO_NOT_TRACK and their own tool-specific variables.

## 4. Recommended Precedence Rules for VoiceMode

### 4.1 Decision Hierarchy

Based on best practices and user expectations, VoiceMode should implement the following precedence:

```
1. DO_NOT_TRACK (if set) → ALWAYS disable telemetry
2. VOICEMODE_TELEMETRY (if set) → Explicit user preference
3. Interactive prompt (first run) → Opt-in consent
4. Default → Telemetry DISABLED (privacy-first)
```

### 4.2 Value Combination Matrix

| DO_NOT_TRACK | VOICEMODE_TELEMETRY | Resulting Behavior | Rationale |
|--------------|---------------------|-------------------|-----------|
| **Set** (any value) | Not set | DISABLED | Universal opt-out takes precedence |
| **Set** (any value) | `false` / `0` | DISABLED | Universal opt-out overrides tool preference |
| **Set** (any value) | `true` / `1` | DISABLED | Universal opt-out is strongest signal |
| Not set | `true` / `1` | ENABLED | Explicit opt-in honored |
| Not set | `false` / `0` | DISABLED | Explicit opt-out honored |
| Not set | Not set | **DISABLED** (default) | Privacy-first default |

### 4.3 Implementation Logic

```python
import os

def should_enable_telemetry() -> bool:
    """
    Determine if telemetry should be enabled based on environment
    and user preferences.

    Precedence:
    1. DO_NOT_TRACK - universal opt-out (highest priority)
    2. VOICEMODE_TELEMETRY - tool-specific preference
    3. Stored consent from interactive prompt
    4. Default to disabled (privacy-first)
    """
    # 1. Check DO_NOT_TRACK (any value means opt-out)
    if os.getenv('DO_NOT_TRACK'):
        return False

    # 2. Check tool-specific VOICEMODE_TELEMETRY
    voicemode_telemetry = os.getenv('VOICEMODE_TELEMETRY', '').lower()
    if voicemode_telemetry in ('1', 'true', 'yes', 'on'):
        return True
    if voicemode_telemetry in ('0', 'false', 'no', 'off'):
        return False

    # 3. Check stored user consent (from config file)
    stored_consent = get_stored_telemetry_consent()
    if stored_consent is not None:
        return stored_consent

    # 4. Default to disabled (privacy-first)
    return False
```

### 4.4 Configuration File Interaction

The configuration file should store explicit consent given via:
- Interactive prompt on first run
- `voicemode config set VOICEMODE_TELEMETRY true/false`
- Direct config file editing

**Priority order:**
1. Environment variable DO_NOT_TRACK (overrides everything)
2. Environment variable VOICEMODE_TELEMETRY (overrides config file)
3. Config file setting
4. Default (disabled)

This allows:
- Global opt-out via `DO_NOT_TRACK` in shell profile
- Per-session override via `VOICEMODE_TELEMETRY=true voicemode ...`
- Persistent preference via config file

## 5. Best Practices for Respecting User Privacy

### 5.1 GDPR Compliance Requirements

**Critical requirements for telemetry under GDPR:**

1. **Opt-in by Default**
   - Telemetry MUST be disabled by default
   - User must actively consent (opt-in), not just fail to opt-out
   - Pre-checked boxes are NOT compliant

2. **Informed Consent**
   - Clearly explain what data is collected
   - Explain specific purposes (vague purposes insufficient)
   - Show before collection begins

3. **Easy Revocation**
   - Disabling telemetry must be as easy as enabling it
   - Provide multiple methods (env var, config, command)

4. **Data Minimization**
   - Only collect data actually needed
   - Avoid collecting personally identifiable information (PII)

5. **Transparency**
   - Document telemetry in privacy policy
   - Make telemetry status visible to users

**Penalties**: GDPR violations can result in fines up to €20 million or 4% of annual worldwide turnover.

### 5.2 Privacy-First Principles

#### Data Collection Guidelines

**DO collect:**
- Anonymous usage statistics (command invoked, success/failure)
- Performance metrics (execution time, resource usage)
- Error types (not error messages with potential PII)
- Feature usage counts
- Python version, OS type (generalized)

**DO NOT collect:**
- File paths (may contain usernames)
- File contents or code snippets
- Error messages with stack traces (may contain paths/data)
- Environment variables (except telemetry-related)
- Network information beyond basic connectivity
- Usernames, emails, or any PII
- Git commit messages or branch names

#### Anonymization Strategies

1. **Hash user identifiers**: Use one-way hashes for any user/machine IDs
2. **Aggregate data**: Report counts, not individual events when possible
3. **Strip paths**: Remove or generalize file system paths
4. **Redact content**: Never include user data in telemetry payloads
5. **Session IDs**: Use random session IDs, not machine IDs

### 5.3 Transparency Best Practices

#### First-Run Experience

```
Welcome to VoiceMode!

VoiceMode collects anonymous usage data to help improve the tool.

What we collect:
  - Commands used and their success/failure
  - Performance metrics (execution time)
  - Error types (not your data or file paths)
  - Python and OS version

What we DON'T collect:
  - Your code, files, or file paths
  - Personal information
  - Environment variables

You can:
  - Opt in now (default: disabled)
  - Review privacy policy: https://voicemode.dev/privacy
  - Disable anytime: voicemode config set VOICEMODE_TELEMETRY false
  - Or set DO_NOT_TRACK=1 in your shell

Enable anonymous telemetry? [y/N]:
```

#### Status Visibility

Users should be able to check telemetry status:

```bash
$ voicemode telemetry status
Telemetry: DISABLED
Reason: DO_NOT_TRACK environment variable is set

$ voicemode telemetry status
Telemetry: ENABLED
Reason: User consent via interactive prompt (2024-12-14)
Override: Set DO_NOT_TRACK=1 or VOICEMODE_TELEMETRY=false
```

#### Documentation Requirements

1. **Privacy Policy**: Detailed data collection disclosure
2. **README**: Mention telemetry and how to disable
3. **Installation docs**: Explain opt-in process
4. **Config docs**: Document all telemetry controls
5. **Help text**: Include telemetry commands in `--help`

### 5.4 Technical Implementation Best Practices

#### Fail-Safe Defaults

```python
# If anything goes wrong detecting preferences, default to disabled
try:
    telemetry_enabled = should_enable_telemetry()
except Exception:
    telemetry_enabled = False  # Fail safe
```

#### Non-Blocking Telemetry

- Telemetry should NEVER slow down the tool
- Send asynchronously in background
- Set short timeouts (1-2 seconds max)
- Silently fail if endpoint unreachable
- Don't retry failed sends

#### Respect Network Conditions

- Check for connectivity before sending
- Respect offline mode
- Don't send over metered connections (if detectable)

#### Audit Trail

- Log when consent is given/revoked (locally)
- Include timestamp and method of consent
- Allow users to export their telemetry data

### 5.5 Ethical Considerations

1. **User Trust**: Respect DO_NOT_TRACK even when not legally required
2. **Progressive Disclosure**: Don't collect more data than initially disclosed
3. **Purpose Limitation**: Only use data for stated purposes
4. **Regular Review**: Audit collected data to ensure compliance
5. **Data Retention**: Delete old telemetry data (suggest 90-day retention)

## 6. Recommendations for VoiceMode

### 6.1 Implementation Checklist

- [ ] **Support DO_NOT_TRACK** (universal opt-out)
- [ ] **Support VOICEMODE_TELEMETRY** (tool-specific control)
- [ ] **Implement precedence**: DO_NOT_TRACK > VOICEMODE_TELEMETRY > config > default
- [ ] **Default to disabled** (privacy-first, GDPR-compliant)
- [ ] **Interactive opt-in prompt** on first run
- [ ] **Config file storage** for persistent preference
- [ ] **Status command**: `voicemode telemetry status`
- [ ] **Enable command**: `voicemode telemetry enable`
- [ ] **Disable command**: `voicemode telemetry disable`
- [ ] **Privacy policy** documentation
- [ ] **README section** about telemetry
- [ ] **Anonymize data** (hash IDs, strip paths)
- [ ] **Non-blocking sends** (async, short timeout)
- [ ] **Audit logging** (consent events)

### 6.2 Configuration Variables

Recommended environment variable naming:

```bash
# Primary control (tool-specific)
VOICEMODE_TELEMETRY=true|false|1|0

# Universal opt-out (respect this FIRST)
DO_NOT_TRACK=1

# Optional: telemetry endpoint override (for testing)
VOICEMODE_TELEMETRY_ENDPOINT=https://custom.endpoint/events

# Optional: debug telemetry without sending
VOICEMODE_TELEMETRY_DEBUG=1
```

### 6.3 Config File Schema

`~/.voicemode/config/config.yaml`:

```yaml
telemetry:
  enabled: false  # explicit user preference
  consent_date: "2024-12-14T10:30:00Z"  # when consent given
  consent_method: "interactive_prompt"  # or "config_set", "env_var"
  anonymous_id: "hash-of-machine-id"  # one-way hash for analytics

  # What to collect (granular control)
  collect:
    usage_stats: true
    performance_metrics: true
    error_types: true
    feature_usage: true
```

### 6.4 Testing Strategy

Test all combinations:

```bash
# Test DO_NOT_TRACK override
DO_NOT_TRACK=1 VOICEMODE_TELEMETRY=true voicemode test
# Expected: Telemetry DISABLED (DO_NOT_TRACK wins)

# Test explicit opt-in
VOICEMODE_TELEMETRY=true voicemode test
# Expected: Telemetry ENABLED

# Test explicit opt-out
VOICEMODE_TELEMETRY=false voicemode test
# Expected: Telemetry DISABLED

# Test default (no vars set)
voicemode test
# Expected: Telemetry DISABLED (privacy-first default)

# Test config file
voicemode config set VOICEMODE_TELEMETRY true
voicemode test
# Expected: Telemetry ENABLED

# Test env var override of config
VOICEMODE_TELEMETRY=false voicemode test
# Expected: Telemetry DISABLED (env var overrides config)
```

## 7. References and Further Reading

### Standards and Specifications
- [Console Do Not Track](https://consoledonottrack.com/) - Official DO_NOT_TRACK specification
- [DO_NOT_TRACK Dev](https://do-not-track.dev/) - Additional documentation
- [NO_COLOR Standard](https://no-color.org/) - Analogous standard for color output
- [FORCE_COLOR Standard](https://force-color.org/) - Related color control

### Community Discussions
- [Console Do Not Track - Hacker News](https://news.ycombinator.com/item?id=27746587) - Community discussion
- [npm DO_NOT_TRACK Discussion](https://github.com/npm/feedback/discussions/481) - Feature request
- [Netlify CLI Issue](https://github.com/netlify/cli/issues/737) - Support request
- [dbt-core Issue](https://github.com/dbt-labs/dbt-core/issues/3540) - Implementation

### Privacy and Compliance
- [Lawful Processing of Telemetry Data](https://www.activemind.legal/guides/telemetry-data/) - GDPR compliance guide
- [Best GDPR-Compliant Analytics Tools](https://posthog.com/blog/best-gdpr-compliant-analytics-tools) - Privacy-preserving alternatives
- [TelemetryDeck Privacy FAQ](https://telemetrydeck.com/docs/guides/privacy-faq/) - Privacy-first telemetry

### Implementation Examples
- [.NET SDK Telemetry](https://learn.microsoft.com/en-us/dotnet/core/tools/telemetry) - Microsoft's approach
- [AWS CDK Telemetry](https://docs.aws.amazon.com/cdk/v2/guide/cli-telemetry.html) - AWS implementation
- [dbt Anonymous Usage Stats](https://docs.getdbt.com/reference/global-configs/usage-stats) - dbt's documentation
- [Next.js Telemetry](https://nextjs.org/telemetry) - Vercel's approach

### Tools and Resources
- [toptout Repository](https://github.com/beatcracker/toptout) - Collection of telemetry opt-out methods
- [Telemetry Opt-Out Examples](https://makandracards.com/makandra/624560-disable-telemetry-various-open-source-tools-libraries) - Quick reference

## 8. Conclusion

The DO_NOT_TRACK standard provides a clear, universal mechanism for users to opt out of telemetry. While not yet universally adopted, it represents best practice for respecting user privacy preferences.

**Key takeaways for VoiceMode:**

1. **Respect DO_NOT_TRACK unconditionally** - This builds user trust and follows emerging standards
2. **Provide tool-specific control** - VOICEMODE_TELEMETRY for granular control
3. **Default to disabled** - Privacy-first and GDPR-compliant
4. **Be transparent** - Clear documentation and easy status checking
5. **Make it easy** - Multiple methods to enable/disable
6. **Fail safely** - When in doubt, disable telemetry

By implementing these standards, VoiceMode will respect user privacy, comply with regulations, and align with community best practices.

---

**Next Steps:**
1. Implement precedence logic in telemetry module
2. Add configuration file support for persistent preferences
3. Create interactive opt-in prompt
4. Document telemetry in README and privacy policy
5. Add telemetry status/enable/disable commands
6. Write comprehensive tests for all combinations
