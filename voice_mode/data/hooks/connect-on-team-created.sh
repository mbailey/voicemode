#!/bin/bash
# VoiceMode Connect: PostToolUse hook for TeamCreate (settings.json)
# Wires up inbox delivery and registers user with Connect gateway
#
# Reads team info from stdin (PostToolUse hook input JSON)
# The field is tool_response (not tool_output)

set -euo pipefail

DEBUG_LOG="/tmp/voicemode-connect-hook-debug.log"
echo "=== on-team-created.sh $(date) ===" >> "$DEBUG_LOG"

# Read hook input from stdin
INPUT=$(cat)
echo "$INPUT" | jq '.' >> "$DEBUG_LOG" 2>/dev/null || echo "$INPUT" >> "$DEBUG_LOG"

# Extract team name from tool_response
TEAM_NAME=""
for field in '.tool_response.team_name' '.tool_response.content.team_name'; do
  TEAM_NAME=$(echo "$INPUT" | jq -r "$field // empty" 2>/dev/null)
  [ -n "$TEAM_NAME" ] && break
done

# Fallback: extract from team_file_path
if [ -z "$TEAM_NAME" ]; then
  for field in '.tool_response.team_file_path' '.tool_response.content.team_file_path'; do
    TEAM_FILE_PATH=$(echo "$INPUT" | jq -r "$field // empty" 2>/dev/null)
    if [ -n "$TEAM_FILE_PATH" ]; then
      TEAM_NAME=$(basename "$(dirname "$TEAM_FILE_PATH")")
      break
    fi
  done
fi

echo "Extracted TEAM_NAME: '$TEAM_NAME'" >> "$DEBUG_LOG"

if [ -z "$TEAM_NAME" ]; then
  echo "Could not extract team name from hook input" >> "$DEBUG_LOG"
  echo '{"systemMessage": "WARNING: VoiceMode Connect setup incomplete — could not extract team name from TeamCreate response. Check /tmp/voicemode-connect-hook-debug.log"}'
  exit 0
fi

# Use team name as the agent/user name for Connect
AGENT_NAME="$TEAM_NAME"

# Try to get display name from agent type or env
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)
DISPLAY_NAME="${VOICEMODE_AGENT_NAME:-${AGENT_TYPE:-$AGENT_NAME}}"

TEAM_DIR="$HOME/.claude/teams/$TEAM_NAME"

# 1. Set up Connect user inbox directory
CONNECT_USER_DIR="$HOME/.voicemode/connect/users/$AGENT_NAME"
mkdir -p "$CONNECT_USER_DIR"

# 2. Symlink inbox-live to team leader inbox
INBOX_TARGET="$TEAM_DIR/inboxes/team-lead.json"
ln -sfn "$INBOX_TARGET" "$CONNECT_USER_DIR/inbox-live"
echo "Inbox-live: $CONNECT_USER_DIR/inbox-live -> $INBOX_TARGET" >> "$DEBUG_LOG"

# 3. Register with VoiceMode Connect (if connect up is running)
if command -v voicemode &>/dev/null; then
  voicemode connect user add "$AGENT_NAME" \
    --name "$DISPLAY_NAME" \
    --subscribe "$AGENT_NAME" 2>> "$DEBUG_LOG" || true
  echo "Registered: $AGENT_NAME ($DISPLAY_NAME)" >> "$DEBUG_LOG"
else
  echo "voicemode not found, skipping registration" >> "$DEBUG_LOG"
fi

echo "=== on-team-created.sh DONE ===" >> "$DEBUG_LOG"

echo "{\"systemMessage\": \"VoiceMode Connect inbox ready. Call connect_status(set_presence=\\\"available\\\") to go available for voice calls.\"}"
exit 0
