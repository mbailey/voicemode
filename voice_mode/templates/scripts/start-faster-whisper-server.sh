#!/usr/bin/env bash
set -euo pipefail
PORT="${VOICEMODE_FASTER_WHISPER_PORT:-2023}"
# speaches serves an OpenAI-compatible API (verbose_json + word timestamps).
exec speaches serve --host 127.0.0.1 --port "$PORT"
