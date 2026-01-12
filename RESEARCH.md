# VM-372 Research: Socket Wait/Retry Pattern for mpv-dj

## Executive Summary

This document captures the research findings for implementing a socket wait/retry pattern in mpv-dj. The goal is to handle the race condition between starting mpv and the IPC socket becoming available.

## Current Codebase Analysis

### mpv-dj Script Location
- **Path**: `skills/voicemode/bin/mpv-dj`
- **Lines of code**: ~703
- **Language**: Bash
- **Dependencies**: mpv, socat, python3 (for JSON history)

### Relevant Functions

#### 1. `is_running()` (line 73-74)
```bash
is_running() {
    [ -S "$SOCKET" ] && echo '{"command": ["get_property", "pid"]}' | socat - "$SOCKET" 2>/dev/null | grep -q '"error":"success"'
}
```
- Checks if socket file exists AND is responsive
- Uses socat for IPC communication
- Returns success if mpv responds with success

#### 2. `send_cmd()` (line 77-84)
```bash
send_cmd() {
    if ! is_running; then
        echo "Error: DJ is not running. Start with: mpv-dj play <file>"
        exit 1
    fi
    echo "$1" | socat - "$SOCKET"
}
```
- Validates mpv is running before sending commands
- Fails immediately if not running (no retry)

#### 3. `cmd_play()` (line 87-135)
```bash
cmd_play() {
    # ... argument parsing ...

    # Stop existing playback
    if is_running; then
        send_cmd '{"command": ["quit"]}' > /dev/null 2>&1 || true
        sleep 0.5
    fi

    # Start mpv in background
    mpv "${mpv_args[@]}" "$source" &> /dev/null &

    echo "Started playback: $source"
    # ... (no wait for socket!)
}
```
**Problem**: After `mpv ... &`, there's no wait for the socket to become available. Commands sent immediately after may fail.

#### 4. `cmd_mfp()` (line 138-199)
- Calls `cmd_play()` at the end
- Same issue - subsequent commands may race against socket availability

### Current Socket Configuration
```bash
SOCKET="/tmp/voicemode-mpv.sock"
```
- Fixed socket path
- No environment variable override currently

## Problem Statement

### Race Condition Scenario
1. User runs `mpv-dj mfp 49`
2. mpv-dj calls `cmd_play()` which starts mpv in background (`mpv ... &`)
3. Immediately after, code tries to interact with socket (or user runs another command)
4. Socket not ready yet -> command fails
5. User sees error, has to retry

### Affected Commands
- Any command run immediately after `play` or `mfp`
- `mpv-dj status` (via `is_running()` -> silent failure)
- `mpv-dj volume X` (fails with "DJ is not running")
- `mpv-dj next/prev` (chapter navigation fails)

## Reference Implementation: mpvc

From VM-370 research, mpvc uses this pattern:

```bash
mpvc_delay() { sleep "${1:-0.1}"; }
mpvc_wait()  {
    for i in $(seq 0 100); do
        mpvc_delay "${1:-}";
        [ -n "$(mpvc_get idle-active)" ] && break;
    done;
}
```

Key characteristics:
- 100 retry attempts
- 0.1s delay between attempts (configurable)
- 10 second maximum wait (100 * 0.1s)
- Tests for actual mpv response, not just socket file existence

## Integration Points

### Where to Add wait_for_socket()

1. **After `cmd_play()` starts mpv** (line 129)
   ```bash
   mpv "${mpv_args[@]}" "$source" &> /dev/null &
   # ADD: wait_for_socket here
   echo "Started playback: $source"
   ```

2. **In `cmd_mfp()`** - Inherits from cmd_play(), no additional changes needed

3. **In `cmd_play()` from mpv-dj-library** (line 392)
   - Calls `mpv-dj play`, so it inherits the fix

### Where NOT to Change

- `send_cmd()` - Should remain as-is (assumes socket is ready)
- `is_running()` - This IS the socket check, used by wait function
- `cmd_status()`, `cmd_pause()`, etc. - These assume mpv is already running

### Configuration Points

Current globals (line 26-31):
```bash
SOCKET="/tmp/voicemode-mpv.sock"
MFP_BASE_URL="https://datashat.net"
MFP_DIR="${HOME}/.voicemode/music-for-programming"
```

