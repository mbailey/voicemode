"""
Stream capture with whisper-stream integration and control phrase detection.

Provides hands-free voice control over recording with cassette-deck style commands:
- send/done: Submit accumulated text
- pause: Temporarily stop recording
- resume: Continue recording
- play: Read back transcription
- stop: Discard and exit
"""

import asyncio
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("voicemode")

# Default control phrases
DEFAULT_CONTROL_PHRASES = {
    "send": ["send", "i'm done", "go ahead", "that's all"],
    "pause": ["pause", "hold on"],
    "resume": ["resume", "continue", "unpause"],
    "play": ["play back", "repeat", "read that"],
    "stop": ["stop", "cancel", "discard"]
}


def deduplicate_segments(segments: List[str]) -> str:
    """
    Deduplicate transcription segments from whisper-stream.

    Whisper-stream can output overlapping or repeated segments as it refines
    transcriptions. This function removes duplicates while preserving order.

    Strategy:
    1. Remove exact duplicates
    2. If a segment is contained within a later segment, keep only the later one
    3. Merge segments that have significant overlap

    Args:
        segments: List of transcription segments from whisper-stream

    Returns:
        Deduplicated transcription text
    """
    if not segments:
        return ""

    # First pass: remove exact duplicates while preserving order
    seen = set()
    unique_segments = []
    for segment in segments:
        segment = segment.strip()
        if segment and segment not in seen:
            seen.add(segment)
            unique_segments.append(segment)

    if len(unique_segments) <= 1:
        return " ".join(unique_segments)

    # Second pass: remove segments that are substrings of later segments
    filtered = []
    for i, current in enumerate(unique_segments):
        is_substring = False
        # Check if this segment is a substring of any later segment
        for later in unique_segments[i+1:]:
            if current in later:
                is_substring = True
                break
        if not is_substring:
            filtered.append(current)

    # Third pass: merge overlapping segments
    if len(filtered) <= 1:
        return " ".join(filtered)

    final = [filtered[0]]
    for segment in filtered[1:]:
        last = final[-1]
        # Check for overlap at the end of last segment and beginning of current
        words_last = last.split()
        words_current = segment.split()

        # Find overlap by checking if end of last matches beginning of current
        overlap_found = False
        for overlap_size in range(min(len(words_last), len(words_current)), 0, -1):
            if words_last[-overlap_size:] == words_current[:overlap_size]:
                # Merge by removing the overlapping part from current segment
                merged = last + " " + " ".join(words_current[overlap_size:])
                final[-1] = merged.strip()
                overlap_found = True
                break

        if not overlap_found:
            final.append(segment)

    return " ".join(final)


def detect_control_phrase(text: str, control_phrases: Dict[str, List[str]]) -> Optional[str]:
    """
    Detect if text contains a control phrase.

    Args:
        text: Transcribed text to check
        control_phrases: Dict mapping control signals to trigger phrases

    Returns:
        Control signal name if detected, None otherwise
    """
    text_lower = text.lower().strip()

    # Check each control signal's phrases
    for signal, phrases in control_phrases.items():
        for phrase in phrases:
            if phrase.lower() in text_lower:
                logger.debug(f"Detected control phrase '{phrase}' -> signal '{signal}'")
                return signal

    return None


