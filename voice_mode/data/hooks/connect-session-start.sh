#!/bin/bash
# VoiceMode Connect: SessionStart hook (settings.json)
# Cleans up stale team dir and prompts agent to create team for Connect
#
# Fires for ALL sessions but exits early if:
# - Not an agent session (no --agent flag)
# - voicemode command not available
# - Connect not enabled

set -euo pipefail

# Source voicemode config to get VOICEMODE_CONNECT_ENABLED
if [ -f "$HOME/.voicemode/voicemode.env" ]; then
  set -a
  source "$HOME/.voicemode/voicemode.env"
  set +a
fi

# Exit early if Connect is not enabled
if [ "${VOICEMODE_CONNECT_ENABLED:-false}" != "true" ]; then
  exit 0
fi

# Debug logging (only when VOICEMODE_DEBUG is enabled)
if [ "${VOICEMODE_DEBUG:-false}" = "true" ]; then
  DEBUG_LOG="$HOME/.voicemode/logs/connect-hook-debug.log"
  mkdir -p "$(dirname "$DEBUG_LOG")"
else
  DEBUG_LOG="/dev/null"
fi

echo "=== session-start.sh ENTRY $(date) ===" >> "$DEBUG_LOG"

# Read hook input from stdin
INPUT=$(cat)
echo "Raw input: $INPUT" >> "$DEBUG_LOG"
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)

# Exit early if not an agent session
if [ -z "$AGENT_TYPE" ]; then
  echo "No agent_type found, exiting early" >> "$DEBUG_LOG"
  exit 0
fi

echo "=== session-start.sh $(date) ===" >> "$DEBUG_LOG"
echo "agent_type: $AGENT_TYPE" >> "$DEBUG_LOG"

# Exit early if voicemode not installed
if ! command -v voicemode &>/dev/null; then
  echo "voicemode not found, skipping" >> "$DEBUG_LOG"
  exit 0
fi

# Use agent_type as the team/user name
AGENT_NAME="$AGENT_TYPE"

# Clean up old team dir so TeamCreate gets the exact name
TEAM_DIR="$HOME/.claude/teams/$AGENT_NAME"

if [ -L "$TEAM_DIR" ]; then
  # Symlink — resolve target, stale it, remove symlink
  TARGET=$(readlink -f "$TEAM_DIR" 2>/dev/null || readlink "$TEAM_DIR")
  echo "Found symlink: $TEAM_DIR -> $TARGET" >> "$DEBUG_LOG"
  if [ -d "$TARGET" ]; then
    mv "$TARGET" "${TARGET}.stale-$(date +%s)" 2>/dev/null || true
  fi
  rm -f "$TEAM_DIR"
elif [ -d "$TEAM_DIR" ]; then
  # Real directory — rename to stale
  mv "$TEAM_DIR" "${TEAM_DIR}.stale-$(date +%s)" 2>/dev/null || true
  echo "Staled: $TEAM_DIR" >> "$DEBUG_LOG"
fi

echo "Ready for TeamCreate with name: $AGENT_NAME" >> "$DEBUG_LOG"

# Plain text stdout is added to agent context for SessionStart hooks
# (systemMessage only shows in UI, not delivered to agent context)
echo "IMPORTANT: Create a team using TeamCreate with team_name '$AGENT_NAME'. This is required for VoiceMode Connect message delivery. Do this as your first action."

exit 0
