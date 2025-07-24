# Phase 1: Provider Resilience - Implementation Complete

## Overview

Implemented the always-try-local provider behavior to ensure local services (Whisper and Kokoro) are never permanently marked as unavailable when they temporarily fail.

## Changes Made

### 1. Added Environment Variable

**File:** `voice_mode/config.py`
- Added `VOICEMODE_ALWAYS_TRY_LOCAL` environment variable (default: true)
- This controls whether local providers should always be retried

```python
# Always try local providers (don't mark them as permanently unavailable)
ALWAYS_TRY_LOCAL = os.getenv("VOICEMODE_ALWAYS_TRY_LOCAL", "true").lower() in ("true", "1", "yes", "on")
```

### 2. Enhanced Provider Discovery

**File:** `voice_mode/provider_discovery.py`

#### Added Helper Function
```python
def is_local_provider(base_url: str) -> bool:
    """Check if a provider URL is for a local service."""
    provider_type = detect_provider_type(base_url)
    return provider_type in ["kokoro", "whisper", "local"] or \
           "127.0.0.1" in base_url or \
           "localhost" in base_url
```

#### Modified mark_unhealthy Method
- Now checks if ALWAYS_TRY_LOCAL is enabled
- For local providers, logs the error but keeps them marked as healthy
- Remote providers continue to be marked unhealthy as normal

```python
async def mark_unhealthy(self, service_type: str, base_url: str, error: str):
    """Mark an endpoint as unhealthy after a failure.
    
    If ALWAYS_TRY_LOCAL is enabled and the provider is local, it will not be
    permanently marked as unhealthy - it will be retried on next request.
    """
    if base_url in self.registry[service_type]:
        # Check if we should skip marking local providers as unhealthy
        if ALWAYS_TRY_LOCAL and is_local_provider(base_url):
            # Log the error but don't mark as unhealthy
            logger.info(f"Local {service_type} endpoint {base_url} failed ({error}) but will be retried (ALWAYS_TRY_LOCAL enabled)")
            # Update error and last check time for diagnostics, but keep healthy=True
            self.registry[service_type][base_url].error = f"{error} (will retry)"
            self.registry[service_type][base_url].last_health_check = datetime.now(timezone.utc).isoformat()
        else:
            # Normal behavior - mark as unhealthy
            self.registry[service_type][base_url].healthy = False
            self.registry[service_type][base_url].error = error
            self.registry[service_type][base_url].last_health_check = datetime.now(timezone.utc).isoformat()
            logger.warning(f"Marked {service_type} endpoint {base_url} as unhealthy: {error}")
```

### 3. Updated Documentation

**File:** `docs/configuration/voicemode.env.example`
- Added documentation for the new VOICEMODE_ALWAYS_TRY_LOCAL variable

```bash
## Always try local providers even if they previously failed (default: true)
## When true, local providers are never marked as permanently unavailable
# export VOICEMODE_ALWAYS_TRY_LOCAL=true
```

### 4. Created Comprehensive Tests

**File:** `tests/test_provider_resilience.py`
- Tests for local provider detection
- Tests for provider type detection
- Tests for resilience behavior with ALWAYS_TRY_LOCAL enabled/disabled
- Tests to ensure remote providers are still marked unhealthy normally

## Test Scenarios

### Scenario 1: Local Provider Temporarily Down
```
1. Kokoro service at http://127.0.0.1:8880/v1 is not running
2. Voice mode attempts to use Kokoro
3. Connection fails
4. With ALWAYS_TRY_LOCAL=true: Provider stays in healthy list, will be retried
5. User starts Kokoro service
6. Next request automatically uses Kokoro without any intervention
```

### Scenario 2: Remote Provider Fails
```
1. OpenAI API returns 401 (invalid API key)
2. Voice mode marks OpenAI as unhealthy
3. Falls back to local providers
4. OpenAI remains marked unhealthy until explicit health check
```

### Scenario 3: Mixed Provider Setup
```
1. Configure both local (Kokoro) and remote (OpenAI) TTS
2. Kokoro is preferred but not running
3. First request tries Kokoro (fails), falls back to OpenAI
4. Second request still tries Kokoro first (not marked unhealthy)
5. User starts Kokoro
6. Third request uses Kokoro successfully
```

## Benefits

1. **Seamless Experience** - Users can start/stop local services without voice mode marking them as permanently unavailable
2. **No Manual Intervention** - No need to restart voice mode or clear health status when local services come back online
3. **Configurable** - Can be disabled if users prefer the old behavior
4. **Backwards Compatible** - Default behavior maintains the resilient approach

## Configuration Examples

### Always retry local providers (default)
```bash
export VOICEMODE_ALWAYS_TRY_LOCAL=true
```

### Disable local provider resilience
```bash
export VOICEMODE_ALWAYS_TRY_LOCAL=false
```

### Use only local providers with resilience
```bash
export VOICEMODE_TTS_BASE_URLS="http://127.0.0.1:8880/v1"
export VOICEMODE_STT_BASE_URLS="http://127.0.0.1:2022/v1"
export VOICEMODE_ALWAYS_TRY_LOCAL=true
```

## Next Steps

With Phase 1 complete, the system now has resilient local provider handling. This sets the foundation for Phase 2: Configuration Enhancement, where we'll add Whisper and Kokoro specific environment variables.