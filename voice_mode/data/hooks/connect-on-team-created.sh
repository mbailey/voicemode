#!/bin/bash
# VoiceMode Connect: PostToolUse hook for TeamCreate
# Sets up inbox-live symlink for message delivery.
# User registration happens via the MCP server's connect_status tool.
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

TEAM_DIR="$HOME/.claude/teams/$TEAM_NAME"

# Set up inbox-live symlink for message delivery
# The MCP server's connect_status tool handles user registration on the gateway
CONNECT_USER_DIR="$HOME/.voicemode/connect/users/$AGENT_NAME"
mkdir -p "$CONNECT_USER_DIR"

# Ensure the inboxes directory exists so is_subscribed() check passes
# (symlink target's parent must exist for the user to be considered subscribed)
INBOX_DIR="$TEAM_DIR/inboxes"
mkdir -p "$INBOX_DIR"
INBOX_TARGET="$INBOX_DIR/team-lead.json"
ln -sfn "$INBOX_TARGET" "$CONNECT_USER_DIR/inbox-live"
echo "Inbox-live: $CONNECT_USER_DIR/inbox-live -> $INBOX_TARGET" >> "$DEBUG_LOG"

echo "=== on-team-created.sh DONE ===" >> "$DEBUG_LOG"

# Tell the agent to register with the gateway via the MCP tool
echo "{\"systemMessage\": \"VoiceMode Connect inbox ready. Call connect_status(set_presence=\\\"available\\\", username=\\\"$AGENT_NAME\\\") to go available for voice calls.\"}"
exit 0
