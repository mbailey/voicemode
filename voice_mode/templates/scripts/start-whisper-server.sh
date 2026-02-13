#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit

# Whisper Service Startup Script
# This script is used by both macOS (launchd) and Linux (systemd) to start the whisper service
# It sources the voicemode.env file to get configuration, especially VOICEMODE_WHISPER_MODEL
#
# Features:
# - Startup health check with 120s timeout
# - Auto-fallback: disables CoreML if server hangs during init
# - Thread count reduction when CoreML is active (commented out pending VM-642)

# Determine whisper directory (script is in bin/, whisper root is parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHISPER_DIR="$(dirname "$SCRIPT_DIR")"

# Voicemode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/whisper"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script (separate from whisper server logs)
STARTUP_LOG="$LOG_DIR/startup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$STARTUP_LOG"
}

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    log "Sourcing voicemode.env"
    source "$VOICEMODE_DIR/voicemode.env"
else
    log "Warning: voicemode.env not found"
fi

# Model selection with environment variable support
MODEL_NAME="${VOICEMODE_WHISPER_MODEL:-base}"
MODEL_PATH="$WHISPER_DIR/models/ggml-$MODEL_NAME.bin"

log "Starting whisper-server with model: $MODEL_NAME"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    log "Error: Model $MODEL_NAME not found at $MODEL_PATH"
    log "Available models:"
    ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\.bin$" >> "$STARTUP_LOG" || true

    # Try to find any available model as fallback
    FALLBACK_MODEL=$(ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\.bin$" | head -1)
    if [ -n "$FALLBACK_MODEL" ]; then
        MODEL_PATH="$WHISPER_DIR/models/$FALLBACK_MODEL"
        log "Using fallback model: $FALLBACK_MODEL"
    else
        log "Fatal: No whisper models found"
        exit 1
    fi
fi

# Port configuration (with environment variable support)
WHISPER_PORT="${VOICEMODE_WHISPER_PORT:-2022}"

# Thread configuration - auto-detect CPU cores if not specified
# Works on macOS, Linux, and WSL
if [ -n "${VOICEMODE_WHISPER_THREADS:-}" ]; then
    WHISPER_THREADS="$VOICEMODE_WHISPER_THREADS"
elif [ "$(uname -s)" = "Darwin" ]; then
    # macOS - use sysctl
    WHISPER_THREADS=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
else
    # Linux/WSL - use nproc
    WHISPER_THREADS=$(nproc 2>/dev/null || echo 4)
fi

# Thread capping when CoreML active — commented out pending VM-642 testing
# The whisper.cpp issue #779 suggests high thread counts conflict with CoreML,
# but we haven't confirmed this is needed. Uncomment if VM-642 testing shows it helps.
# See: https://github.com/ggml-org/whisper.cpp/issues/779
# COREML_MODEL_DIR="$WHISPER_DIR/models/ggml-${MODEL_NAME}-encoder.mlmodelc"
# if [ -d "$COREML_MODEL_DIR" ]; then
#     if [ "$WHISPER_THREADS" -gt 4 ]; then
#         log "CoreML model detected — capping threads at 4 (was $WHISPER_THREADS) to avoid ANE threading conflict"
#         WHISPER_THREADS=4
#     fi
# fi
log "Using $WHISPER_THREADS threads"

# Determine server binary location
# Check new CMake build location first, then legacy location
if [ -f "$WHISPER_DIR/build/bin/whisper-server" ]; then
    SERVER_BIN="$WHISPER_DIR/build/bin/whisper-server"
elif [ -f "$WHISPER_DIR/server" ]; then
    SERVER_BIN="$WHISPER_DIR/server"
else
    log "Error: whisper-server binary not found"
    log "Checked: $WHISPER_DIR/build/bin/whisper-server"
    log "Checked: $WHISPER_DIR/server"
    exit 1
fi

log "Using binary: $SERVER_BIN"
log "Model path: $MODEL_PATH"
log "Port: $WHISPER_PORT"

# CoreML model path (used by timeout fallback to disable CoreML if server hangs)
COREML_MODEL_DIR="$WHISPER_DIR/models/ggml-${MODEL_NAME}-encoder.mlmodelc"

# Startup timeout configuration
STARTUP_TIMEOUT="${VOICEMODE_WHISPER_STARTUP_TIMEOUT:-120}"
HEALTH_URL="http://127.0.0.1:${WHISPER_PORT}/health"

# Start whisper-server in background to monitor startup
cd "$WHISPER_DIR"
"$SERVER_BIN" \
    --host 0.0.0.0 \
    --port "$WHISPER_PORT" \
    --model "$MODEL_PATH" \
    --inference-path /v1/audio/transcriptions \
    --threads "$WHISPER_THREADS" \
    --convert &
SERVER_PID=$!

log "Started whisper-server (PID: $SERVER_PID), waiting for health check..."

# Poll health endpoint until ready or timeout
ELAPSED=0
while [ "$ELAPSED" -lt "$STARTUP_TIMEOUT" ]; do
    # Check if process is still alive
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        log "whisper-server process exited unexpectedly"
        wait "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi

    # Check if health endpoint responds
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        log "whisper-server is ready (took ${ELAPSED}s)"
        # Server is healthy — wait for it (keeps this script as the parent)
        wait "$SERVER_PID"
        exit $?
    fi

    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

# Timeout reached — server hung during initialization (likely CoreML ANE compilation)
log "WARNING: whisper-server failed to start within ${STARTUP_TIMEOUT}s"

# Kill the hung process
kill "$SERVER_PID" 2>/dev/null || true
sleep 1
kill -9 "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

# Disable CoreML model to prevent future hangs
if [ -d "$COREML_MODEL_DIR" ]; then
    log "Disabling CoreML model to prevent ANE compilation hang: $COREML_MODEL_DIR -> ${COREML_MODEL_DIR}.disabled"
    mv "$COREML_MODEL_DIR" "${COREML_MODEL_DIR}.disabled"
    # Reset thread count since CoreML is now disabled
    if [ "$(uname -s)" = "Darwin" ]; then
        WHISPER_THREADS=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
    else
        WHISPER_THREADS=$(nproc 2>/dev/null || echo 4)
    fi
    log "Restarting without CoreML (Metal acceleration only), threads: $WHISPER_THREADS"
else
    log "No CoreML model to disable — restarting with same configuration"
fi

# Restart whisper-server (exec replaces this script process)
exec "$SERVER_BIN" \
    --host 0.0.0.0 \
    --port "$WHISPER_PORT" \
    --model "$MODEL_PATH" \
    --inference-path /v1/audio/transcriptions \
    --threads "$WHISPER_THREADS" \
    --convert
