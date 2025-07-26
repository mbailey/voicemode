# Provider Registry Review and Refactor Proposal

## Current Issues

1. **Stale Health Status**: When Kokoro was stopped, the registry continued showing it as healthy (✅) because health checks are cached and not updated in real-time.

2. **OpenAI Marked as Failed**: The OpenAI endpoint was marked as failed (❌) from a previous attempt, even though it should have been available as a fallback.

3. **No Real-time Service Detection**: The registry doesn't detect when a local service is stopped/started without manual refresh.

4. **Overly Complex Health Management**: The current system maintains persistent health state that can become stale and cause failover issues.

5. **ALWAYS_TRY_LOCAL Interference**: When enabled (default), local services are never marked unhealthy, causing repeated failures instead of proper failover.

## Analysis of Current Implementation

### Provider Discovery (`provider_discovery.py`)
- Maintains a `ProviderRegistry` class with health status for each endpoint
- **Optimistic initialization**: All endpoints marked healthy on startup
- Health checks only performed on `_discover_endpoint()` calls
- Uses `mark_unhealthy()` to update status after failures
- **Key Issue**: `ALWAYS_TRY_LOCAL` config prevents local services from being marked unhealthy
- No automatic detection of service state changes

### Key Code Insights
1. **Optimistic Mode**: Registry initializes all endpoints as healthy without checking
2. **ALWAYS_TRY_LOCAL**: When enabled, local providers are never truly marked unhealthy:
   ```python
   if config.ALWAYS_TRY_LOCAL and is_local_provider(base_url):
       # Log error but keep healthy=True
       self.registry[service_type][base_url].error = f"{error} (will retry)"
   ```
3. **No Periodic Health Checks**: Health only updated on failures or manual refresh

### Failover Logic (`converse.py::text_to_speech_with_failover`)
- Tries initial provider if specified
- Falls back to endpoints in `TTS_BASE_URLS` order
- Marks endpoints as unhealthy on failure (but see ALWAYS_TRY_LOCAL issue)
- **Problem**: When Kokoro is stopped but still marked healthy, it tries and fails
- **Problem**: OpenAI marked unhealthy from previous failure, not retried

### Service Management
- Services can be started/stopped via the service tool
- Registry is not automatically notified of these changes
- Manual refresh required to update health status
- No integration between service state and registry state

## Root Cause Analysis

The failover issue occurred due to a combination of factors:

1. **Kokoro was stopped** but registry still showed it as healthy (optimistic initialization + no real-time updates)
2. **ALWAYS_TRY_LOCAL=true** prevented Kokoro from being marked unhealthy after failure
3. **OpenAI was previously marked unhealthy** and wasn't retried
4. **Result**: Both endpoints appeared unavailable, triggering "All TTS providers failed" error

## Proposed Refactor

### 1. Lightweight Health Checks
Instead of maintaining persistent health state, perform quick health checks on-demand:
- For local services: Quick TCP connection test (< 50ms)
- For remote services: Use cached results with short TTL (5 minutes)
- Remove complex health state management
- Remove ALWAYS_TRY_LOCAL logic - let failover work naturally

### 2. Service-Aware Registry
- Subscribe to service state changes from the service management system
- Automatically mark local services as unavailable when stopped
- Automatically mark local services as available when started
- Add hooks in service.py to notify registry

### 3. Simplified Failover
- Always try preferred provider first (no pre-filtering based on health)
- On failure, try next available endpoint
- Use exponential backoff for failed endpoints (reset after success)
- Better error aggregation when all fail

### 4. Real-time Status
- Quick status check before each request for local services
- Cached status with TTL for remote services
- Remove the need for manual registry refresh
- Clear separation between "temporarily down" vs "permanently failed"

## Implementation Steps

1. **Refactor ProviderRegistry**
   - Remove persistent health tracking
   - Add quick health check methods
   - Implement TTL-based caching for remote endpoints

2. **Integrate with Service Management**
   - Add registry update hooks to service start/stop
   - Notify registry of service state changes

3. **Simplify Failover Logic**
   - Remove dependency on pre-checked health status
   - Try endpoints in order with quick pre-flight checks
   - Better error messages on total failure

4. **Add Monitoring**
   - Log all failover attempts
   - Track success rates per endpoint
   - Provide clear diagnostics when all endpoints fail

## Benefits

1. **More Reliable**: Real-time service detection prevents stale health data
2. **Simpler**: Less state to manage, fewer edge cases
3. **Faster**: Quick pre-flight checks instead of complex health management
4. **Better UX**: Clear error messages and automatic recovery

## Next Steps

1. Review current provider_discovery.py implementation
2. Create proof-of-concept for lightweight health checks
3. Test failover scenarios with service start/stop
4. Implement service state integration
5. Update documentation