#!/bin/bash

# VoiceMode Connect Standby Startup Script
# Runs voicemode connect standby on login to enable remote wake from iOS/web

# VoiceMode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/connect"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script (separate from connect logs)
STARTUP_LOG="$LOG_DIR/startup.log"

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sourcing voicemode.env" >> "$STARTUP_LOG"
    source "$VOICEMODE_DIR/voicemode.env"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: voicemode.env not found, using defaults" >> "$STARTUP_LOG"
fi

# Configuration from environment
WAKE_MESSAGE="${VOICEMODE_WAKE_MESSAGE:-}"
WAKE_COMMAND="${VOICEMODE_WAKE_COMMAND:-}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VoiceMode Connect standby" >> "$STARTUP_LOG"

# Build command arguments
CMD_ARGS=()

if [ -n "$WAKE_MESSAGE" ]; then
    CMD_ARGS+=(--wake-message "$WAKE_MESSAGE")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Wake message: $WAKE_MESSAGE" >> "$STARTUP_LOG"
fi

if [ -n "$WAKE_COMMAND" ]; then
    CMD_ARGS+=(--wake-command "$WAKE_COMMAND")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Wake command: $WAKE_COMMAND" >> "$STARTUP_LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Executing: voicemode connect standby ${CMD_ARGS[*]}" >> "$STARTUP_LOG"

# Start VoiceMode Connect standby
# Using exec to replace this script process with the connect command
# Use voicemode CLI command which is in ~/.local/bin (added to PATH by launchd plist)
exec voicemode connect standby "${CMD_ARGS[@]}"
