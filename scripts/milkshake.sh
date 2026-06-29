#!/usr/bin/env bash
# milkshake.sh — the canonical multi-voice demo (VM-1772).
#
# BEFORE (four serial processes — four cold starts, four TTS round-trips,
# dead air between each line):
#
#   vmv='voicemode converse --skip-stt --voice'
#   $vmv sandy     "My milkshake brings all the boys to the yard."
#   $vmv tripitaka "Damn right. It's better than yours."
#   $vmv pigsy     "I could teach you. But I'd have to charge."
#   $vmv monkey    "So! You still want a milkshake?"
#
# AFTER — one call. Turn N+1 is synthesized while turn N plays, so the lines
# run gap-free (only the configured pause between them, no synth dead-air).
#
# The text has no ':' so the quick --say 'VOICE:TEXT' surface is fine. For text
# containing ':' use --script (see milkshake.json below).
set -euo pipefail

voicemode converse --skip-stt \
  --say "sandy:My milkshake brings all the boys to the yard." \
  --say "tripitaka:Damn right. It's better than yours." \
  --say "pigsy:I could teach you. But I'd have to charge." \
  --say "monkey:So! You still want a milkshake?"

# Equivalent JSON-script form (escape hatch for ':' in text, reusable file):
#
#   voicemode converse --skip-stt --script - <<'JSON'
#   [ {"say":"My milkshake brings all the boys to the yard.", "voice":"sandy"},
#     {"say":"Damn right. It's better than yours.",           "voice":"tripitaka"},
#     {"say":"I could teach you. But I'd have to charge.",    "voice":"pigsy", "pause_after_ms":400},
#     {"say":"So! You still want a milkshake?",               "voice":"monkey"} ]
#   JSON
