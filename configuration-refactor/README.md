# Unified Configuration Enhancement

## Overview

Enhance and consolidate the existing environment variable configuration system for voice-mode, including core settings, Whisper configuration, and Kokoro configuration. Build upon the existing voicemode.env.example file to create a comprehensive configuration system that works seamlessly with MCP.

## Goals

1. **Enhanced Environment Variable System** - Build on existing VOICEMODE_* variables
2. **Service-Specific Settings** - Add Whisper and Kokoro configuration variables
3. **LLM Management Capability** - Enable the LLM to view and update configurations
4. **Always-Try-Local Behavior** - Implement resilient provider selection
5. **Best Practices** - Follow Unix conventions and MCP requirements

## Current State Analysis

### Existing Configuration Sources
1. **Environment Variables** (~30 VOICEMODE_* variables)
2. **Voice Preferences Files** (.voices.txt system - working well)
3. **Example Environment File** (voicemode.env.example - good foundation)
4. **Service Launch Configs** (launchd/systemd for Whisper/Kokoro)

### Key Areas to Address
- **Provider Resilience** - Always try local providers, don't mark as unavailable
- **Service Configuration** - Add Whisper/Kokoro specific env vars
- **Configuration Management** - Tools to read/update ~/.voicemode.env
- **Service Integration** - Pass env vars to launchd/systemd units
- **Documentation** - Clear guidance on configuration options

## Proposed Enhancements

### Configuration Location
- Primary config file: `~/.voicemode.env`
- Project overrides: `.voicemode.env` in project directory
- MCP reads these through standard environment

### New Environment Variables
```bash
# Whisper Configuration
VOICEMODE_WHISPER_MODEL=large-v2        # Whisper model to use
VOICEMODE_WHISPER_PORT=2022             # Whisper server port
VOICEMODE_WHISPER_LANGUAGE=auto         # Language for transcription
VOICEMODE_WHISPER_MODEL_PATH=~/.voicemode/models/whisper

# Kokoro Configuration  
VOICEMODE_KOKORO_PORT=8880              # Kokoro server port
VOICEMODE_KOKORO_MODELS_DIR=~/.voicemode/models/kokoro
VOICEMODE_KOKORO_CACHE_DIR=~/.voicemode/cache/kokoro
VOICEMODE_KOKORO_DEFAULT_VOICE=af_sky   # Default Kokoro voice

# Provider Behavior
VOICEMODE_ALWAYS_TRY_LOCAL=true         # Always attempt local providers
VOICEMODE_PROVIDER_RETRY_INTERVAL=5     # Seconds between retries
```

### Configuration Hierarchy (highest to lowest precedence)
1. **Per-request parameters** (tool invocation parameters)
2. **Environment variables** (VOICEMODE_* vars in shell)
3. **Project config** (.voicemode.env in project directory)
4. **User config** (~/.voicemode.env)
5. **System defaults** (built into code)

## Implementation Tasks

### Phase 1: Provider Resilience (Quick Win)
- [ ] Modify provider selection to always try local endpoints
- [ ] Remove "mark as unavailable" behavior for local providers
- [ ] Add VOICEMODE_ALWAYS_TRY_LOCAL environment variable
- [ ] Update provider discovery to respect retry behavior
- [ ] Test with local services up/down scenarios

### Phase 2: Configuration Enhancement
- [ ] Add Whisper-specific environment variables to voicemode.env.example
- [ ] Add Kokoro-specific environment variables to voicemode.env.example
- [ ] Create MCP resource: voicemode-config (shows all current config)
- [ ] Create MCP resource: whisper-config (shows Whisper settings)
- [ ] Create MCP resource: kokoro-config (shows Kokoro settings)

### Phase 3: Configuration Management
- [ ] Create MCP tool: update-config (updates ~/.voicemode.env)
- [ ] Create MCP tool: reload-config (sources updated config)
- [ ] Add config validation for service-specific settings
- [ ] Implement service restart helpers for config changes
- [ ] Document which settings require service restart

### Phase 4: Service Integration
- [ ] Update Whisper launchd/systemd units to read env vars
- [ ] Update Kokoro launchd/systemd units to read env vars
- [ ] Create helper scripts to inject env vars into services
- [ ] Add configuration templates for common scenarios
- [ ] Test end-to-end configuration updates

## Design Decisions

### Why Environment Variables?
- MCP works natively with environment variables
- Simple, Unix-standard approach
- Easy to source in shell and services
- No additional parsing complexity
- Existing voicemode.env.example is already well-structured

### Provider Resilience Strategy
- Always attempt configured providers in order
- Don't cache "unavailable" status for local services
- Provides seamless experience when services start/stop
- Configurable via VOICEMODE_ALWAYS_TRY_LOCAL

### Service Management
- Services read configuration from environment at startup
- LLM can update ~/.voicemode.env and restart services
- Clear documentation on which changes require restart
- Helper tools to make updates seamless

## Migration Path

1. **Phase 1**: Add new env vars to voicemode.env.example
2. **Phase 2**: Update documentation with new variables
3. **Phase 3**: Implement MCP resources and tools
4. **Phase 4**: Full integration with service management

## Security Considerations

- API keys remain in environment variables only
- Config files should have appropriate permissions (600)
- No secrets in MCP resources (only non-sensitive config)
- Audit trail for configuration changes via MCP tools

## Testing Strategy

- Test provider resilience with services up/down
- Validate all environment variables work correctly
- Test configuration updates through MCP tools
- Verify service restart behavior
- End-to-end testing of configuration changes

## Documentation Updates

- Update voicemode.env.example with all new variables
- Enhance configuration README with new options
- Add troubleshooting guide for configuration issues
- Document MCP tools for configuration management
- Create quick-start guide for common scenarios