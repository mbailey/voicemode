#!/bin/bash

# Whisper Service Startup Script
# This script is used by both macOS (launchd) and Linux (systemd) to start the whisper service
# It sources the voicemode.env file to get configuration, especially VOICEMODE_WHISPER_MODEL

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

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sourcing voicemode.env" >> "$STARTUP_LOG"
    source "$VOICEMODE_DIR/voicemode.env"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: voicemode.env not found" >> "$STARTUP_LOG"
fi

# Model selection with environment variable support
MODEL_NAME="${VOICEMODE_WHISPER_MODEL:-base}"
MODEL_PATH="$WHISPER_DIR/models/ggml-$MODEL_NAME.bin"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting whisper-server with model: $MODEL_NAME" >> "$STARTUP_LOG"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error: Model $MODEL_NAME not found at $MODEL_PATH" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Available models:" >> "$STARTUP_LOG"
    ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\.bin$" >> "$STARTUP_LOG"
    
    # Try to find any available model as fallback
    FALLBACK_MODEL=$(ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\.bin$" | head -1)
    if [ -n "$FALLBACK_MODEL" ]; then
        MODEL_PATH="$WHISPER_DIR/models/$FALLBACK_MODEL"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using fallback model: $FALLBACK_MODEL" >> "$STARTUP_LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fatal: No whisper models found" >> "$STARTUP_LOG"
        exit 1
    fi
fi

# Port configuration (with environment variable support)
WHISPER_PORT="${VOICEMODE_WHISPER_PORT:-2022}"

# Determine server binary location
# Check new CMake build location first, then legacy location
if [ -f "$WHISPER_DIR/build/bin/whisper-server" ]; then
    SERVER_BIN="$WHISPER_DIR/build/bin/whisper-server"
elif [ -f "$WHISPER_DIR/server" ]; then
    SERVER_BIN="$WHISPER_DIR/server"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error: whisper-server binary not found" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checked: $WHISPER_DIR/build/bin/whisper-server" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checked: $WHISPER_DIR/server" >> "$STARTUP_LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using binary: $SERVER_BIN" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Model path: $MODEL_PATH" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port: $WHISPER_PORT" >> "$STARTUP_LOG"

# Start whisper-server
# Using exec to replace this script process with whisper-server
cd "$WHISPER_DIR"
exec "$SERVER_BIN" \
    --host 0.0.0.0 \
    --port "$WHISPER_PORT" \
    --model "$MODEL_PATH" \
    --inference-path /v1/audio/transcriptions \
    --threads 8