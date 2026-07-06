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
CONVO_LOG_FILE="$CONVO_LOG_DIR/exchanges_$(date +%Y-%m-%d).jsonl"

Q1="Question one: what is two plus two?"
Q2="Question two: what's your favorite color?"
Q3="Question three: say one thing you're grateful for today."

ASSERT_FAILS=0

say() { uv run voicemode converse --skip-stt --voice "$VOICE" --skip-conch "$1" >/dev/null 2>&1; }

# assert_survey RUN_NAME JSON_FILE EXIT_CODE EXPECT_COMPLETED [EXPECT_TURN EXPECT_PHASE EXPECT_REASON]
#
# Structural assertions against the README ## Design return contract --
# alignment invariant (turns always length 3, index-aligned), completed/
# exit-code agreement (0 completed / 3 partial), and (on a partial) the
# stopped_at shape + every turn past the stop point reporting not_reached.
# This is the per-run "PASS/FAIL" the VM-1772 bench-turns.sh pattern computes
# for its speedup claim -- here computed for the survey JSON's structure
# rather than a human eyeballing the raw dump. It intentionally does NOT
# assert on the actual spoken reply text (that varies with the live
# respondent) -- only on the shape/contract, which is deterministic.
assert_survey() {
  local name="$1" file="$2" exit_code="$3" expect_completed="$4"
  local expect_turn="${5:-}" expect_phase="${6:-}" expect_reason="${7:-}"
  if python3 - "$file" "$exit_code" "$expect_completed" "$expect_turn" "$expect_phase" "$expect_reason" "$name" <<'PY'
import json, sys
file, exit_code, expect_completed, expect_turn, expect_phase, expect_reason, name = sys.argv[1:8]
exit_code = int(exit_code)
expect_completed = expect_completed == "true"
problems = []
try:
    raw = open(file).read()
    payload = json.loads(raw)
except Exception as e:
    print(f"ASSERT FAIL [{name}]: could not parse JSON ({e}); raw={raw[:200]!r}" if 'raw' in dir() else f"ASSERT FAIL [{name}]: could not read {file} ({e})")
    sys.exit(1)
survey = payload.get("survey")
if survey is None:
    print(f"ASSERT FAIL [{name}]: no top-level 'survey' key -- got: {raw[:200]!r}")
    sys.exit(1)
turns = survey.get("turns")
if not isinstance(turns, list) or len(turns) != 3:
    problems.append(f"turns array not length 3 (got {turns!r})")
if survey.get("asked") != 3:
    problems.append(f"asked != 3 (got {survey.get('asked')!r})")
if survey.get("completed") != expect_completed:
    problems.append(f"completed={survey.get('completed')!r}, expected {expect_completed}")
expected_exit = 0 if expect_completed else 3
if exit_code != expected_exit:
    problems.append(f"exit={exit_code}, expected {expected_exit}")
stopped_at = survey.get("stopped_at")
if expect_completed:
    if stopped_at is not None:
        problems.append(f"stopped_at should be null on completion, got {stopped_at!r}")
    if any(t.get("status") == "not_reached" for t in (turns or [])):
        problems.append("a turn is not_reached despite completed=true")
else:
    if stopped_at is None:
        problems.append("stopped_at is null but survey did not complete")
    else:
        if expect_turn and stopped_at.get("turn") != int(expect_turn):
            problems.append(f"stopped_at.turn={stopped_at.get('turn')!r}, expected {expect_turn}")
        if expect_phase and stopped_at.get("phase") != expect_phase:
            problems.append(f"stopped_at.phase={stopped_at.get('phase')!r}, expected {expect_phase!r}")
        if expect_reason and stopped_at.get("reason") != expect_reason:
            problems.append(f"stopped_at.reason={stopped_at.get('reason')!r}, expected {expect_reason!r}")
        stop_turn = stopped_at.get("turn")
        if stop_turn is not None:
            for t in (turns or []):
                if t.get("turn") is not None and t.get("turn") > stop_turn and t.get("status") != "not_reached":
                    problems.append(f"turn {t.get('turn')} should be not_reached (got {t.get('status')!r})")
if problems:
    print(f"ASSERT FAIL [{name}]:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
suffix = f", stopped_at.reason={expect_reason}" if expect_reason else ""
print(f"ASSERT PASS [{name}]: completed={expect_completed}, exit={exit_code}, turns=3/3 aligned{suffix}")
sys.exit(0)
PY
  then
    return 0
  else
    ASSERT_FAILS=$((ASSERT_FAILS + 1))
    return 1
  fi
}

# check_convo_log RUN_NAME JSON_FILE SINCE_EPOCH_S — confirm EVERY answered
# reply in the run's own survey JSON landed in today's conversation log
# at/after SINCE_EPOCH_S (Decision 7's crash-persistence guarantee: per-turn
# logging, not batched at survey end -- must hold even on a stop/break run
# that returns a partial). N-d (fable pre-merge audit): this used to require
# only >=1 logged reply regardless of how many turns were actually answered,
# which would silently pass even if a multi-answer run only logged one of
# its replies. Now computes the expected count from the run's own JSON and
# requires every answered turn accounted for.
check_convo_log() {
  local name="$1" file="$2" since="$3"
  if python3 - "$CONVO_LOG_FILE" "$file" "$since" "$name" <<'PY'
import json, sys
from datetime import datetime
path, survey_file, since, name = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]

try:
    survey = json.loads(open(survey_file).read()).get("survey") or {}
    turns = survey.get("turns") or []
except Exception as e:
    print(f"ASSERT FAIL [{name}]: could not parse {survey_file} to compute expected answered count ({e})")
    sys.exit(1)
expected = sum(1 for t in turns if t.get("status") == "answered")

try:
    lines = open(path).readlines()
except FileNotFoundError:
    print(f"ASSERT FAIL [{name}]: conversation log not found at {path}")
    sys.exit(1)
found = 0
for line in lines:
    try:
        entry = json.loads(line)
    except Exception:
        continue
    if entry.get("type") != "stt":
        continue
    if (entry.get("metadata") or {}).get("transport") != "survey":
        continue
    try:
        ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
    except Exception:
        continue
    if ts >= since:
        found += 1
if found < expected:
    print(f"ASSERT FAIL [{name}]: only {found}/{expected} answered survey replies durably logged since run start")
    sys.exit(1)
print(f"ASSERT PASS [{name}]: {found}/{expected} answered survey replies durably logged")
sys.exit(0)
PY
  then
    return 0
  else
    ASSERT_FAILS=$((ASSERT_FAILS + 1))
    return 1
  fi
}

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
  local since; since="$(date +%s)"
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run1.json" 2>"$OUT_DIR/run1.log"
  local rc=$?
  echo "exit=$rc -- see $OUT_DIR/run1.json"
  cat "$OUT_DIR/run1.json"
  assert_survey "run1-full" "$OUT_DIR/run1.json" "$rc" true
  check_convo_log "run1-full" "$OUT_DIR/run1.json" "$since"
}

