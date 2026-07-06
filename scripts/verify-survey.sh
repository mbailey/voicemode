#!/usr/bin/env bash
# verify-survey.sh — LIVE verification of survey mode (VM-1775, impl-007).
#
# Follows the VM-1772 bench-turns.sh pattern: a runnable script against LIVE
# TTS/STT services and a real respondent (not mocks). Requires:
#   * VOICEMODE_CONTROL_CHANNEL_ENABLED=true (for the barge-in / stop drills)
#   * a live human respondent standing by at the mic
#
# Drives a fixed 3-question survey FOUR ways:
#   1. full        — respondent answers all three questions normally
#   2. barge-in    — skip_forward during Q1's SPEAKING phase (answer-early,
#                    jumps straight to listening) + skip_forward again during
#                    Q2's LISTENING phase (end-capture, ends recording early)
#   3. stop        — `voicemode control stop` fired mid-LISTEN on Q2
#   4. break       — respondent says a spoken break phrase ("break") instead
#                    of answering Q2
#
# skip_forward/stop are driven via `voicemode control` (the same CLI a Stream
# Deck button or media key would invoke — see docs/reference/control-channel.md)
# timed off ~/.voicemode/state.json phase transitions (VM-1793), so the drill
# is deterministic rather than racing a human's key-press timing. The THREE
# actual answers/break-phrase in each run still require a real human voice at
# the mic — that part is not simulated.
set -uo pipefail

VOICE="${VOICE:-sandy}"
STATE_FILE="${VOICEMODE_BASE_DIR:-$HOME/.voicemode}/state.json"
OUT_DIR="$(mktemp -d /tmp/vm1775-verify-survey.XXXXXX 2>/dev/null || mktemp -d)"
CONVO_LOG_DIR="${VOICEMODE_BASE_DIR:-$HOME/.voicemode}/logs/conversations"

Q1="Question one: what is two plus two?"
Q2="Question two: what's your favorite color?"
Q3="Question three: say one thing you're grateful for today."

say() { uv run voicemode converse --skip-stt --voice "$VOICE" --skip-conch "$1" >/dev/null 2>&1; }

# poll_phase TURN PHASE TIMEOUT_S — block until state.json shows
# survey.turn==TURN and phase==PHASE, or timeout.
poll_phase() {
  local turn="$1" phase="$2" timeout="${3:-20}"
  python3 - "$STATE_FILE" "$turn" "$phase" "$timeout" <<'PY'
import json, sys, time
path, turn, phase, timeout = sys.argv[1], int(sys.argv[2]), sys.argv[3], float(sys.argv[4])
deadline = time.time() + timeout
while time.time() < deadline:
    try:
        d = json.loads(open(path).read())
        sv = d.get("survey")
        if d.get("phase") == phase and sv and sv.get("turn") == turn:
            print(f"OK phase={phase} turn={turn} ts={d.get('ts')}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(0.05)
print(f"TIMEOUT waiting for phase={phase} turn={turn}", file=sys.stderr)
sys.exit(1)
PY
}

control() {
  echo "  >>> voicemode control $1"
  uv run voicemode control "$1"
}

run_full() {
  echo "=== RUN 1: full completion ==="
  say "Run 1 of 4: full completion. Please answer all three questions normally."
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run1.json" 2>"$OUT_DIR/run1.log"
  echo "exit=$? -- see $OUT_DIR/run1.json"
  cat "$OUT_DIR/run1.json"
}

run_bargein() {
  echo "=== RUN 2: skip-forward barge-in (answer-early + end-capture) ==="
  say "Run 2 of 4: barge in. I will trigger skip forward automatically. For question one, answer with just the single word four, right away. For question two, keep talking continuously and do not stop, in one long rambling stream about any color, until you notice I cut you off."
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run2.json" 2>"$OUT_DIR/run2.log" &
  local pid=$!
  # Turn 0: fire skip_forward while still SPEAKING -> answer-early (jumps to listen)
  poll_phase 0 speaking 15 && sleep 0.8 && control skip-forward
  # Turn 1: let it reach LISTENING, then fire skip_forward again -> end-capture
  poll_phase 1 listening 60 && sleep 2.5 && control skip-forward
  wait "$pid"
  echo "exit=$? -- see $OUT_DIR/run2.json"
  cat "$OUT_DIR/run2.json"
}

run_stop() {
  echo "=== RUN 3: stop mid-listen ==="
  say "Run 3 of 4: stop mid listen. For question one, answer with just the single word four, right away. Then wait -- I will stop the survey myself during question two, no need to answer it."
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run3.json" 2>"$OUT_DIR/run3.log" &
  local pid=$!
  poll_phase 1 listening 60 && sleep 1.5 && control stop
  wait "$pid"
  echo "exit=$? -- see $OUT_DIR/run3.json"
  cat "$OUT_DIR/run3.json"
}

run_break() {
  echo "=== RUN 4: spoken break ==="
  say "Run 4 of 4: spoken break. Answer question one normally. On question two you will be told to just say the word break -- do that instead of actually answering."
  local q2_break="Question two: right now, please just say the single word break."
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$q2_break" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run4.json" 2>"$OUT_DIR/run4.log"
  echo "exit=$? -- see $OUT_DIR/run4.json"
  cat "$OUT_DIR/run4.json"
}

case "${1:-all}" in
  full) run_full ;;
  bargein) run_bargein ;;
  stop) run_stop ;;
  break) run_break ;;
  all)
    run_full
    run_bargein
    run_stop
    run_break
    ;;
  *) echo "usage: $0 [full|bargein|stop|break|all]"; exit 2 ;;
esac

echo
echo "Output dir: $OUT_DIR"
echo "Conversation logs: $CONVO_LOG_DIR"
