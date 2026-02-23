#!/bin/bash
# VoiceMode Connect: SessionStart hook (settings.json)
# Prompts agent to create team for Connect message delivery
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

# Sanitize agent_type — only allow safe filesystem characters
if [[ ! "$AGENT_TYPE" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Invalid agent_type '$AGENT_TYPE', exiting" >> "$DEBUG_LOG"
  exit 0
fi

echo "Prompting agent to create team" >> "$DEBUG_LOG"

# Plain text stdout is added to agent context for SessionStart hooks
# (systemMessage only shows in UI, not delivered to agent context)
echo "Create a team using TeamCreate. This is required for VoiceMode Connect message delivery. Do this as your first action."

exit 0