run_bargein() {
  echo "=== RUN 2: skip-forward barge-in (answer-early + end-capture) ==="
  say "Run 2 of 4: barge in. I will trigger skip forward automatically. For question one, answer with just the single word four, right away. For question two, keep talking continuously and do not stop, in one long rambling stream about any color, until you notice I cut you off."
  local since; since="$(date +%s)"
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run2.json" 2>"$OUT_DIR/run2.log" &
  local pid=$!
  # N-d (fable pre-merge audit): track whether each gesture actually fired --
  # if poll_phase times out, `control skip-forward` never runs and the run
  # silently degrades to a plain full-completion survey, which would
  # otherwise still satisfy `assert_survey ... true` unnoticed.
  local bargein_fired=0
  # Turn 0: fire skip_forward while still SPEAKING -> answer-early (jumps to listen)
  if poll_phase 0 speaking 15; then
    sleep 0.8
    control skip-forward && bargein_fired=$((bargein_fired + 1))
  else
    echo "  !! poll_phase(turn=0, speaking) timed out -- turn-0 skip_forward will NOT fire"
  fi
  # Turn 1: let it reach LISTENING, then fire skip_forward again -> end-capture
  if poll_phase 1 listening 60; then
    sleep 2.5
    control skip-forward && bargein_fired=$((bargein_fired + 1))
  else
    echo "  !! poll_phase(turn=1, listening) timed out -- turn-1 skip_forward will NOT fire"
  fi
  wait "$pid"
  local rc=$?
  echo "exit=$rc -- see $OUT_DIR/run2.json"
  cat "$OUT_DIR/run2.json"
  assert_survey "run2-bargein" "$OUT_DIR/run2.json" "$rc" true
  if [ "$bargein_fired" -ne 2 ]; then
    echo "ASSERT FAIL [run2-bargein-gestures]: only $bargein_fired/2 skip_forward gestures actually fired -- this run does not exercise barge-in and would otherwise be indistinguishable from run 1's full completion"
    ASSERT_FAILS=$((ASSERT_FAILS + 1))
  else
    echo "ASSERT PASS [run2-bargein-gestures]: both skip_forward gestures fired (turn-0 speaking barge-in + turn-1 listening end-capture)"
  fi
  check_convo_log "run2-bargein" "$OUT_DIR/run2.json" "$since"
}

run_stop() {
  echo "=== RUN 3: stop mid-listen ==="
  say "Run 3 of 4: stop mid listen. For question one, answer with just the single word four, right away. Then wait -- I will stop the survey myself during question two, no need to answer it."
  local since; since="$(date +%s)"
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$Q2" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run3.json" 2>"$OUT_DIR/run3.log" &
  local pid=$!
  poll_phase 1 listening 60 && sleep 1.5 && control stop
  wait "$pid"
  local rc=$?
  echo "exit=$rc -- see $OUT_DIR/run3.json"
  cat "$OUT_DIR/run3.json"
  assert_survey "run3-stop" "$OUT_DIR/run3.json" "$rc" false 1 listening stop
  check_convo_log "run3-stop" "$OUT_DIR/run3.json" "$since"
}

run_break() {
  echo "=== RUN 4: spoken break ==="
  say "Run 4 of 4: spoken break. Answer question one normally. On question two you will be told to just say the word break -- do that instead of actually answering."
  local q2_break="Question two: right now, please just say the single word break."
  local since; since="$(date +%s)"
  uv run voicemode converse --skip-conch --ask "$VOICE:$Q1" --ask "$VOICE:$q2_break" --ask "$VOICE:$Q3" \
    >"$OUT_DIR/run4.json" 2>"$OUT_DIR/run4.log"
  local rc=$?
  echo "exit=$rc -- see $OUT_DIR/run4.json"
  cat "$OUT_DIR/run4.json"
  assert_survey "run4-break" "$OUT_DIR/run4.json" "$rc" false 1 listening spoken_break
  check_convo_log "run4-break" "$OUT_DIR/run4.json" "$since"
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
echo "Conversation logs: $CONVO_LOG_FILE"
echo
if [ "$ASSERT_FAILS" -eq 0 ]; then
  echo "=== RESULT: PASS (0 assertion failures) ==="
else
  echo "=== RESULT: FAIL ($ASSERT_FAILS assertion failure(s) -- see ASSERT FAIL lines above) ==="
  exit 1
fi
