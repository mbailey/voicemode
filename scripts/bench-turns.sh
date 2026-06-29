#!/usr/bin/env bash
# bench-turns.sh — latency benchmark for multi-utterance converse (VM-1772).
#
# Proves the headline claim: a single `turns` call eliminates the per-line
# synthesis dead-air the serial milkshake pays. Requires LIVE TTS services
# (Kokoro/mlx-audio or OpenAI) and an audio device — it actually speaks.
#
# It measures END-TO-END WALL-CLOCK for two runs of the same four lines:
#   * baseline  — four serial `voicemode converse --skip-stt` processes (today's
#                 milkshake.sh: four cold starts + four TTS round-trips, dead air
#                 between each line)
#   * candidate — ONE `voicemode converse` call with a four-turn `turns` list,
#                 synth pipelined behind playback
#
# Pass criteria (record both numbers in the task log):
#   * candidate wall-clock < baseline wall-clock
#   * candidate inter-utterance gap ≈ pause_after_ms (synth dead-air gone after
#     turn 1) — audible on a listen. To confirm generation overlapped playback,
#     watch the converse INFO logs: per-turn "TTS synthesized … (gen Ns)" lines
#     land while earlier turns are still playing, and the final
#     "Spoke N/N turns (gen: Xs, play: Ys)" summary shows total gen < total play.
set -euo pipefail

L1="My milkshake brings all the boys to the yard."
L2="Damn right. It's better than yours."
L3="I could teach you. But I'd have to charge."
L4="So! You still want a milkshake?"
PAUSE_MS="${PAUSE_MS:-150}"

now() { python3 -c 'import time; print(time.perf_counter())' 2>/dev/null || date +%s.%N; }
elapsed() { python3 -c "import sys; print(f'{float(sys.argv[2]) - float(sys.argv[1]):.2f}')" "$1" "$2"; }

echo "=== BASELINE: four serial converse calls (cold start each) ==="
b0=$(now)
voicemode converse --skip-stt --voice sandy     "$L1"
voicemode converse --skip-stt --voice tripitaka "$L2"
voicemode converse --skip-stt --voice pigsy     "$L3"
voicemode converse --skip-stt --voice monkey    "$L4"
b1=$(now)
baseline=$(elapsed "$b0" "$b1")
echo "baseline wall-clock: ${baseline}s"
echo

echo "=== CANDIDATE: one converse call, four turns, pipelined (pause ${PAUSE_MS}ms) ==="
c0=$(now)
voicemode converse --skip-stt --pause-after-ms "$PAUSE_MS" \
  --say "sandy:$L1" \
  --say "tripitaka:$L2" \
  --say "pigsy:$L3" \
  --say "monkey:$L4"
c1=$(now)
candidate=$(elapsed "$c0" "$c1")
echo "candidate wall-clock: ${candidate}s"
echo

echo "=== RESULT ==="
echo "baseline  = ${baseline}s"
echo "candidate = ${candidate}s"
python3 -c "
b, c = float('$baseline'), float('$candidate')
print(f'speedup   = {b - c:.2f}s faster ({(1 - c/b) * 100:.0f}% reduction)' if b else 'n/a')
print('PASS: candidate is faster' if c < b else 'FAIL: candidate not faster — investigate')
"
