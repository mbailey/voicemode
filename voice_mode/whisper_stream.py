"""Whisper-stream integration for uninterrupted recording mode."""

import asyncio
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Tuple, List, Optional
import numpy as np

# Optional soundfile for audio loading
try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

logger = logging.getLogger("voice-mode")

# Default configuration
DEFAULT_END_PHRASES = ["i'm done", "go ahead", "that's all", "okay process that"]
DEFAULT_MODEL_PATH = Path.home() / ".voicemode" / "services" / "whisper" / "models" / "ggml-large-v2.bin"

def deduplicate_transcription(segments: List[str]) -> str:
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

async def record_with_whisper_stream(
    end_phrases: Optional[List[str]] = None,
    max_duration: float = 600.0,  # 10 minutes max
    model_path: Optional[Path] = None
) -> Tuple[np.ndarray, str]:
    """
    Record audio using whisper-stream subprocess with end phrase detection.
    
    This function launches whisper-stream in VAD mode and collects transcriptions
    until one of the end phrases is detected or max duration is reached.
    
    Args:
        end_phrases: List of phrases that end recording (case-insensitive)
        max_duration: Maximum recording duration in seconds
        model_path: Path to whisper model (defaults to large-v2)
    
    Returns:
        Tuple of (audio_data, transcribed_text)
        - audio_data: Combined audio as numpy array (16kHz mono)
        - transcribed_text: Full transcription text
    """
    
    if end_phrases is None:
        end_phrases = DEFAULT_END_PHRASES
    
    if model_path is None:
        model_path = DEFAULT_MODEL_PATH
    
    # Normalize end phrases to lowercase for comparison
    end_phrases_lower = [phrase.lower() for phrase in end_phrases]
    
    logger.info(f"Starting whisper-stream recording (max {max_duration}s)")
    logger.info(f"End phrases: {end_phrases}")
    
    # Create temp directory for audio files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_file = temp_path / "recording.wav"
        
        # Build whisper-stream command
        cmd = [
            "whisper-stream",
            "-m", str(model_path),
            "--step", "0",  # VAD mode - process full utterances
            "-t", "6",  # threads
            "--length", "30000",  # 30 seconds max per chunk
            "--keep", "0",  # Don't keep audio from previous chunks (reduces overlap)
            "-vth", "0.6",  # VAD threshold
            "-l", "en"  # English
        ]
        
        logger.debug(f"Launching whisper-stream: {' '.join(cmd)}")
        
        # Start whisper-stream process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # Discard stderr (initialization messages)
            text=False  # We'll decode manually to handle partial lines
        )
        
        # Track recording state
        full_text = []
        start_time = time.time()
        found_end_phrase = False
        
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
                
                # Decode and clean the line
                try:
                    line = line_bytes.decode('utf-8').strip()
                except UnicodeDecodeError:
                    continue
                
                # Skip non-transcription lines (logs, debug output, etc)
                if not line:
                    continue
                    
                # Skip whisper-stream debug/log lines
                if (line.startswith('whisper') or 
                    line.startswith('init:') or 
                    line.startswith('main:') or
                    line.startswith('###') or  # Skip debug markers
                    line.startswith('⏱️') or   # Skip timer lines
                    'Transcription' in line and 'START' in line or
                    'Transcription' in line and 'END' in line or
                    line.startswith('[Start') or
                    line == '[Start speaking]'):
                    continue
                
                # Skip ANSI color codes and special formatting
                if '\033[' in line:
                    continue
                
                # Only process lines that contain actual transcribed text
                # Skip timer lines that only contain "t0 = X ms" or similar
                if ' = ' in line and 'ms' in line and len(line) < 20:
                    continue
                
                # Skip empty transcriptions or very short non-speech
                if len(line) < 2:
                    continue
                    
                logger.debug(f"Transcription: {line}")
                full_text.append(line)
                
                # Check for end phrases
                line_lower = line.lower()
                for phrase in end_phrases_lower:
                    if phrase in line_lower:
                        logger.info(f"End phrase detected: '{phrase}' in '{line}'")
                        found_end_phrase = True
                        break
                
                if found_end_phrase:
                    break
            
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
        transcribed_text = deduplicate_transcription(full_text)
        logger.info(f"Recording complete. Transcribed {len(full_text)} segments -> {len(transcribed_text.split())} words after deduplication")
        
        # Create a dummy audio array since we're not saving audio
        # The important part is the transcription, not the audio
        # Use a reasonable length based on recording duration
        elapsed = time.time() - start_time
        samples = int(16000 * elapsed)  # 16kHz sample rate
        audio_data = np.zeros(samples, dtype=np.float32)
        logger.debug(f"Created placeholder audio array with {samples} samples ({elapsed:.1f}s)")
        
        return audio_data, transcribed_text


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