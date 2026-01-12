# VM-372 Technical Specification: Socket Wait/Retry Pattern

## Overview

This specification defines the implementation of a socket wait/retry pattern in `mpv-dj` to handle the race condition between starting mpv and the IPC socket becoming available.

## Design Decision

**Strategy: Post-startup socket wait with configurable timeout**

Rationale:
- Proven pattern from mpvc (battle-tested in production)
- No new dependencies - reuses existing `is_running()` and `socat`
- Non-blocking for normal operation (socket usually ready in <100ms)
- Graceful degradation with clear error message on timeout
- Environment variable configuration for edge cases

## Components

### 1. Configuration Variables

**Location**: `skills/voicemode/bin/mpv-dj` (lines 26-31, after existing config)

```bash
# Socket wait configuration
SOCKET_TIMEOUT="${MPV_SOCKET_TIMEOUT:-10}"      # Max wait time in seconds
SOCKET_RETRY_DELAY="${MPV_SOCKET_DELAY:-0.1}"   # Delay between retries (seconds)
```

**Design notes**:
- 10 second default timeout covers slow systems/large playlists
- 0.1s retry delay balances responsiveness vs CPU usage
- Environment variables allow user override without code changes
- Variable names prefixed with `MPV_` for namespace clarity

### 2. wait_for_socket() Function

**Location**: `skills/voicemode/bin/mpv-dj` (after `send_cmd()` function, ~line 85)

```bash
# Wait for mpv socket to become ready
# Returns: 0 on success, 1 on timeout
wait_for_socket() {
    local max_attempts=$((SOCKET_TIMEOUT * 10))  # 10 attempts per second
    local attempt=0

    while [[ $attempt -lt $max_attempts ]]; do
        if is_running; then
            return 0
        fi
        sleep "$SOCKET_RETRY_DELAY"
        ((attempt++))
    done

    echo "Error: mpv socket not ready after ${SOCKET_TIMEOUT}s" >&2
    return 1
}
```

**Design notes**:
- Uses existing `is_running()` which checks both socket file AND IPC responsiveness
- `if is_running; then` pattern avoids `set -e` exit on false return
- Error message goes to stderr for proper stream separation
- Hardcoded 10 attempts/second avoids floating-point arithmetic issues in bash
- Loop counter with `((attempt++))` is POSIX-compliant and readable

### 3. cmd_play() Modification

**Location**: `skills/voicemode/bin/mpv-dj` line 129-131 (after mpv start)

**Before**:
```bash
    # Start mpv in background
    mpv "${mpv_args[@]}" "$source" &> /dev/null &

    echo "Started playback: $source"
```

**After**:
```bash
    # Start mpv in background
    mpv "${mpv_args[@]}" "$source" &> /dev/null &

    # Wait for socket to be ready
    if ! wait_for_socket; then
        echo "Failed to start mpv - socket not ready"
        exit 1
    fi

    echo "Started playback: $source"
```

**Design notes**:
- Wait happens AFTER `mpv &` but BEFORE success message
- User only sees "Started playback" after socket is confirmed ready
- Failure case has distinct error message from timeout message
- Exit 1 ensures calling scripts can detect failure

### 4. Optional: `mpv-dj wait` Command

**Location**: Command dispatch section (~line 650+)

```bash
wait)
    check_socat
    if ! wait_for_socket; then
        exit 1
    fi
    echo "Socket ready"
    ;;
```

**Purpose**: Manual command for scripts that start mpv independently

**Scope decision**: This is optional and can be deferred to a follow-up task if time is constrained.

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `skills/voicemode/bin/mpv-dj` | Modify | Add config vars, wait_for_socket(), update cmd_play() |

## Files NOT Changed

| File | Reason |
|------|--------|
| `skills/voicemode/bin/mpv-dj-library` | Uses `mpv-dj play`, inherits the fix automatically |
| `skills/voicemode/bin/mfp-rss-helper` | RSS parsing only, no socket interaction |
| `tests/test_mpv_dj_chapter_sync.sh` | Existing tests unaffected; may add new tests |

## Implementation Steps

1. **Add configuration variables** (2 lines)
   - Add `SOCKET_TIMEOUT` and `SOCKET_RETRY_DELAY` after existing globals

2. **Add `wait_for_socket()` function** (15 lines)
   - Place after `send_cmd()` function
   - Include inline comment explaining purpose

3. **Update `cmd_play()` to call wait** (5 lines)
   - Add wait call after `mpv ... &`
   - Add failure handling with exit

4. **Test manually**
   - Run `mpv-dj mfp 49` - should work reliably
   - Run `mpv-dj status` immediately after - should show info
   - Test timeout: `MPV_SOCKET_TIMEOUT=0.1 mpv-dj play ...`

5. **Commit changes**
   - Single commit: `feat(VM-372): add socket wait/retry pattern to mpv-dj`

## Testing Approach

### Manual Tests (Primary)

```bash
# Test 1: Normal startup
mpv-dj stop  # Ensure clean state
mpv-dj mfp 49
mpv-dj status  # Should show track info immediately

# Test 2: Rapid succession
mpv-dj stop && mpv-dj mfp 49 && mpv-dj status

# Test 3: Timeout behavior
MPV_SOCKET_TIMEOUT=0 mpv-dj mfp 49  # Should timeout immediately

# Test 4: No regression
mpv-dj volume 50
mpv-dj next
mpv-dj prev
mpv-dj pause
mpv-dj resume
mpv-dj stop
```

### Automated Tests (Optional/Future)

The existing `tests/test_mpv_dj_chapter_sync.sh` tests chapter sync functionality and should continue to pass. New automated tests for socket timing would require mocking mpv startup, which is complex for a bash script. Manual testing is sufficient for this feature.

## Rollback Plan

If issues arise:
1. Remove the `wait_for_socket` call from `cmd_play()`
2. Behavior returns to original (race condition present but rare)
3. No data migration or cleanup needed

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Commands wait for socket | `mpv-dj status` works immediately after `mpv-dj mfp` |
| Configurable timeout | `MPV_SOCKET_TIMEOUT=1 mpv-dj ...` uses 1s timeout |
| Configurable retry delay | `MPV_SOCKET_DELAY=0.5 mpv-dj ...` uses 0.5s delay |
| Clear timeout error | Timeout shows "Error: mpv socket not ready after Xs" |
| No regression | All existing commands work as before |

## Edge Cases Handled

1. **Socket exists but mpv crashed**: `is_running()` checks IPC response, not just socket file
2. **Rapid restarts**: `cmd_play()` already quits existing mpv and waits 0.5s
3. **User interrupt**: Ctrl+C during wait exits cleanly
4. **Slow systems**: 10s default timeout covers most scenarios
5. **set -e interaction**: `if is_running` pattern doesn't trigger exit on false

## References

- [RESEARCH.md](./RESEARCH.md) - Detailed codebase analysis
- [VM-370 mpvc research](../VM-370_research_review-mpvc-lwillettsmpvc-for-mpv-dj-feature-comparison/README.md) - Source of wait pattern
- [mpv IPC documentation](https://mpv.io/manual/stable/#json-ipc) - JSON IPC protocol
