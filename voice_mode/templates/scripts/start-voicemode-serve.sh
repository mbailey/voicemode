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

# >>> voicemode_load_env_file — safe replacement for `source` (GHSA-h97v-r3jw-cf6f) >>>
# Load KEY=VALUE pairs from voicemode.env as INERT DATA. We must NOT `source`
# the file: bash runs command substitution even inside double quotes, so a
# value like VOICEMODE_VOICES='x$(rm -rf ~)' would execute as the service user
# on every start. This reader only ever assigns; it never evaluates the value.
voicemode_load_env_file() {
    local file="$1" line key val
    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        # Trim leading whitespace
        line="${line#"${line%%[![:space:]]*}"}"
        # Skip blank lines and comments
        if [ -z "$line" ]; then continue; fi
        case "$line" in '#'*) continue ;; esac
        # Require KEY=VALUE with a valid shell-identifier key
        case "$line" in [A-Za-z_]*=*) : ;; *) continue ;; esac
        key="${line%%=*}"
        case "$key" in *[!A-Za-z0-9_]*) continue ;; esac
        val="${line#*=}"
        # Strip ONE layer of surrounding quotes; contents are never expanded.
        # (Multiline-quoted values are read by the Python config loader, not
        # needed by this script — their continuation lines are skipped above.)
        case "$val" in
            \"*\") val="${val#\"}"; val="${val%\"}" ;;
            \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        export "$key=$val"
    done < "$file"
    return 0
}
# <<< voicemode_load_env_file <<<

# Load voicemode configuration if it exists (without executing it)
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loading voicemode.env" >> "$STARTUP_LOG"
    voicemode_load_env_file "$VOICEMODE_DIR/voicemode.env"
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
