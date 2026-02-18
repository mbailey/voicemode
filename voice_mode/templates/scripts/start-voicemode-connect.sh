#!/bin/bash

# VoiceMode Connect Startup Script
# Runs voicemode connect up on login to enable remote voice from iOS/web

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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VoiceMode Connect" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Executing: voicemode connect up" >> "$STARTUP_LOG"

# Start VoiceMode Connect
# Using exec to replace this script process with the connect command
# Use voicemode CLI command which is in ~/.local/bin (added to PATH by launchd plist)
exec voicemode connect up
