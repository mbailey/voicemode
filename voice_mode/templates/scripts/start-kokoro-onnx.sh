#!/bin/bash

# Kokoro ONNX TTS Server Startup Script
# This script is used by both macOS (launchd) and Linux (systemd) to start the Kokoro ONNX server
# It sources the voicemode.env file to get configuration for VOICEMODE_KOKORO_ONNX_* variables

# VoiceMode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/kokoro-onnx"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script (separate from server logs)
STARTUP_LOG="$LOG_DIR/startup.log"

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sourcing voicemode.env" >> "$STARTUP_LOG"
    source "$VOICEMODE_DIR/voicemode.env"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: voicemode.env not found, using defaults" >> "$STARTUP_LOG"
fi

# Configuration with environment variable support (defaults match config.py)
KOKORO_ONNX_HOST="${VOICEMODE_KOKORO_ONNX_HOST:-0.0.0.0}"
KOKORO_ONNX_PORT="${VOICEMODE_KOKORO_ONNX_PORT:-8881}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Kokoro ONNX TTS server" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Host: $KOKORO_ONNX_HOST" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port: $KOKORO_ONNX_PORT" >> "$STARTUP_LOG"

# Check if kokoro-onnx is installed
if ! python3 -c "import kokoro_onnx" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error: kokoro-onnx not installed" >> "$STARTUP_LOG"
    echo "Please install with: pip install kokoro-onnx" >> "$STARTUP_LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Executing: uvicorn voice_mode.services.kokoro_onnx.server:app --host $KOKORO_ONNX_HOST --port $KOKORO_ONNX_PORT" >> "$STARTUP_LOG"

# Start Kokoro ONNX server using uvicorn
# Using exec to replace this script process with the server
exec python3 -m uvicorn voice_mode.services.kokoro_onnx.server:app \
    --host "$KOKORO_ONNX_HOST" \
    --port "$KOKORO_ONNX_PORT"