async def stream_capture(
    control_phrases: Optional[Dict[str, List[str]]] = None,
    max_duration: float = 600.0,
    model_path: Optional[Path] = None,
    initial_mode: str = "recording"
) -> Dict[str, Any]:
    """
    Capture audio with whisper-stream and detect control commands.

    This is the core stream capture function that runs whisper-stream as a subprocess,
    collects transcriptions in real-time, and watches for control phrases.

    Args:
        control_phrases: Dict mapping control signals to trigger phrases.
            Example: {"send": ["send", "done"], "pause": ["pause"]}
            If None, uses DEFAULT_CONTROL_PHRASES
        max_duration: Maximum capture duration in seconds
        model_path: Path to whisper model (defaults to voicemode large-v2)
        initial_mode: Start in "recording" or "paused" state

    Returns:
        {
            "text": "accumulated transcription",
            "control_signal": "send"|"pause"|"resume"|"play"|"stop"|None,
            "segments": List[str],  # Raw segments for debugging
            "duration": float
        }
    """
    if control_phrases is None:
        control_phrases = DEFAULT_CONTROL_PHRASES

    if model_path is None:
        model_path = Path.home() / ".voicemode" / "services" / "whisper" / "models" / "ggml-large-v2.bin"

    if not model_path.exists():
        raise FileNotFoundError(f"Whisper model not found: {model_path}")

    logger.info(f"Starting stream capture (max {max_duration}s, mode: {initial_mode})")
    logger.debug(f"Control phrases: {control_phrases}")

    # Build whisper-stream command
    cmd = [
        "whisper-stream",
        "-m", str(model_path),
        "--step", "0",  # VAD mode - process full utterances
        "-t", "6",      # 6 threads
    ]

    logger.debug(f"Launching whisper-stream: {' '.join(cmd)}")

    # Start whisper-stream subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )

    # Track state
    segments = []
    start_time = time.time()
    control_signal = None
    current_segment_t0 = None

    try:
        # Read output line by line
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > max_duration:
                logger.info(f"Max duration reached ({max_duration}s)")
                break

            # Read line with timeout
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # No output, check if process is still running
                if process.returncode is not None:
                    logger.warning("Whisper-stream process ended unexpectedly")
                    break
                continue

            if not line:
                # End of stream
                if process.returncode is not None:
                    break
                continue

            line = line.strip()
            if not line:
                continue

            # Parse timing from START markers
            # Format: ### Transcription N START | t0 = 150761 ms | t1 = 160761 ms
            if line.startswith("### Transcription") and "START" in line:
                match = re.search(r't0 = (\d+) ms', line)
                if match:
                    current_segment_t0 = int(match.group(1))
                    logger.debug(f"Segment start at t0={current_segment_t0}ms")
                continue

            # Filter out END markers
            if line.startswith("### Transcription") and "END" in line:
                logger.debug("Segment end")
                continue

            # Filter out [Start speaking] messages
            if line == "[Start speaking]":
                logger.debug("Speech started")
                continue

            # Only process lines that look like transcriptions
            # Format: [HH:MM:SS.mmm --> HH:MM:SS.mmm]  transcribed text
            if line.startswith("[") and "-->" in line:
                # Extract just the text part (after the timestamp)
                parts = line.split("]", 1)
                if len(parts) == 2:
                    text = parts[1].strip()
                    if text:
                        logger.debug(f"Transcription: {text}")
                        segments.append(text)

                        # Check for control phrases
                        signal = detect_control_phrase(text, control_phrases)
                        if signal:
                            logger.info(f"Control signal detected: {signal}")
                            control_signal = signal
                            # Terminal signals end capture immediately
                            if signal in ["send", "stop", "play"]:
                                break
            else:
                # Log unexpected output for debugging
                if not line.startswith("whisper") and not line.startswith("main:"):
                    logger.debug(f"Unexpected output: {line}")

    finally:
        # Terminate the process
        if process.returncode is None:
            logger.info("Terminating whisper-stream process")
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Force killing whisper-stream process")
                process.kill()
                await process.wait()

    # Deduplicate and combine transcribed text
    text = deduplicate_segments(segments)

    # Strip control phrases from the final text
    if control_signal:
        # Remove the control phrase that triggered the signal
        for phrase in control_phrases.get(control_signal, []):
            # Case-insensitive removal
            text_lower = text.lower()
            phrase_lower = phrase.lower()
            if phrase_lower in text_lower:
                # Find the phrase and remove it
                idx = text_lower.find(phrase_lower)
                text = text[:idx] + text[idx+len(phrase):]
                text = text.strip()
                break

    duration = time.time() - start_time
    logger.info(f"Capture complete: {len(segments)} segments -> {len(text.split())} words, "
                f"duration: {duration:.1f}s, signal: {control_signal}")

    return {
        "text": text,
        "control_signal": control_signal,
        "segments": segments,
        "duration": duration
    }


def check_whisper_stream_available() -> bool:
    """Check if whisper-stream is available in PATH."""
    try:
        result = subprocess.run(
            ["which", "whisper-stream"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
