#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
# VoiceMode Connect: SessionStart hook
# Writes session identity file so notification hooks know which agent's inbox to check.
#
# Fires for ALL sessions but exits early if:
# - Connect not enabled
# - Not an agent session (no agent_type in stdin JSON)

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

echo "=== session-start.sh $(date) ===" >> "$DEBUG_LOG"

# Read hook input from stdin
INPUT=$(cat)
echo "Raw input: $INPUT" >> "$DEBUG_LOG"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)

# Exit early if not an agent session
if [ -z "$AGENT_TYPE" ]; then
  echo "No agent_type found, exiting early" >> "$DEBUG_LOG"
  exit 0
fi

# Exit early if no session ID
if [ -z "$SESSION_ID" ]; then
  echo "No session_id found, exiting early" >> "$DEBUG_LOG"
  exit 0
fi

echo "agent_type: $AGENT_TYPE, session_id: $SESSION_ID" >> "$DEBUG_LOG"

# Sanitize agent_type — only allow safe filesystem characters
if [[ ! "$AGENT_TYPE" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Invalid agent_type '$AGENT_TYPE', exiting" >> "$DEBUG_LOG"
  exit 0
fi

# Write session identity file so notification hooks can map session -> agent
SESSIONS_DIR="$HOME/.voicemode/sessions"
mkdir -p "$SESSIONS_DIR"

SESSION_FILE="$SESSIONS_DIR/${SESSION_ID}.json"
cat > "$SESSION_FILE" <<EOF
{"session_id":"$SESSION_ID","agent_name":"$AGENT_TYPE","created":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF

echo "Wrote session identity: $SESSION_FILE" >> "$DEBUG_LOG"

# Ensure inbox directory exists for this agent
INBOX_DIR="$HOME/.voicemode/connect/users/$AGENT_TYPE"
mkdir -p "$INBOX_DIR"
if [ ! -f "$INBOX_DIR/inbox" ]; then
  touch "$INBOX_DIR/inbox"
  echo "Created empty inbox: $INBOX_DIR/inbox" >> "$DEBUG_LOG"
fi

echo "=== session-start.sh DONE ===" >> "$DEBUG_LOG"

exit 0
