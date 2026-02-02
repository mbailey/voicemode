#!/bin/bash
# Cleanup script to prepare for fresh VoiceMode installation testing
# This script does NOT delete anything - it renames and disables instead
#
# Usage:
#   ./cleanup-for-reinstall.sh         # Dry run (shows what would happen)
#   ./cleanup-for-reinstall.sh --run   # Actually perform cleanup

set -euo pipefail

DRY_RUN=true
if [[ "${1:-}" == "--run" ]]; then
    DRY_RUN=false
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log() {
    echo "[cleanup] $1"
}

run_cmd() {
    if $DRY_RUN; then
        echo "[dry-run] Would run: $1"
    else
        log "Running: $1"
        eval "$1"
    fi
}

echo "=== VoiceMode Cleanup for Reinstall Testing ==="
echo "Timestamp: $TIMESTAMP"
if $DRY_RUN; then
    echo "Mode: DRY RUN (use --run to actually execute)"
else
    echo "Mode: LIVE RUN"
fi
echo ""

# 1. Stop systemd services (Linux)
if command -v systemctl &>/dev/null; then
    log "Checking systemd services..."
    for svc in whisper kokoro livekit; do
        if systemctl --user is-active --quiet "$svc" 2>/dev/null; then
            run_cmd "systemctl --user stop $svc"
        fi
        if systemctl --user is-enabled --quiet "$svc" 2>/dev/null; then
            run_cmd "systemctl --user disable $svc"
        fi
        if [[ -f "$HOME/.config/systemd/user/${svc}.service" ]]; then
            run_cmd "mv '$HOME/.config/systemd/user/${svc}.service' '$HOME/.config/systemd/user/${svc}.service.backup.$TIMESTAMP'"
        fi
    done
    run_cmd "systemctl --user daemon-reload"
fi

# 1b. Stop launchd services (macOS)
if command -v launchctl &>/dev/null; then
    log "Checking launchd services..."
    for svc in whisper kokoro livekit; do
        plist="$HOME/Library/LaunchAgents/com.voicemode.${svc}.plist"
        if [[ -f "$plist" ]]; then
            run_cmd "launchctl unload '$plist' 2>/dev/null || true"
            run_cmd "mv '$plist' '${plist}.backup.$TIMESTAMP'"
        fi
    done
fi

# 2. Uninstall voicemode package
log "Checking voicemode package..."
if command -v uv &>/dev/null; then
    if uv tool list 2>/dev/null | grep -q voicemode; then
        run_cmd "uv tool uninstall voicemode"
    else
        log "voicemode not installed via uv tool"
    fi
else
    log "uv not found, skipping package uninstall"
fi

# 3. Rename ~/.voicemode directory (NEVER delete!)
if [[ -d "$HOME/.voicemode" ]]; then
    log "Renaming ~/.voicemode..."
    run_cmd "mv '$HOME/.voicemode' '$HOME/.voicemode.backup.$TIMESTAMP'"
else
    log "~/.voicemode not found"
fi

# 4. Handle Claude Code MCP configuration
log "Checking Claude Code MCP configuration..."
CLAUDE_CONFIG="$HOME/.config/claude-code/settings.json"
if [[ -f "$CLAUDE_CONFIG" ]]; then
    if grep -q "voicemode\|voice-mode" "$CLAUDE_CONFIG"; then
        log "Found VoiceMode in Claude Code config: $CLAUDE_CONFIG"
        log "You may want to manually remove the voicemode MCP entry"
        if ! $DRY_RUN; then
            echo ""
            echo "WARNING: Claude Code config contains VoiceMode MCP entry."
            echo "You should manually edit: $CLAUDE_CONFIG"
            echo "And remove the voicemode/voice-mode MCP server entry."
            echo ""
        fi
    fi
fi

# Also check ~/.claude.json (older location)
CLAUDE_JSON="$HOME/.claude.json"
if [[ -f "$CLAUDE_JSON" ]]; then
    if grep -q "voicemode\|voice-mode" "$CLAUDE_JSON"; then
        log "Found VoiceMode in ~/.claude.json"
        log "You may want to manually remove the voicemode MCP entry"
    fi
fi

echo ""
echo "=== Cleanup Summary ==="
if $DRY_RUN; then
    echo "This was a DRY RUN. No changes were made."
    echo "Run with --run to actually perform cleanup."
else
    echo "Cleanup complete!"
    echo ""
    echo "Backups created with suffix: .backup.$TIMESTAMP"
    echo ""
    echo "To restore if needed:"
    echo "  mv ~/.voicemode.backup.$TIMESTAMP ~/.voicemode"
fi
