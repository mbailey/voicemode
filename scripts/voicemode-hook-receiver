#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
#
# voicemode-hook-receiver - Fast standalone hook receiver for Claude Code
#
# This is a high-performance alternative to 'voicemode claude hooks receiver'
# that avoids Python startup overhead (~700ms -> ~20ms).
#
# Usage:
#   # Called by Claude Code hooks (reads JSON from stdin)
#   echo '{"tool_name":"Task","hook_event_name":"PreToolUse","tool_input":{"subagent_type":"mama-bear"}}' | voicemode-hook-receiver
#
#   # Testing with debug output
#   VOICEMODE_HOOK_DEBUG=1 voicemode-hook-receiver --tool-name Task --event PreToolUse --subagent-type mama-bear
#
# Configuration:
#   VOICEMODE_SOUNDFONTS_ENABLED - Sound fonts enabled by default, set to 'false' to disable
#   VOICEMODE_HOOK_DEBUG - Set to '1' for debug output
#
# Sound file lookup order:
#   1. ~/.voicemode/soundfonts/current/{event}/{tool}/subagent/{subagent}.{mp3,wav}
#   2. ~/.voicemode/soundfonts/current/{event}/{tool}/default.{mp3,wav}
#   3. ~/.voicemode/soundfonts/current/{event}/default.{mp3,wav}
#   4. ~/.voicemode/soundfonts/current/fallback.{mp3,wav}

usage() {
  cat <<'EOF'
Usage: voicemode-hook-receiver [OPTIONS]

Fast standalone hook receiver for Claude Code.

This is a high-performance alternative to 'voicemode claude hooks receiver'
that avoids Python startup overhead (~700ms -> ~20ms).

Options:
    --tool-name NAME       Override tool name (for testing)
    --event EVENT          Override event (PreToolUse or PostToolUse)
    --subagent-type TYPE   Override subagent type (for testing)
    -d, --debug            Enable debug output
    -h, --help             Show this help message and exit

Environment:
    VOICEMODE_SOUNDFONTS_ENABLED   Sound fonts enabled by default, set to 'false' to disable
    VOICEMODE_HOOK_DEBUG           Set to '1' for debug output

When called by Claude Code, JSON is read from stdin.
EOF
}

# Check for help first
for arg in "$@"; do
  case "$arg" in
  -h | --help)
    usage
    exit 0
    ;;
  esac
done

DEBUG="${VOICEMODE_HOOK_DEBUG:-}"
SOUNDFONTS_BASE="$HOME/.voicemode/soundfonts/current"

debug() {
  [[ -n "$DEBUG" ]] && echo "[DEBUG] $*" >&2 || true
}

# Parse command line arguments
TOOL_NAME=""
EVENT=""
SUBAGENT_TYPE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
  --tool-name)
    TOOL_NAME="$2"
    shift 2
    ;;
  --event)
    EVENT="$2"
    shift 2
    ;;
  --subagent-type)
    SUBAGENT_TYPE="$2"
    shift 2
    ;;
  -d | --debug)
    DEBUG=1
    shift
    ;;
  *)
    shift
    ;;
  esac
done

