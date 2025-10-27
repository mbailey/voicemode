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
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger("voicemode")


async def play_control_feedback(control_signal: str) -> None:
    """
    Play audio feedback for control commands.

    Uses simple chimes from core module for immediate feedback.
    """
    try:
        from voice_mode.core import play_chime_start, play_chime_end

        if control_signal == "pause":
            # Descending tone for pause
            await play_chime_end(leading_silence=0.0, trailing_silence=0.1)
        elif control_signal == "resume":
            # Ascending tone for resume
            await play_chime_start(leading_silence=0.0, trailing_silence=0.1)
        elif control_signal in ["send", "stop"]:
            # Double beep for terminal commands
            await play_chime_end(leading_silence=0.0, trailing_silence=0.1)
            await asyncio.sleep(0.1)
            await play_chime_end(leading_silence=0.0, trailing_silence=0.0)
    except Exception as e:
        logger.debug(f"Audio feedback failed: {e}")
        # Don't interrupt capture if feedback fails


@dataclass
class WhisperSegment:
    """Represents a single whisper-stream output segment with timing."""
    start_time: float  # seconds
    end_time: float    # seconds
    text: str

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

    logger.debug(f"Deduplicating {len(segments)} segments")

    # First pass: remove exact duplicates while preserving order
    seen = set()
    unique_segments = []
    for segment in segments:
        segment = segment.strip()
        if segment and segment not in seen:
            seen.add(segment)
            unique_segments.append(segment)

    logger.debug(f"After exact duplicate removal: {len(unique_segments)} segments")

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
                logger.debug(f"Removing substring: '{current[:50]}...' (contained in later segment)")
                break
        if not is_substring:
            filtered.append(current)

    logger.debug(f"After substring removal: {len(filtered)} segments")

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
                logger.debug(f"Merged overlap of {overlap_size} words")
                break

        if not overlap_found:
            final.append(segment)

    logger.debug(f"After merging overlaps: {len(final)} segments")
    result = " ".join(final)
    logger.info(f"Deduplication: {len(segments)} -> {len(final)} segments, {len(result.split())} words")

    return result


def parse_whisper_timestamp(timestamp_str: str) -> float:
    """
    Parse whisper timestamp format to seconds.

    Format: [HH:MM:SS.mmm --> HH:MM:SS.mmm]  text

    Args:
        timestamp_str: Timestamp string like "00:00:15.480"

    Returns:
        Time in seconds (float)
    """
    parts = timestamp_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def parse_whisper_line(line: str) -> Optional[WhisperSegment]:
    """
    Parse a whisper-stream output line into a segment.

    Format: [00:00:15.000 --> 00:00:20.000]   text here

    Args:
        line: Line from whisper-stream output

    Returns:
        WhisperSegment or None if line doesn't match format
    """
    if not line.startswith("[") or "-->" not in line:
        return None

    try:
        # Extract timestamps and text
        match = re.match(r'\[([0-9:.]+)\s+-->\s+([0-9:.]+)\]\s+(.*)', line)
        if not match:
            return None

        start_str, end_str, text = match.groups()
        start_time = parse_whisper_timestamp(start_str)
        end_time = parse_whisper_timestamp(end_str)

        return WhisperSegment(
            start_time=start_time,
            end_time=end_time,
            text=text.strip()
        )
    except Exception as e:
        logger.debug(f"Failed to parse whisper line: {line[:50]}... Error: {e}")
        return None


