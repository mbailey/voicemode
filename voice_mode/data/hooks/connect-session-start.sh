#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
# VoiceMode Connect: SessionStart hook
# Writes session identity file so notification hooks know which agent's inbox to check.
#
# Fires for ALL sessions but exits early if:
# - Connect not enabled
# - Not an agent session (no agent_type in stdin JSON and no fallback name)
#
# Identity resolution priority:
# 1. agent_type from SessionStart hook input (for --agent sessions)
# 2. VOICEMODE_AGENT_NAME from voicemode.env
# 3. VOICEMODE_CONNECT_USERNAME from voicemode.env
# No system username fallback — would create inbox for OS user, not useful for Connect

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

echo "=== session-start.sh $(date) ===" >> "$DEBUG_LOG"

# Read hook input from stdin
INPUT=$(cat)
echo "Raw input: $INPUT" >> "$DEBUG_LOG"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)

# Exit early if no session ID
if [ -z "$SESSION_ID" ]; then
  echo "No session_id found, exiting early" >> "$DEBUG_LOG"
  exit 0
fi

# Resolve agent name with fallback chain
AGENT_NAME=""
IDENTITY_SOURCE=""

if [ -n "$AGENT_TYPE" ]; then
  AGENT_NAME="$AGENT_TYPE"
  IDENTITY_SOURCE="agent_type"
elif [ -n "${VOICEMODE_AGENT_NAME:-}" ]; then
  AGENT_NAME="$VOICEMODE_AGENT_NAME"
  IDENTITY_SOURCE="VOICEMODE_AGENT_NAME"
elif [ -n "${VOICEMODE_CONNECT_USERNAME:-}" ]; then
  AGENT_NAME="$VOICEMODE_CONNECT_USERNAME"
  IDENTITY_SOURCE="VOICEMODE_CONNECT_USERNAME"
else
  # No identity available — exit early
  echo "No agent identity found, exiting early" >> "$DEBUG_LOG"
  exit 0
fi

# Normalize to lowercase
AGENT_NAME=$(echo "$AGENT_NAME" | tr '[:upper:]' '[:lower:]')

echo "agent_name: $AGENT_NAME (from $IDENTITY_SOURCE), session_id: $SESSION_ID" >> "$DEBUG_LOG"

# Sanitize agent name — only allow safe filesystem characters
if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Invalid agent name '$AGENT_NAME', exiting" >> "$DEBUG_LOG"
  exit 0
fi

# Write session identity file so notification hooks can map session -> agent
SESSIONS_DIR="$HOME/.voicemode/sessions"
mkdir -p "$SESSIONS_DIR"

SESSION_FILE="$SESSIONS_DIR/${SESSION_ID}.json"
CWD=$(pwd)
cat > "$SESSION_FILE" <<EOF
{"session_id":"$SESSION_ID","agent_name":"$AGENT_NAME","agent_type":"${AGENT_TYPE:-}","identity_source":"$IDENTITY_SOURCE","cwd":"$CWD","created":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF

echo "Wrote session identity: $SESSION_FILE" >> "$DEBUG_LOG"

# Ensure inbox directory exists for this agent
INBOX_DIR="$HOME/.voicemode/connect/users/$AGENT_NAME"
mkdir -p "$INBOX_DIR"
if [ ! -f "$INBOX_DIR/inbox" ]; then
  touch "$INBOX_DIR/inbox"
  echo "Created empty inbox: $INBOX_DIR/inbox" >> "$DEBUG_LOG"
fi

# Initialize delivery watermark to last message in inbox so old messages
# don't flood the agent on first notification check. Only NEW messages
# (arriving after this session starts) will be delivered.
DELIVERED_FILE="$INBOX_DIR/inbox.delivered"
if [ ! -f "$DELIVERED_FILE" ] && [ -s "$INBOX_DIR/inbox" ]; then
  # Get the last message ID from the inbox JSONL
  LAST_MSG_ID=$(tail -1 "$INBOX_DIR/inbox" | jq -r '.id // empty' 2>/dev/null)
  if [ -n "$LAST_MSG_ID" ]; then
    echo "$LAST_MSG_ID" > "$DELIVERED_FILE"
    echo "Initialized delivery watermark: $LAST_MSG_ID" >> "$DEBUG_LOG"
  fi
fi

# Clean up stale session files (older than 7 days)
find "$SESSIONS_DIR" -name "*.json" -mtime +7 -delete 2>/dev/null || true

echo "=== session-start.sh DONE ===" >> "$DEBUG_LOG"

exit 0