# Read JSON from stdin if not a tty
if [[ ! -t 0 ]]; then
  # Read entire stdin
  JSON_INPUT=$(cat)
  debug "Received JSON: $JSON_INPUT"

  # Parse JSON using basic shell tools (jq if available, otherwise grep/sed)
  if command -v jq &>/dev/null; then
    [[ -z "$TOOL_NAME" ]] && TOOL_NAME=$(echo "$JSON_INPUT" | jq -r '.tool_name // "Task"')
    [[ -z "$EVENT" ]] && EVENT=$(echo "$JSON_INPUT" | jq -r '.hook_event_name // "PreToolUse"')
    if [[ -z "$SUBAGENT_TYPE" && "$TOOL_NAME" == "Task" ]]; then
      SUBAGENT_TYPE=$(echo "$JSON_INPUT" | jq -r '.tool_input.subagent_type // ""')
    fi
  else
    # Fallback: basic pattern matching (less robust but works without jq)
    if [[ -z "$TOOL_NAME" ]]; then
      TOOL_NAME=$(echo "$JSON_INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:.*"\([^"]*\)"/\1/' || echo "Task")
    fi
    if [[ -z "$EVENT" ]]; then
      EVENT=$(echo "$JSON_INPUT" | grep -o '"hook_event_name"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:.*"\([^"]*\)"/\1/' || echo "PreToolUse")
    fi
    if [[ -z "$SUBAGENT_TYPE" && "$TOOL_NAME" == "Task" ]]; then
      SUBAGENT_TYPE=$(echo "$JSON_INPUT" | grep -o '"subagent_type"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:.*"\([^"]*\)"/\1/' || echo "")
    fi
  fi
fi

# Apply defaults
TOOL_NAME="${TOOL_NAME:-Task}"
EVENT="${EVENT:-PreToolUse}"

debug "Processing: event=$EVENT, tool=$TOOL_NAME, subagent=$SUBAGENT_TYPE"

# Check if soundfonts are enabled
# First check env var, then check config file
soundfonts_enabled() {
  local enabled="${VOICEMODE_SOUNDFONTS_ENABLED:-}"

  # If env var is set, use it
  if [[ -n "$enabled" ]]; then
    [[ "$enabled" == "true" || "$enabled" == "1" || "$enabled" == "yes" || "$enabled" == "on" ]]
    return
  fi

  # Check voicemode.env config file
  local config_file="$HOME/.voicemode/voicemode.env"
  if [[ -f "$config_file" ]]; then
    enabled=$(grep -E '^VOICEMODE_SOUNDFONTS_ENABLED=' "$config_file" 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'" || echo "")
    [[ "$enabled" == "true" || "$enabled" == "1" || "$enabled" == "yes" || "$enabled" == "on" ]]
    return
  fi

  # Default: enabled
  return 0
}

if ! soundfonts_enabled; then
  debug "Sound fonts are disabled (VOICEMODE_SOUNDFONTS_ENABLED=false)"
  exit 0
fi

# Check if a voice conversation is active (conch lock file)
# If active, skip sound playback to avoid disrupting voice recording
converse_active() {
  local conch_file="$HOME/.voicemode/conch"

  # No lock file = no active conversation
  [[ ! -f "$conch_file" ]] && return 1

  # Check if the process holding the lock is still alive
  local pid
  if command -v jq &>/dev/null; then
    pid=$(jq -r '.pid // ""' "$conch_file" 2>/dev/null)
  else
    # Fallback: basic grep for pid field
    pid=$(grep -o '"pid"[[:space:]]*:[[:space:]]*[0-9]*' "$conch_file" | grep -o '[0-9]*' || echo "")
  fi

  # If no valid PID, lock is stale
  [[ -z "$pid" ]] && return 1

  # Check if process is alive (signal 0 doesn't send a signal, just checks)
  kill -0 "$pid" 2>/dev/null
}

if converse_active; then
  debug "Voice conversation active (conch lock) - skipping sound playback"
  exit 0
fi

# Resolve soundfonts symlink
if [[ -L "$SOUNDFONTS_BASE" ]]; then
  SOUNDFONTS_BASE=$(readlink -f "$SOUNDFONTS_BASE" 2>/dev/null || readlink "$SOUNDFONTS_BASE")
fi

if [[ ! -d "$SOUNDFONTS_BASE" ]]; then
  debug "Soundfonts directory not found: $SOUNDFONTS_BASE"
  exit 0
fi

# Normalize to lowercase for filesystem
tool_lower=$(echo "$TOOL_NAME" | tr '[:upper:]' '[:lower:]')
subagent_lower=$(echo "$SUBAGENT_TYPE" | tr '[:upper:]' '[:lower:]')

# Parse MCP tool names: mcp__{server}__{tool} -> mcp/{server}/{tool}
mcp_server=""
mcp_tool=""
if [[ "$tool_lower" =~ ^mcp__([^_]+)__(.+)$ ]]; then
  mcp_server="${BASH_REMATCH[1]}"
  mcp_tool="${BASH_REMATCH[2]}"
  debug "Parsed MCP tool: server=$mcp_server, tool=$mcp_tool"
fi

# Map event names to directory names
event_lower=$(echo "$EVENT" | tr '[:upper:]' '[:lower:]')
case "$event_lower" in
pretooluse | start)
  event_dir="PreToolUse"
  ;;
posttooluse | end)
  event_dir="PostToolUse"
  ;;
precompact)
  event_dir="PreCompact"
  ;;
*)
  event_dir="$EVENT"
  ;;
