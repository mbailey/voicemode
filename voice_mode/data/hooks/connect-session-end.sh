#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
# VoiceMode Connect: SessionEnd hook
# Cleans up session artifacts when a Claude Code session ends:
# 1. Removes inbox-live symlink IF this session owns it (is team lead)
# 2. Removes the session identity file
#
# Critical safety rules:
# - ONLY remove inbox-live if this session has a team_name (= created via TeamCreate = team lead)
# - ONLY remove inbox-live if the symlink points to THIS session's team inbox
# - Subagents/teammates do NOT have team_name in their session file, so they won't touch inbox-live
# - Always remove the session identity file (it's per-session, safe to clean up)

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

echo "=== connect-session-end.sh $(date) session=$SESSION_ID ===" >> "$DEBUG_LOG"

# Look up session identity file
SESSIONS_DIR="$HOME/.voicemode/sessions"
SESSION_FILE="$SESSIONS_DIR/${SESSION_ID}.json"

if [ ! -f "$SESSION_FILE" ]; then
  echo "No session file found: $SESSION_FILE — nothing to clean up" >> "$DEBUG_LOG"
  echo "=== connect-session-end.sh DONE (no session file) ===" >> "$DEBUG_LOG"
  exit 0
fi

# Read session data
AGENT_NAME=$(jq -r '.agent_name // empty' "$SESSION_FILE" 2>/dev/null)
TEAM_NAME=$(jq -r '.team_name // empty' "$SESSION_FILE" 2>/dev/null)

echo "Session data: agent_name=$AGENT_NAME, team_name=$TEAM_NAME" >> "$DEBUG_LOG"

# --- inbox-live cleanup (only if we're the team lead) ---
if [ -n "$TEAM_NAME" ] && [ -n "$AGENT_NAME" ]; then
  INBOX_LIVE="$HOME/.voicemode/connect/users/$AGENT_NAME/inbox-live"

  if [ -L "$INBOX_LIVE" ]; then
    CURRENT_TARGET=$(readlink "$INBOX_LIVE" 2>/dev/null || true)
    EXPECTED_TARGET="$HOME/.claude/teams/$TEAM_NAME/inboxes/team-lead.json"

    echo "inbox-live: $CURRENT_TARGET (expected: $EXPECTED_TARGET)" >> "$DEBUG_LOG"

    if [ "$CURRENT_TARGET" = "$EXPECTED_TARGET" ]; then
      rm "$INBOX_LIVE"
      echo "Removed inbox-live symlink (owned by this session's team: $TEAM_NAME)" >> "$DEBUG_LOG"
    else
      echo "inbox-live points to different team — leaving it alone" >> "$DEBUG_LOG"
    fi
  else
    echo "No inbox-live symlink found — nothing to clean up" >> "$DEBUG_LOG"
  fi
else
  if [ -z "$TEAM_NAME" ]; then
    echo "No team_name in session — not a team lead, skipping inbox-live cleanup" >> "$DEBUG_LOG"
  fi
  if [ -z "$AGENT_NAME" ]; then
    echo "No agent_name in session — skipping inbox-live cleanup" >> "$DEBUG_LOG"
  fi
fi

# --- Session file cleanup (always safe to remove our own) ---
rm "$SESSION_FILE"
echo "Removed session file: $SESSION_FILE" >> "$DEBUG_LOG"

echo "=== connect-session-end.sh DONE ===" >> "$DEBUG_LOG"

exit 0
