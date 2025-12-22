#!/usr/bin/env bash
set -o nounset -o pipefail -o errexit
#
# benchmark-hooks - Measure hook execution overhead
#
# This script benchmarks the impact of different hook configurations
# by running claude with a prompt that triggers multiple tool uses.
#
# Usage:
#   benchmark-hooks [runs]
#
# The script will test three configurations:
#   1. No hooks (baseline)
#   2. Python hooks (original)
#   3. Shell script hooks (optimized)

usage() {
    cat << 'EOF'
Usage: benchmark-hooks [OPTIONS] [runs]

Measure hook execution overhead by running claude with prompts that trigger
multiple tool uses under different hook configurations.

Arguments:
    runs    Number of runs per configuration (default: 3)

Options:
    -h, --help    Show this help message and exit

Configurations tested:
    1. No hooks (baseline)
    2. Python hooks (voicemode claude hooks receiver)
    3. Shell script hooks (voicemode-hook-receiver)
EOF
}

# Parse arguments
case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

RUNS="${1:-3}"
SETTINGS_FILE="$HOME/.claude/settings.json"
BACKUP_FILE="$HOME/.claude/settings.json.backup"

# The prompt triggers 5 Bash tool calls with minimal work
TEST_PROMPT='Run these 5 bash commands in parallel: "sleep 0.1", "sleep 0.1", "sleep 0.1", "sleep 0.1", "sleep 0.1". Just run them, no explanation needed.'

# Save original settings
if [[ -f "$SETTINGS_FILE" ]]; then
    cp "$SETTINGS_FILE" "$BACKUP_FILE"
fi

cleanup() {
    if [[ -f "$BACKUP_FILE" ]]; then
        mv "$BACKUP_FILE" "$SETTINGS_FILE"
        echo "Restored original settings"
    fi
}
trap cleanup EXIT

write_settings() {
    local hook_cmd="$1"
    if [[ -z "$hook_cmd" ]]; then
        # No hooks
        cat > "$SETTINGS_FILE" << 'EOF'
{
  "permissions": {}
}
EOF
    else
        cat > "$SETTINGS_FILE" << EOF
{
  "permissions": {},
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${hook_cmd} || true"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${hook_cmd} || true"
          }
        ]
      }
    ]
  }
}
EOF
    fi
}

run_benchmark() {
    local name="$1"
    local total=0

    echo "=== $name ==="
    for i in $(seq 1 "$RUNS"); do
        start=$(python3 -c "import time; print(time.time())")
        echo "$TEST_PROMPT" | claude -p --tools "Bash" > /dev/null 2>&1
        end=$(python3 -c "import time; print(time.time())")
        elapsed=$(python3 -c "print(f'{$end - $start:.2f}')")
        total=$(python3 -c "print($total + $end - $start)")
        echo "  Run $i: ${elapsed}s"
    done
    avg=$(python3 -c "print(f'{$total / $RUNS:.2f}')")
    echo "  Average: ${avg}s"
    echo ""
}

echo "Hook Performance Benchmark"
echo "=========================="
echo "Runs per config: $RUNS"
echo "Prompt triggers 5 parallel Bash tool calls"
echo ""

# Test 1: No hooks (baseline)
write_settings ""
run_benchmark "No Hooks (baseline)"

# Test 2: Python hooks
write_settings "voicemode claude hooks receiver"
run_benchmark "Python Hook (voicemode claude hooks receiver)"

# Test 3: Shell script hooks
write_settings "voicemode-hook-receiver"
run_benchmark "Shell Script Hook (voicemode-hook-receiver)"

echo "Benchmark complete!"