esac

# Select a random variant from a directory
# Args: directory path
# Returns: random file path from numbered variants or default.{mp3,wav}
#
# Numbered file patterns (in order of preference):
#   - 01_description.{mp3,wav}  (2-digit zero-padded with underscore separator)
#   - 001_description.{mp3,wav} (3-digit zero-padded with underscore separator)
#   - 01.{mp3,wav}              (2-digit zero-padded, no description)
#
# Files starting with a number (any zero-padding) followed by underscore or extension
# are considered variants and one is randomly selected.
#
# Falls back to default.{mp3,wav} only if no numbered variants found.
select_variant() {
  local dir="$1"
  local variants=()

  # Find all numbered variant files (supports any zero-padding length)
  # Pattern: <digits>_*.{mp3,wav} or <digits>.{mp3,wav}
  for ext in mp3 wav; do
    # Use find to locate files matching the pattern
    # Look for files starting with digits, followed by either _ or .ext
    while IFS= read -r -d '' file; do
      local filename=$(basename "$file")
      # Match files like: 01_name.wav, 001_name.wav, 01.wav, etc.
      if [[ "$filename" =~ ^[0-9]+(_.*)?\.${ext}$ ]]; then
        variants+=("$file")
      fi
    done < <(find "$dir" -maxdepth 1 -type f -name "*.$ext" -print0 2>/dev/null)
  done

  # If we found numbered variants, select one randomly
  if [[ ${#variants[@]} -gt 0 ]]; then
    local count=${#variants[@]}
    local index=$((RANDOM % count))
    echo "${variants[$index]}"
    debug "Found ${count} numbered variants in $dir, selected: ${variants[$index]}"
    return 0
  fi

  # No numbered variants found, try default files
  for ext in mp3 wav; do
    if [[ -f "$dir/default.$ext" ]]; then
      echo "$dir/default.$ext"
      debug "No numbered variants in $dir, using default.$ext"
      return 0
    fi
  done

  # Nothing found
  return 1
}

# Find sound file (most specific to least specific)
#
# Mute marker:
#   - MUTE.txt in any directory will suppress sound playback for that path
#
# Sound file lookup order (with MCP tools):
#   1. {event}/mcp/{server}/{tool}/[01-99|default].{mp3,wav}  - MCP tool variants
#   2. {event}/mcp/{server}/default.{mp3,wav}                  - Server default
#   3. {event}/mcp/default.{mp3,wav}                           - MCP-wide default
#   4. {event}/{tool}/subagent/{subagent}.{mp3,wav}            - Task subagent
#   5. {event}/{tool}/[01-99|default].{mp3,wav}                - Tool variants
#   6. {event}/default.{mp3,wav}                               - Event default
#   7. fallback.{mp3,wav}                                      - Global fallback
#
# Examples:
#   PostToolUse/mcp/voicemode/converse/01.mp3       - Voice tool variant 1
#   PostToolUse/mcp/voicemode/converse/default.mp3  - Voice tool default
#   PreToolUse/bash/02.mp3                          - Bash variant 2
#   PreToolUse/task/subagent/mama-bear.mp3          - Specific agent
#   PreToolUse/mcp/voicemode/converse/MUTE.txt      - Mute converse PreToolUse sounds
find_sound_file() {
  local sound_file

  # 1. MCP tool-specific sounds (if this is an MCP tool)
  if [[ -n "$mcp_server" && -n "$mcp_tool" ]]; then
    local mcp_tool_dir="$SOUNDFONTS_BASE/$event_dir/mcp/$mcp_server/$mcp_tool"

    # Check for mute marker
    if [[ -f "$mcp_tool_dir/MUTE.txt" ]]; then
      debug "Found MUTE.txt in $mcp_tool_dir - skipping sound playback"
      return 1
    fi

    # Try selecting variant from MCP tool directory
    if sound_file=$(select_variant "$mcp_tool_dir" 2>/dev/null); then
      echo "$sound_file"
      return 0
    fi

    # Try MCP server default
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/mcp/$mcp_server/default.mp3" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/mcp/$mcp_server/default.mp3"
      return 0
    fi
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/mcp/$mcp_server/default.wav" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/mcp/$mcp_server/default.wav"
      return 0
    fi

    # Try MCP-wide default
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/mcp/default.mp3" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/mcp/default.mp3"
      return 0
    fi
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/mcp/default.wav" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/mcp/default.wav"
      return 0
    fi
  fi

  # 2. Task subagent sounds (special case)
  if [[ "$tool_lower" == "task" && -n "$subagent_lower" ]]; then
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/$tool_lower/subagent/${subagent_lower}.mp3" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/$tool_lower/subagent/${subagent_lower}.mp3"
      return 0
    fi
    if [[ -f "$SOUNDFONTS_BASE/$event_dir/$tool_lower/subagent/${subagent_lower}.wav" ]]; then
      echo "$SOUNDFONTS_BASE/$event_dir/$tool_lower/subagent/${subagent_lower}.wav"
      return 0
    fi
  fi

  # 3. Regular tool-specific sounds with variants
  local tool_dir="$SOUNDFONTS_BASE/$event_dir/$tool_lower"

  # Check for mute marker
  if [[ -f "$tool_dir/MUTE.txt" ]]; then
    debug "Found MUTE.txt in $tool_dir - skipping sound playback"
    return 1
  fi

  if sound_file=$(select_variant "$tool_dir" 2>/dev/null); then
    echo "$sound_file"
    return 0
  fi

  # 4. Event-level default (no variants at this level)
  if [[ -f "$SOUNDFONTS_BASE/$event_dir/default.mp3" ]]; then
    echo "$SOUNDFONTS_BASE/$event_dir/default.mp3"
    return 0
  fi
  if [[ -f "$SOUNDFONTS_BASE/$event_dir/default.wav" ]]; then
    echo "$SOUNDFONTS_BASE/$event_dir/default.wav"
    return 0
  fi

  # 5. Global fallback (no variants)
  if [[ -f "$SOUNDFONTS_BASE/fallback.mp3" ]]; then
    echo "$SOUNDFONTS_BASE/fallback.mp3"
    return 0
  fi
  if [[ -f "$SOUNDFONTS_BASE/fallback.wav" ]]; then
    echo "$SOUNDFONTS_BASE/fallback.wav"
    return 0
  fi

  return 1
}

SOUND_FILE=$(find_sound_file)

if [[ -z "$SOUND_FILE" ]]; then
  debug "No sound file found for this event"
  exit 0
fi

debug "Found sound file: $SOUND_FILE"

# Skip filler phrases when wait_for_response=false (no listening after speaking)
# Filler phrases only make sense when Claude is waiting for user input
if [[ "$EVENT" == "PostToolUse" && "$tool_lower" == "mcp__voicemode__converse" ]]; then
  # Check if wait_for_response was false in tool_input
  if [[ -n "$JSON_INPUT" ]] && command -v jq &>/dev/null; then
    # Extract wait_for_response - check if field exists first, then convert to string
    # Default to "true" if field is missing, but preserve explicit false values
    wait_for_response=$(echo "$JSON_INPUT" | jq -r 'if .tool_input.wait_for_response == null then "true" else (.tool_input.wait_for_response | tostring) end')
    if [[ "$wait_for_response" == "false" ]]; then
      debug "Skipping filler phrase: wait_for_response=false (speak-only mode)"
      exit 0
    fi
  fi
fi

# Rate limiting for PostToolUse converse events (optional, disabled by default)
# Set VOICEMODE_CONVERSE_RATE_LIMIT=true to enable
# This prevents rapid-fire filler phrases when Claude batches tool calls
if [[ "$EVENT" == "PostToolUse" && "$tool_lower" == "mcp__voicemode__converse" ]]; then
  RATE_LIMIT_ENABLED="${VOICEMODE_CONVERSE_RATE_LIMIT:-false}"
  if [[ "$RATE_LIMIT_ENABLED" == "true" || "$RATE_LIMIT_ENABLED" == "1" ]]; then
    RATE_LIMIT_SECONDS="${VOICEMODE_CONVERSE_RATE_LIMIT_SECONDS:-2}"
    LOG_FILE="$HOME/.voicemode/logs/hook-receiver.log"

    # Check if we played a converse filler recently
    if [[ -f "$LOG_FILE" ]]; then
      # Get the last PostToolUse converse timestamp
      last_converse=$(grep "PostToolUse mcp__voicemode__converse" "$LOG_FILE" | tail -1 | cut -d' ' -f1-2)
      if [[ -n "$last_converse" ]]; then
        # Convert timestamp to epoch (cross-platform: macOS and Linux)
        if date -j -f "%Y-%m-%d %H:%M:%S" "$last_converse" "+%s" &>/dev/null; then
          # macOS (BSD date)
          last_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$last_converse" "+%s")
        else
          # Linux (GNU date)
          last_epoch=$(date -d "$last_converse" "+%s" 2>/dev/null || echo 0)
        fi
        now_epoch=$(date "+%s")
        elapsed=$((now_epoch - last_epoch))

        if [[ $elapsed -lt $RATE_LIMIT_SECONDS ]]; then
          debug "Rate limited: only ${elapsed}s since last converse filler (threshold: ${RATE_LIMIT_SECONDS}s)"
          exit 0
        fi
      fi
    fi
  fi
fi

# Log hook execution (always, for debugging)
LOG_FILE="$HOME/.voicemode/logs/hook-receiver.log"
mkdir -p "$(dirname "$LOG_FILE")"
timestamp=$(date "+%Y-%m-%d %H:%M:%S")
echo "$timestamp $EVENT $TOOL_NAME -> $SOUND_FILE" >>"$LOG_FILE"

# Play sound asynchronously (fire and forget)
# Redirect both stdout and stderr to /dev/null to prevent any output
# Prefer native players (afplay on macOS, paplay on Linux) for better concurrent playback
if command -v afplay &>/dev/null; then
  # macOS native - handles concurrent playback through Core Audio
  afplay "$SOUND_FILE" >/dev/null 2>&1 &
  disown 2>/dev/null || true
  debug "Sound playback started (afplay)"
elif command -v paplay &>/dev/null; then
  # Linux PulseAudio - handles concurrent playback natively
  paplay "$SOUND_FILE" >/dev/null 2>&1 &
  disown 2>/dev/null || true
  debug "Sound playback started (paplay)"
elif command -v ffplay &>/dev/null; then
  # ffmpeg fallback - may have issues with concurrent playback
  ffplay -nodisp -autoexit -loglevel quiet "$SOUND_FILE" >/dev/null 2>&1 &
  disown 2>/dev/null || true
  debug "Sound playback started (ffplay)"
else
  debug "No audio player found (tried: afplay, paplay, ffplay)"
fi

exit 0