def process_whisper_output(
    raw_lines: List[str],
    state_changes: List[Dict[str, Any]]
) -> str:
    """
    Process raw whisper-stream output with pause/resume filtering.

    Algorithm:
    1. Parse all lines into WhisperSegment objects with timestamps
    2. Build pause time ranges from state_changes
    3. Group segments by their start time (t=0 vs t>0)
    4. For t=0 segments: take the longest/latest complete transcription
    5. For t>0 segments: filter out any that fall within paused ranges
    6. Deduplicate overlapping segments
    7. Return final text

    Args:
        raw_lines: Raw output lines from whisper-stream (from -f file)
        state_changes: List of {event, relative_time_seconds, whisper_t0_ms}

    Returns:
        Deduplicated and filtered transcription text
    """
    logger.info(f"Processing {len(raw_lines)} raw whisper lines with {len(state_changes)} state changes")

    # Parse all segments
    segments = []
    for line in raw_lines:
        seg = parse_whisper_line(line)
        if seg and seg.text:  # Ignore empty segments
            segments.append(seg)

    logger.info(f"Parsed {len(segments)} valid segments from raw output")

    # Build paused time ranges
    # Track pairs of (pause_time, resume_time)
    paused_ranges = []
    pause_start = None

    for change in state_changes:
        if change["event"] == "pause":
            if pause_start is None:  # Start a new pause period
                pause_start = change["relative_time_seconds"]
        elif change["event"] == "resume":
            if pause_start is not None:  # End the pause period
                paused_ranges.append((pause_start, change["relative_time_seconds"]))
                pause_start = None

    # If still paused at end, close the range
    if pause_start is not None:
        paused_ranges.append((pause_start, float('inf')))

    logger.info(f"Paused time ranges: {paused_ranges}")

    # Separate segments into t=0 (full retranscriptions) and t>0 (incremental)
    t0_segments = [s for s in segments if s.start_time == 0.0]
    incremental_segments = [s for s in segments if s.start_time > 0.0]

    logger.info(f"Segments: {len(t0_segments)} at t=0, {len(incremental_segments)} incremental")

    # For t=0 segments: Take the longest one (most complete transcription)
    # These are full re-transcriptions of the entire VAD chunk
    final_segments = []

    if t0_segments:
        # Find the longest t=0 segment (most complete)
        longest = max(t0_segments, key=lambda s: len(s.text))
        logger.info(f"Selected longest t=0 segment: {len(longest.text)} chars, {len(longest.text.split())} words")

        # Split this segment into individual parts based on timing if available
        # For now, just use it as is
        final_segments.append(longest.text)

    # For incremental segments: filter by pause ranges
    for seg in incremental_segments:
        # Check if this segment's time falls within any paused range
        is_paused = False
        for pause_start, pause_end in paused_ranges:
            # If segment starts or ends during pause, skip it
            if (pause_start <= seg.start_time <= pause_end or
                pause_start <= seg.end_time <= pause_end):
                is_paused = True
                logger.debug(f"Skipping paused segment [{seg.start_time:.1f}s-{seg.end_time:.1f}s]: {seg.text[:50]}...")
                break

        if not is_paused:
            logger.debug(f"Keeping segment [{seg.start_time:.1f}s-{seg.end_time:.1f}s]: {seg.text[:50]}...")
            final_segments.append(seg.text)

    # Simple join for now - could apply deduplication here
    result = " ".join(final_segments)
    logger.info(f"Processed output: {len(final_segments)} segments, {len(result.split())} words")

    return result


