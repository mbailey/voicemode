#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit

# mlx-audio Service Startup Script
# Used by launchd on macOS (Apple Silicon only) to start the unified
# Whisper STT + Kokoro TTS + Qwen3-TTS clone-voice mlx-audio server.
#
# The mlx-audio venv lives at:
#   ~/.voicemode/services/mlx-audio/venv/
#
# Configuration is sourced from ~/.voicemode/voicemode.env if present.

# Determine install directory (script is in bin/, mlx-audio root is parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MLX_AUDIO_DIR="$(dirname "$SCRIPT_DIR")"

# Voicemode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/mlx-audio"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script (separate from server logs)
STARTUP_LOG="$LOG_DIR/startup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$STARTUP_LOG"
}

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    log "Sourcing voicemode.env"
    # shellcheck disable=SC1091
    source "$VOICEMODE_DIR/voicemode.env"
else
    log "Warning: voicemode.env not found, using defaults"
fi

# Configuration with environment variable support
MLX_AUDIO_HOST="${VOICEMODE_MLX_AUDIO_HOST:-127.0.0.1}"
MLX_AUDIO_PORT="${VOICEMODE_MLX_AUDIO_PORT:-8890}"

VENV_DIR="$MLX_AUDIO_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    log "Error: mlx-audio venv python not found at $PYTHON_BIN"
    log "Run: voicemode mlx_audio_install"
    exit 1
fi

log "Starting mlx-audio server"
log "  python: $PYTHON_BIN"
log "  host:   $MLX_AUDIO_HOST"
log "  port:   $MLX_AUDIO_PORT"

# exec into the server so launchd manages it directly
cd "$MLX_AUDIO_DIR"
exec "$PYTHON_BIN" -m mlx_audio.server \
    --host "$MLX_AUDIO_HOST" \
    --port "$MLX_AUDIO_PORT"
