#!/bin/bash

# Voice Mode Comparison Script
# Runs local voice mode vs OpenAI voice mode side-by-side for demo purposes
#
# This script creates two tmux panes above the current pane with different voice configurations:
# - Left pane: OpenAI (cloud-based TTS/STT)
# - Right pane: Local (Whisper + Kokoro)
#
# Usage: ./compare-voice-modes.sh [message]
#        message: Optional message to speak (default: provider-specific greeting)
#        (Must be run from within a tmux session)

# Get message from argument or use defaults
MESSAGE="${1:-}"

# Pane name identifiers
OPENAI_PANE_NAME="voice-compare-openai"
LOCAL_PANE_NAME="voice-compare-local"

# Check if we're in a tmux session
if [ -z "$TMUX" ]; then
  echo "❌ Error: This script must be run from within a tmux session"
  echo "   Start tmux first: tmux"
  exit 1
fi

echo "🎬 Starting voice mode comparison demo..."
echo ""

# Clean up existing comparison panes if they exist
EXISTING_PANES=$(tmux list-panes -F '#{pane_id} #{pane_title}' | grep -E "(${OPENAI_PANE_NAME}|${LOCAL_PANE_NAME})" | cut -d' ' -f1)
if [ -n "$EXISTING_PANES" ]; then
  echo "🧹 Cleaning up existing comparison panes..."
  for pane_id in $EXISTING_PANES; do
    tmux kill-pane -t "$pane_id" 2>/dev/null || true
  done
  sleep 0.2
fi

echo "Configuration:"
echo "  Top-left pane:     OpenAI (Cloud)"
echo "  Top-right pane:    Local (Whisper + Kokoro)"
echo "  Bottom pane:       Control/output (current)"
echo ""

# Get current pane ID
CURRENT_PANE="$(tmux display-message -p '#{pane_id}')"

# Split current pane horizontally (create top pane)
tmux split-window -v -b -p 75

# Get the new top pane ID
TOP_PANE="$(tmux display-message -p '#{pane_id}')"

# Split the top pane vertically to create left and right
tmux split-window -h -t "$TOP_PANE"

# Get the two pane IDs (after the split, we need to find them)
# The top-left will be the one we just split, top-right is the new one
PANES=($(tmux list-panes -F '#{pane_id}' | grep -v "$CURRENT_PANE"))
LEFT_PANE="${PANES[0]}"
RIGHT_PANE="${PANES[1]}"

# Name the panes so we can identify them later
tmux select-pane -t "$LEFT_PANE" -T "$OPENAI_PANE_NAME"
tmux select-pane -t "$RIGHT_PANE" -T "$LOCAL_PANE_NAME"

sleep 0.3

# Add visual separators to each pane
tmux send-keys -t "$LEFT_PANE" "clear && echo '╔════════════════════════════════════╗' && echo '║      OpenAI Voice Mode (Cloud)      ║' && echo '╚════════════════════════════════════╝' && echo ''" Enter
tmux send-keys -t "$RIGHT_PANE" "clear && echo '╔════════════════════════════════════╗' && echo '║    Local Voice Mode (Whisper+Kokoro)║' && echo '╚════════════════════════════════════╝' && echo ''" Enter

sleep 0.3

# Set default messages if not provided
if [ -z "$MESSAGE" ]; then
  OPENAI_MESSAGE='.cloud'
  LOCAL_MESSAGE='.voice'
else
  OPENAI_MESSAGE="$MESSAGE"
  LOCAL_MESSAGE="$MESSAGE"
fi

# Configuration for OpenAI (left pane)
# Forces OpenAI endpoints for both TTS and STT
OPENAI_CMD="VOICEMODE_TTS_BASE_URLS=https://api.openai.com/v1 VOICEMODE_STT_BASE_URLS=https://api.openai.com/v1 voicemode converse --transport local --message '$OPENAI_MESSAGE'"

# Configuration for Local (right pane)
# Uses local endpoints (defaults to Kokoro TTS + Whisper STT)
LOCAL_CMD="VOICEMODE_VOICES=af_sky voicemode converse --transport local --message '$LOCAL_MESSAGE'"

echo "⏳ Preparing both voice modes for simultaneous start..."
# Send commands to both panes without executing yet
tmux send-keys -t "$LEFT_PANE" "$OPENAI_CMD"
tmux send-keys -t "$RIGHT_PANE" "$LOCAL_CMD"

sleep 0.2

echo "▶️  Starting both voice modes simultaneously..."
# Execute both commands at the same time (minimize timing difference)
tmux send-keys -t "$LEFT_PANE" Enter
tmux send-keys -t "$RIGHT_PANE" Enter

sleep 0.5

echo ""
echo "✅ Both voice modes initialized!"
echo "📊 Comparison demo is running"
echo ""
echo "Pane IDs:"
echo "  • OpenAI (left):  $LEFT_PANE"
echo "  • Local (right):  $RIGHT_PANE"
echo "  • Control (this): $CURRENT_PANE"
echo ""
echo "📊 Metrics to observe:"
echo "  • Time to First Audio (TTFA) - shown in voice response timing"
echo "  • Total round-trip latency"
echo "  • STT processing time"
echo "  • Response generation time"
echo "  • Audio playback time"
echo ""
echo "Key advantages of local:"
echo "  ✓ Lower latency (no network round-trips)"
echo "  ✓ No bandwidth costs"
echo "  ✓ Full privacy (data stays local)"
echo "  ✓ Works offline"
echo ""
echo "👀 Both voice modes are now running above."
echo "💬 Speak naturally in either pane to test."
echo "⏹️  Press Ctrl+C in a pane to stop it, or run: tmux kill-pane -t PANE_ID"
echo ""
