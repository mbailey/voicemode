#!/bin/bash

# VoiceMode HTTP Server Startup Script
# This script is used by both macOS (launchd) and Linux (systemd) to start the VoiceMode HTTP server
# It sources the voicemode.env file to get configuration for VOICEMODE_SERVE_* variables

# VoiceMode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/serve"

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
SERVE_HOST="${VOICEMODE_SERVE_HOST:-127.0.0.1}"
SERVE_PORT="${VOICEMODE_SERVE_PORT:-8765}"
SERVE_TRANSPORT="${VOICEMODE_SERVE_TRANSPORT:-streamable-http}"
SERVE_LOG_LEVEL="${VOICEMODE_SERVE_LOG_LEVEL:-info}"

# Security configuration
SERVE_ALLOW_LOCAL="${VOICEMODE_SERVE_ALLOW_LOCAL:-true}"
SERVE_ALLOW_ANTHROPIC="${VOICEMODE_SERVE_ALLOW_ANTHROPIC:-false}"
SERVE_ALLOW_TAILSCALE="${VOICEMODE_SERVE_ALLOW_TAILSCALE:-false}"
SERVE_ALLOWED_IPS="${VOICEMODE_SERVE_ALLOWED_IPS:-}"
SERVE_SECRET="${VOICEMODE_SERVE_SECRET:-}"
SERVE_TOKEN="${VOICEMODE_SERVE_TOKEN:-}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VoiceMode HTTP server" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Host: $SERVE_HOST" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port: $SERVE_PORT" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Transport: $SERVE_TRANSPORT" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log level: $SERVE_LOG_LEVEL" >> "$STARTUP_LOG"

# Build command arguments
CMD_ARGS=(
    --host "$SERVE_HOST"
    --port "$SERVE_PORT"
    --transport "$SERVE_TRANSPORT"
    --log-level "$SERVE_LOG_LEVEL"
)

# Add security flags based on configuration
if [ "$SERVE_ALLOW_LOCAL" = "true" ]; then
    CMD_ARGS+=(--allow-local)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Allowing local connections" >> "$STARTUP_LOG"
else
    CMD_ARGS+=(--no-allow-local)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Blocking local connections" >> "$STARTUP_LOG"
fi

if [ "$SERVE_ALLOW_ANTHROPIC" = "true" ]; then
    CMD_ARGS+=(--allow-anthropic)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Allowing Anthropic IP ranges" >> "$STARTUP_LOG"
fi

if [ "$SERVE_ALLOW_TAILSCALE" = "true" ]; then
    CMD_ARGS+=(--allow-tailscale)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Allowing Tailscale IP range" >> "$STARTUP_LOG"
fi

# Add custom allowed IPs if configured (comma-separated list)
if [ -n "$SERVE_ALLOWED_IPS" ]; then
    IFS=',' read -ra IP_ARRAY <<< "$SERVE_ALLOWED_IPS"
    for ip in "${IP_ARRAY[@]}"; do
        # Trim whitespace
        ip=$(echo "$ip" | xargs)
        if [ -n "$ip" ]; then
            CMD_ARGS+=(--allow-ip "$ip")
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Allowing custom IP: $ip" >> "$STARTUP_LOG"
        fi
    done
fi

# Add authentication if configured
if [ -n "$SERVE_SECRET" ]; then
    CMD_ARGS+=(--secret "$SERVE_SECRET")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Secret path authentication enabled" >> "$STARTUP_LOG"
fi

if [ -n "$SERVE_TOKEN" ]; then
    CMD_ARGS+=(--token "$SERVE_TOKEN")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bearer token authentication enabled" >> "$STARTUP_LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Executing: voicemode serve ${CMD_ARGS[*]}" >> "$STARTUP_LOG"

# Start VoiceMode HTTP server
# Using exec to replace this script process with the server
# Use voicemode CLI command which is in ~/.local/bin (added to PATH by launchd plist)
exec voicemode serve "${CMD_ARGS[@]}"
