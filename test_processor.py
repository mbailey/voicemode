#!/usr/bin/env python3
"""Test the process_whisper_output function with captured test data."""

import sys
from pathlib import Path

# Add voice_mode to path
sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.stream_capture import process_whisper_output

# Test with the captured data from our test run
# Use absolute path
test_file = Path("/Users/admin/tasks/projects/voicemode/VM-194_feat_implement-stream-capture-with-cassette-deck-flow-controls/test-data/capture_20251027_224846.txt")

# State changes from the test run (from logs)
state_changes = [
    {"event": "resume", "relative_time_seconds": 26.7, "whisper_t0_ms": 0},
    {"event": "resume", "relative_time_seconds": 30.6, "whisper_t0_ms": 0},
    {"event": "resume", "relative_time_seconds": 35.1, "whisper_t0_ms": 0},
    {"event": "resume", "relative_time_seconds": 39.2, "whisper_t0_ms": 3442},
    {"event": "pause", "relative_time_seconds": 42.2, "whisper_t0_ms": 6798},
    {"event": "resume", "relative_time_seconds": 42.2, "whisper_t0_ms": 6798},
    {"event": "pause", "relative_time_seconds": 42.2, "whisper_t0_ms": 6798},
    {"event": "pause", "relative_time_seconds": 46.1, "whisper_t0_ms": 10198},
    {"event": "pause", "relative_time_seconds": 46.1, "whisper_t0_ms": 10198},
    {"event": "resume", "relative_time_seconds": 54.1, "whisper_t0_ms": 18210},
    {"event": "pause", "relative_time_seconds": 54.1, "whisper_t0_ms": 18210},
    {"event": "pause", "relative_time_seconds": 58.2, "whisper_t0_ms": 22170},
    {"event": "resume", "relative_time_seconds": 58.2, "whisper_t0_ms": 22170},
    {"event": "pause", "relative_time_seconds": 61.8, "whisper_t0_ms": 25569},
    {"event": "resume", "relative_time_seconds": 61.8, "whisper_t0_ms": 25569},
    {"event": "pause", "relative_time_seconds": 68.0, "whisper_t0_ms": 31903},
    {"event": "resume", "relative_time_seconds": 68.0, "whisper_t0_ms": 31903},
    {"event": "pause", "relative_time_seconds": 71.3, "whisper_t0_ms": 35391},
    {"event": "resume", "relative_time_seconds": 71.3, "whisper_t0_ms": 35391},
]

if __name__ == "__main__":
    print("Testing process_whisper_output with captured data")
    print(f"Test file: {test_file}")
    print()

    if not test_file.exists():
        print(f"Error: Test file not found: {test_file}")
        sys.exit(1)

    # Read raw lines
    with open(test_file) as f:
        raw_lines = f.readlines()

    print(f"Raw lines: {len(raw_lines)}")
    print(f"State changes: {len(state_changes)}")
    print()

    # Process
    result = process_whisper_output(raw_lines, state_changes)

    print()
    print("=" * 60)
    print("RESULT:")
    print("=" * 60)
    print(result)
    print()
    print(f"Word count: {len(result.split())}")