def detect_control_phrase(text: str, control_phrases: Dict[str, List[str]]) -> Optional[str]:
    """
    Detect if text contains a control phrase using word boundaries.

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
            phrase_lower = phrase.lower()

            # Use word boundary matching for single-word phrases
            # For multi-word phrases, check if they appear as is
            if ' ' in phrase_lower:
                # Multi-word phrase - just check if it appears
                if phrase_lower in text_lower:
                    logger.debug(f"Detected control phrase '{phrase}' -> signal '{signal}'")
                    return signal
            else:
                # Single-word phrase - check with word boundaries
                # Strip punctuation from each word before matching
                import string
                words = text_lower.split()
                words_no_punct = [w.strip(string.punctuation) for w in words]
                if phrase_lower in words_no_punct:
                    logger.debug(f"Detected control phrase '{phrase}' -> signal '{signal}'")
                    return signal

    return None


async def stream_capture(
    control_phrases: Optional[Dict[str, List[str]]] = None,
    max_duration: float = 600.0,
    model_path: Optional[Path] = None,
    initial_mode: str = "recording",
    debug_output_file: Optional[Path] = None
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
        debug_output_file: Optional path to save raw whisper-stream output for analysis

    Returns:
        {
            "text": "accumulated transcription",
            "control_signal": "send"|"pause"|"resume"|"play"|"stop"|None,
            "segments": List[str],  # Raw segments for debugging
            "duration": float,
            "state_changes": List[dict]  # Pause/resume events with timestamps
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
        "--step", "0",     # VAD mode - process full utterances
        "--keep", "0",     # Don't keep audio from previous chunks (reduces overlap)
        "--length", "30000",  # 30 seconds max per chunk
        "-t", "6",         # 6 threads
    ]

    # Add file output for debugging if requested
    if debug_output_file:
        debug_output_file.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["-f", str(debug_output_file)])
        logger.info(f"Debug output will be saved to: {debug_output_file}")

    logger.info(f"Launching whisper-stream: {' '.join(cmd)}")

    # Start whisper-stream subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
        # Note: Read bytes and decode manually (text=True not supported with PIPE)
    )

    # Track state
    segments = []
    start_time = time.time()
    control_signal = None
    current_segment_t0 = None
    current_mode = initial_mode  # "recording" or "paused"
    control_phrases_detected = []  # Track all control phrases to strip later
    recording_started_at = start_time if initial_mode == "recording" else None  # Track when we last entered recording mode
    skip_next_segments = 0  # Skip N segments after resume to avoid stale refinements
    state_changes = []  # Track pause/resume events with timestamps

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
                line_bytes = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # No output, check if process is still running
                if process.returncode is not None:
                    logger.warning("Whisper-stream process ended unexpectedly")
                    break
                continue

            if not line_bytes:
                # End of stream
                if process.returncode is not None:
                    break
                continue

            # Decode bytes to text
            try:
                line = line_bytes.decode('utf-8').strip()
            except UnicodeDecodeError:
                continue
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
                        # Check for control phrases BEFORE any processing
                        signal = detect_control_phrase(text, control_phrases)

                        if signal:
                            logger.info(f"Control signal detected: {signal} in '{text}'")
                            control_phrases_detected.append(text)  # Track for stripping later

                            # Play immediate audio feedback
                            await play_control_feedback(signal)

                            # Handle state transitions BEFORE checking current_mode
                            if signal == "pause":
                                relative_time = time.time() - start_time
                                state_changes.append({
                                    "event": "pause",
                                    "relative_time_seconds": relative_time,
                                    "whisper_t0_ms": current_segment_t0
                                })
                                logger.info(f"State: RECORDING -> PAUSED (at {relative_time:.1f}s)")
                                current_mode = "paused"
                                recording_started_at = None  # Clear recording timestamp
                                # Don't add this segment, don't log it
                                continue
                            elif signal == "resume":
                                relative_time = time.time() - start_time
                                state_changes.append({
                                    "event": "resume",
                                    "relative_time_seconds": relative_time,
                                    "whisper_t0_ms": current_segment_t0
                                })
                                logger.info(f"State: PAUSED -> RECORDING (at {relative_time:.1f}s)")
                                current_mode = "recording"
                                recording_started_at = time.time()  # Mark when we resumed
                                # Skip next 3 segments to avoid stale whisper refinements from paused period
                                skip_next_segments = 3
                                logger.debug(f"Recording resumed, will skip next {skip_next_segments} segments")
                                # Don't add this segment, don't log it
                                continue
                            elif signal in ["send", "stop", "play"]:
                                # Terminal signals - set and break immediately
                                control_signal = signal
                                break
                            # If we get here with a signal, something's wrong
                            logger.warning(f"Unhandled signal: {signal}")

                        # Now check mode for non-control segments
                        # State transitions happen ABOVE, so current_mode is already updated

                        # Skip segments if we're in the post-resume grace period
                        if skip_next_segments > 0:
                            skip_next_segments -= 1
                            logger.info(f"⏭️  [skipped post-resume] {text} ({skip_next_segments} more to skip)")
                            continue

                        if current_mode == "recording":
                            logger.info(f"📝 {text}")
                            segments.append(text)
                        else:  # paused
                            logger.info(f"⏸️  [ignored] {text}")
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

    # Strip ALL control phrases that were detected during capture
    # This removes pause, resume, send, etc. from the final text
    for control_text in control_phrases_detected:
        # Remove each control phrase occurrence (case-insensitive)
        text_lower = text.lower()
        control_lower = control_text.lower()

        # Find and remove the control phrase
        idx = text_lower.find(control_lower)
        if idx != -1:
            text = text[:idx] + text[idx+len(control_text):]
            text = text.strip()
            # Update text_lower for next iteration
            text_lower = text.lower()

    duration = time.time() - start_time
    logger.info(f"Capture complete: {len(segments)} segments -> {len(text.split())} words, "
                f"duration: {duration:.1f}s, signal: {control_signal}")

    # Log state changes summary
    if state_changes:
        logger.info(f"State changes during capture:")
        for change in state_changes:
            logger.info(f"  {change['event']}: {change['relative_time_seconds']:.1f}s "
                       f"(whisper t0: {change['whisper_t0_ms']}ms)")

    return {
        "text": text,
        "control_signal": control_signal,
        "segments": segments,
        "duration": duration,
        "state_changes": state_changes
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
