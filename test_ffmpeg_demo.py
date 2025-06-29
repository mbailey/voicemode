#!/usr/bin/env python
"""Demo script to show FFmpeg detection behavior."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_mode.utils.ffmpeg_check import check_and_report_ffmpeg, ensure_ffmpeg_or_exit

print("=== Testing FFmpeg Detection ===\n")

print("1. Testing check_and_report_ffmpeg():")
print("-" * 40)
result = check_and_report_ffmpeg()
print(f"Result: FFmpeg {'found' if result else 'NOT FOUND'}")

print("\n2. Testing ensure_ffmpeg_or_exit():")
print("-" * 40)
try:
    ensure_ffmpeg_or_exit()
except SystemExit:
    print("(Script would exit here)")