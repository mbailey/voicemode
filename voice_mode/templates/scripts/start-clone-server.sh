#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit

# Clone TTS (Qwen3-TTS via mlx-audio) Service Startup Script
# Used by both macOS (launchd) and Linux (systemd) to start the clone TTS service
# Sources voicemode.env for configuration (port, model)
#
# Features:
# - Startup health check with 180s timeout (model loading can be slow)
# - Graceful error on non-Apple-Silicon hardware

# Determine clone directory (script is in bin/, clone root is parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLONE_DIR="$(dirname "$SCRIPT_DIR")"

# Voicemode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/clone"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script
STARTUP_LOG="$LOG_DIR/startup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$STARTUP_LOG"
}

# Check for Apple Silicon
ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
    log "ERROR: Clone TTS (mlx-audio) requires Apple Silicon (arm64). Detected: $ARCH"
    echo "ERROR: Clone TTS (mlx-audio) requires Apple Silicon (arm64). Detected: $ARCH" >&2
    exit 1
fi

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    log "Sourcing voicemode.env"
    source "$VOICEMODE_DIR/voicemode.env"
else
    log "Warning: voicemode.env not found"
fi

# Configuration from environment (with defaults)
CLONE_PORT="${VOICEMODE_CLONE_PORT:-8890}"
CLONE_MODEL="${VOICEMODE_CLONE_MODEL:-mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16}"

log "Starting clone TTS server"
log "Port: $CLONE_PORT"
log "Model: $CLONE_MODEL"

# Activate virtual environment
VENV_PATH="$CLONE_DIR/.venv"
if [ -f "$VENV_PATH/bin/activate" ]; then
    log "Activating venv: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
else
    log "Error: Virtual environment not found at $VENV_PATH"
    exit 1
fi

# Verify mlx-audio is installed
if ! python -c "import mlx_audio" 2>/dev/null; then
    log "Error: mlx-audio is not installed in the virtual environment"
    exit 1
fi

# Health check configuration
HEALTH_URL="http://127.0.0.1:${CLONE_PORT}/v1/models"
STARTUP_TIMEOUT="${VOICEMODE_CLONE_STARTUP_TIMEOUT:-180}"

# Start mlx-audio server in background to monitor startup
log "Launching mlx-audio server..."
cd "$CLONE_DIR"
python -m mlx_audio.server --port "$CLONE_PORT" &
SERVER_PID=$!

log "Started mlx-audio server (PID: $SERVER_PID), waiting for health check..."

# Poll health endpoint until ready or timeout
ELAPSED=0
while [ "$ELAPSED" -lt "$STARTUP_TIMEOUT" ]; do
    # Check if process is still alive
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        log "mlx-audio server process exited unexpectedly"
        wait "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi

    # Check if health endpoint responds
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        log "mlx-audio server is ready (took ${ELAPSED}s)"
        # Server is healthy -- wait for it (keeps this script as the parent)
        wait "$SERVER_PID"
        exit $?
    fi

    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

# Timeout reached
log "WARNING: mlx-audio server failed to start within ${STARTUP_TIMEOUT}s"

# Kill the hung process
kill "$SERVER_PID" 2>/dev/null || true
sleep 1
kill -9 "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

log "Server failed to start. Check logs for details."
exit 1
