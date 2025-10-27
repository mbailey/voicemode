#!/usr/bin/env python3
"""
Simple CLI test for stream_capture module.

Usage:
    python test_stream_capture.py [--max-duration SECONDS]

This will start stream_capture and listen for control phrases.
Speak naturally and say "send" or "i'm done" to finish.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add voice_mode to path
sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.stream_capture import stream_capture, check_whisper_stream_available


async def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    # Check if whisper-stream is available
    if not check_whisper_stream_available():
        logger.error("whisper-stream not found in PATH")
        logger.error("Please install whisper-stream or ensure it's in your PATH")
        return 1

    # Parse args
    max_duration = 120.0  # 2 minutes default
    if len(sys.argv) > 1 and sys.argv[1] == "--max-duration":
        max_duration = float(sys.argv[2])

    logger.info("=" * 60)
    logger.info("Stream Capture Test")
    logger.info("=" * 60)
    logger.info(f"Max duration: {max_duration}s")
    logger.info("Control phrases:")
    logger.info("  - 'send', 'i'm done', 'go ahead' -> Submit text")
    logger.info("  - 'stop', 'cancel' -> Discard text")
    logger.info("  - 'pause', 'hold on' -> Pause recording")
    logger.info("  - 'resume', 'continue' -> Resume recording")
    logger.info("  - 'play back', 'repeat' -> Review transcription")
    logger.info("")
    logger.info("Starting capture... Speak now!")
    logger.info("=" * 60)

    try:
        result = await stream_capture(max_duration=max_duration)

        logger.info("=" * 60)
        logger.info("Capture complete!")
        logger.info("=" * 60)
        logger.info(f"Duration: {result['duration']:.1f}s")
        logger.info(f"Control signal: {result['control_signal']}")
        logger.info(f"Raw segments: {len(result['segments'])}")
        logger.info(f"Final text ({len(result['text'].split())} words):")
        logger.info("")
        logger.info(result['text'])
        logger.info("=" * 60)

        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