Proposed additions:
```bash
SOCKET_TIMEOUT="${MPV_SOCKET_TIMEOUT:-10}"      # Max wait in seconds
SOCKET_RETRY_DELAY="${MPV_SOCKET_DELAY:-0.1}"   # Delay between retries
```

## Constraints and Gotchas

### 1. Bash Arithmetic
Bash doesn't support floating-point arithmetic natively.
```bash
# Won't work:
local max_attempts=$((SOCKET_TIMEOUT / SOCKET_RETRY_DELAY))

# Solutions:
# A) Use seq for loop
for i in $(seq 0 100); do ...

# B) Calculate with bc
local max_attempts=$(echo "$SOCKET_TIMEOUT / $SOCKET_RETRY_DELAY" | bc)

# C) Hardcode 10 attempts per second (recommended)
local max_attempts=$((SOCKET_TIMEOUT * 10))
```

### 2. Exit Behavior
- `set -e` is enabled (line 20) - any failing command exits
- `is_running()` returns non-zero when mpv not running
- Need to handle this in the retry loop:
```bash
# Safe pattern:
if is_running; then
    return 0
fi
# Not: is_running && return 0  (would exit on failure)
```

### 3. Subshell vs Current Shell
mpv is started in background with `&`:
```bash
mpv "${mpv_args[@]}" "$source" &> /dev/null &
```
- This creates a subshell
- PID available via `$!` if needed
- No wait by default - parent continues immediately

### 4. Socket File vs Socket Responsiveness
- `[ -S "$SOCKET" ]` only checks if socket file exists
- File may exist but mpv may not be responding yet
- Must use IPC ping (like `is_running()`) for reliable check

### 5. Existing sleep in cmd_play
Line 114-115:
```bash
send_cmd '{"command": ["quit"]}' > /dev/null 2>&1 || true
sleep 0.5
```
- This waits 0.5s for mpv to quit before starting new instance
- New wait_for_socket should be AFTER starting new mpv, not here

### 6. Error Messages
Current error from `send_cmd()`:
```
Error: DJ is not running. Start with: mpv-dj play <file>
```
New timeout error should be distinct:
```
Error: mpv socket not ready after 10s
```

### 7. Testing Considerations
- `tests/test_mpv_dj_chapter_sync.sh` exists for chapter sync
- No existing tests for socket timing
- Manual testing recommended with slow startup scenarios
- Can test timeout with `MPV_SOCKET_TIMEOUT=1`

## Proposed Implementation

### New Function: wait_for_socket()

```bash
# Wait for mpv socket to be ready
# Returns 0 on success, 1 on timeout
wait_for_socket() {
    local max_attempts=$((SOCKET_TIMEOUT * 10))  # 10 per second
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

### Updated cmd_play()

```bash
cmd_play() {
    # ... existing code ...

    # Start mpv in background
    mpv "${mpv_args[@]}" "$source" &> /dev/null &

    # Wait for socket to be ready
    if ! wait_for_socket; then
        echo "Failed to start mpv"
        exit 1
    fi

    echo "Started playback: $source"
    # ... rest of function ...
}
```

### Optional: Standalone wait Command

```bash
# In command dispatch:
wait)
    check_socat
    if ! wait_for_socket; then
        exit 1
    fi
    echo "Socket ready"
    ;;
```

## Files to Modify

| File | Change |
|------|--------|
| `skills/voicemode/bin/mpv-dj` | Add wait_for_socket(), config vars, update cmd_play() |

## Files That Don't Need Changes

| File | Reason |
|------|--------|
| `skills/voicemode/bin/mpv-dj-library` | Uses mpv-dj play, inherits fix |
| `skills/voicemode/bin/mfp-rss-helper` | RSS parsing only, no socket interaction |
| Tests | May add new tests, but existing tests unaffected |

## Success Criteria

1. `mpv-dj mfp 49` works reliably on first try
2. `mpv-dj status` immediately after play shows correct info
3. Timeout produces clear error message
4. No regression in normal operation
5. Configurable via environment variables

## References

- [VM-370 mpvc research](../VM-370_research_review-mpvc-lwillettsmpvc-for-mpv-dj-feature-comparison/README.md) - Source of wait pattern
- [lwilletts/mpvc](https://github.com/lwilletts/mpvc) - Reference implementation
- [mpv IPC documentation](https://mpv.io/manual/stable/#json-ipc) - JSON IPC protocol
