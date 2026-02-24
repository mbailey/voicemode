#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
# VoiceMode Connect: PostToolUse hook for TeamCreate
# Captures team_name from TeamCreate response and writes it to the session
# identity file. This enables connect_status to auto-discover the team
# and set up inbox-live symlink for wake-from-idle capability.
#
# The team_name is extracted from tool_response and stored at:
#   ~/.voicemode/sessions/{session_id}.json

# Source voicemode config
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

# Read hook input from stdin
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
  echo "No session_id, exiting" >> "$DEBUG_LOG"
  exit 0
fi

echo "=== on-team-created.sh $(date) session=$SESSION_ID ===" >> "$DEBUG_LOG"

# Extract team_name from tool_response
# TeamCreate returns: {"team_name": "cora", "team_file_path": "...", "lead_agent_id": "..."}
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

if [ -z "$TEAM_NAME" ]; then
  echo "Could not extract team_name from hook input" >> "$DEBUG_LOG"
  exit 0
fi

# Sanitize team name
if [[ ! "$TEAM_NAME" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Invalid team_name '$TEAM_NAME', exiting" >> "$DEBUG_LOG"
  exit 0
fi

echo "Captured team_name: $TEAM_NAME" >> "$DEBUG_LOG"

# Write team_name to session identity file
SESSIONS_DIR="$HOME/.voicemode/sessions"
SESSION_FILE="$SESSIONS_DIR/${SESSION_ID}.json"

if [ -f "$SESSION_FILE" ]; then
  # Add team_name to existing session file
  UPDATED=$(jq --arg tn "$TEAM_NAME" '. + {team_name: $tn}' "$SESSION_FILE" 2>/dev/null)
  if [ -n "$UPDATED" ]; then
    echo "$UPDATED" > "$SESSION_FILE"
    echo "Added team_name to session file: $SESSION_FILE" >> "$DEBUG_LOG"
  fi
else
  # Session file doesn't exist yet — create minimal one
  mkdir -p "$SESSIONS_DIR"
  cat > "$SESSION_FILE" <<EOF
{"session_id":"$SESSION_ID","team_name":"$TEAM_NAME","created":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
  echo "Created session file with team_name: $SESSION_FILE" >> "$DEBUG_LOG"
fi

echo "=== on-team-created.sh DONE ===" >> "$DEBUG_LOG"

# Output guidance for agent to go available
cat <<HOOKEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "VoiceMode Connect: Team created. You can now go available for voice calls with connect_status(set_presence=\\\"available\\\")."}}
HOOKEOF

exit 0
