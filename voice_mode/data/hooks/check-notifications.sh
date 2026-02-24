#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
# VoiceMode Connect: PostToolUse notification hook
# Checks agent inbox for pending messages and delivers them mid-conversation.
#
# Fires after tool use (filtered by matcher in JSON config).
# Rate-limited to avoid checking on every single tool call.

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

# Rate limit: skip if checked recently
RATE_LIMIT_SECONDS="${VOICEMODE_NOTIFICATION_INTERVAL:-30}"
LAST_CHECK_FILE="/tmp/voicemode-last-notification-check-${SESSION_ID}"

if [ -f "$LAST_CHECK_FILE" ]; then
  LAST_CHECK=$(cat "$LAST_CHECK_FILE")
  NOW=$(date +%s)
  ELAPSED=$((NOW - LAST_CHECK))
  if [ "$ELAPSED" -lt "$RATE_LIMIT_SECONDS" ]; then
    echo "Rate limited: ${ELAPSED}s < ${RATE_LIMIT_SECONDS}s" >> "$DEBUG_LOG"
    exit 0
  fi
fi

# Update last check timestamp
date +%s > "$LAST_CHECK_FILE"

# Resolve agent name from session identity file
SESSIONS_DIR="$HOME/.voicemode/sessions"
SESSION_FILE="$SESSIONS_DIR/${SESSION_ID}.json"
AGENT_NAME=""

if [ -f "$SESSION_FILE" ]; then
  AGENT_NAME=$(jq -r '.agent_name // empty' "$SESSION_FILE" 2>/dev/null)
fi

# Fallback to VOICEMODE_AGENT_NAME env var
if [ -z "$AGENT_NAME" ]; then
  AGENT_NAME="${VOICEMODE_AGENT_NAME:-}"
fi

if [ -z "$AGENT_NAME" ]; then
  echo "No agent name found for session $SESSION_ID" >> "$DEBUG_LOG"
  exit 0
fi

# Sanitize agent name
if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Invalid agent name '$AGENT_NAME', exiting" >> "$DEBUG_LOG"
  exit 0
fi

echo "=== check-notifications.sh $(date) session=$SESSION_ID agent=$AGENT_NAME ===" >> "$DEBUG_LOG"

# Check inbox for undelivered messages
INBOX_FILE="$HOME/.voicemode/connect/users/$AGENT_NAME/inbox"
DELIVERED_FILE="$HOME/.voicemode/connect/users/$AGENT_NAME/inbox.delivered"

if [ ! -f "$INBOX_FILE" ]; then
  echo "No inbox file" >> "$DEBUG_LOG"
  exit 0
fi

# Get the last delivered message ID (to only deliver new messages)
LAST_DELIVERED_ID=""
if [ -f "$DELIVERED_FILE" ]; then
  LAST_DELIVERED_ID=$(cat "$DELIVERED_FILE")
fi

# Read new messages from inbox (JSONL format)
# Skip delivery confirmations and already-delivered messages
MESSAGES=""
FOUND_LAST=false
if [ -z "$LAST_DELIVERED_ID" ]; then
  FOUND_LAST=true
fi

LATEST_ID=""
while IFS= read -r line; do
  [ -z "$line" ] && continue

  MSG_ID=$(echo "$line" | jq -r '.id // empty' 2>/dev/null)
  MSG_TYPE=$(echo "$line" | jq -r '.type // empty' 2>/dev/null)

  # Skip delivery confirmations
  [ "$MSG_TYPE" = "delivery_confirmation" ] && continue

  # Skip until we find the last delivered message
  if [ "$FOUND_LAST" = "false" ]; then
    if [ "$MSG_ID" = "$LAST_DELIVERED_ID" ]; then
      FOUND_LAST=true
    fi
    continue
  fi

  # Collect new message
  FROM=$(echo "$line" | jq -r '.from // "unknown"' 2>/dev/null)
  TEXT=$(echo "$line" | jq -r '.text // ""' 2>/dev/null)

  if [ -n "$TEXT" ]; then
    if [ -n "$MESSAGES" ]; then
      MESSAGES="${MESSAGES}\n---\n"
    fi
    MESSAGES="${MESSAGES}Message from ${FROM}: ${TEXT}"
    LATEST_ID="$MSG_ID"
  fi
done < "$INBOX_FILE"

if [ -z "$MESSAGES" ]; then
  echo "No new messages" >> "$DEBUG_LOG"
  exit 0
fi

echo "Found new messages, latest_id=$LATEST_ID" >> "$DEBUG_LOG"

# Mark messages as delivered
if [ -n "$LATEST_ID" ]; then
  echo "$LATEST_ID" > "$DELIVERED_FILE"
fi

# Escape the messages for JSON output
# Replace newlines with \n, escape quotes and backslashes
ESCAPED_MESSAGES=$(printf '%s' "$MESSAGES" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')

# Output hookSpecificOutput to deliver messages to agent context
cat <<HOOKEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "You have pending VoiceMode Connect notifications:\n${ESCAPED_MESSAGES}"}}
HOOKEOF

exit 0
