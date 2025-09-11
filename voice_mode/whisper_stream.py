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


async def continuous_listen_with_whisper_stream(
    wake_words: List[str],
    command_callback,  # Callable[[str, str], Awaitable[None]]
    max_idle_time: float = 3600.0,  # 1 hour idle timeout
    model_path: Optional[Path] = None
) -> None:
    """
    Continuous listening mode with wake word detection.
    
    This function launches whisper-stream and continuously listens for wake words,
    then extracts and processes commands following the wake words.
    
    Args:
        wake_words: List of wake words to listen for (case-insensitive)
        command_callback: Async function to call with (wake_word, command)
        max_idle_time: Maximum idle time before auto-shutdown
        model_path: Path to whisper model (defaults to base for efficiency)
    """
    from collections import deque
    
    if model_path is None:
        # Use base model for continuous listening (more efficient)
        base_model = Path.home() / ".voicemode" / "services" / "whisper" / "models" / "ggml-base.bin"
        if base_model.exists():
            model_path = base_model
        else:
            model_path = DEFAULT_MODEL_PATH
    
    # Normalize wake words to lowercase
    wake_words_lower = [w.lower().strip() for w in wake_words]
    
    logger.info(f"Starting continuous listening with wake words: {wake_words}")
    logger.info(f"Using model: {model_path}")
    
    # Build whisper-stream command for continuous mode
    cmd = [
        "whisper-stream",
        "-m", str(model_path),
        "--step", "0",  # VAD mode
        "-t", "6",  # threads
        "--length", "5000",  # Shorter chunks for quicker wake word detection
        "--keep", "0",  # Don't keep previous audio
        "-vth", "0.6",  # VAD threshold
        "-l", "en"  # English
    ]
    
    logger.debug(f"Launching whisper-stream: {' '.join(cmd)}")
    
    # Start whisper-stream process
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,  # Capture stderr for initialization monitoring
        text=False
    )
    
    # Wait for initialization
    logger.info("Waiting for whisper-stream to initialize...")
    init_complete = False
    init_timeout = 10.0  # 10 seconds to initialize
    init_start = time.time()
    
    while time.time() - init_start < init_timeout:
        # Check stderr for initialization messages
        try:
            stderr_line = await asyncio.wait_for(
                process.stderr.readline(),
                timeout=0.5
            )
            if stderr_line:
                line = stderr_line.decode('utf-8', errors='ignore').strip()
                logger.debug(f"Whisper init: {line}")
                # Check if model is loaded
                if "whisper_model_load:" in line or "n_text_layer" in line:
                    init_complete = True
                    logger.info("Whisper-stream initialized successfully")
                    break
        except asyncio.TimeoutError:
            # Check if process is still running
            if process.returncode is not None:
                logger.error("Whisper-stream process ended during initialization")
                raise RuntimeError("Whisper-stream failed to start")
    
    if not init_complete:
        logger.warning("Whisper-stream initialization timeout - continuing anyway")
    
    # Use a deque to maintain a rolling buffer of recent transcriptions
    buffer = deque(maxlen=100)  # Keep last 100 transcription segments
    last_activity = time.time()
    
    try:
        while True:
            # Check idle timeout
            if time.time() - last_activity > max_idle_time:
                logger.info("Idle timeout reached, shutting down listener")
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
            
            # Skip non-transcription lines
            if not line or len(line) < 2:
                continue
            
            # Skip whisper-stream debug/log lines
            if (line.startswith('whisper') or 
                line.startswith('init:') or 
                line.startswith('main:') or
                line.startswith('###') or
                line.startswith('⏱️') or
                'Transcription' in line and 'START' in line or
                'Transcription' in line and 'END' in line or
                line.startswith('[Start') or
                line == '[Start speaking]' or
                '\033[' in line or  # ANSI codes
                (' = ' in line and 'ms' in line and len(line) < 20)):  # Timer lines
                continue
            
            logger.debug(f"Transcription: {line}")
            buffer.append(line)
            
            # Combine recent buffer for wake word detection
            # Look at last few segments to catch wake words that might span segments
            recent_text = " ".join(list(buffer)[-5:]).lower()
            
            # Check for wake words
            for wake_word in wake_words_lower:
                if wake_word in recent_text:
                    logger.info(f"Wake word detected: '{wake_word}'")
                    
                    # Extract command after wake word
                    # Find the position of wake word in the combined text
                    wake_pos = recent_text.rfind(wake_word)
                    command_text = recent_text[wake_pos + len(wake_word):].strip()
                    
                    # If we have a command, process it
                    if command_text:
                        logger.info(f"Command extracted: '{command_text}'")
                        await command_callback(wake_word, command_text)
                        
                        # Clear buffer after processing to avoid re-triggering
                        buffer.clear()
                        last_activity = time.time()
                        break
                    else:
                        # Wake word detected but no command yet, keep listening
                        logger.debug("Wake word detected, waiting for command...")
                        # Don't clear buffer yet, command might come in next segment
                        last_activity = time.time()
    
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


def extract_command_after_wake(full_text: str, wake_word: str) -> Optional[str]:
    """
    Extract command text that comes after a wake word.
    
    Args:
        full_text: The full transcribed text
        wake_word: The wake word that was detected (lowercase)
    
    Returns:
        The command text after the wake word, or None if no command found
    """
    text_lower = full_text.lower()
    wake_pos = text_lower.rfind(wake_word)
    
    if wake_pos == -1:
        return None
    
    # Extract everything after the wake word
    command = full_text[wake_pos + len(wake_word):].strip()
    
    # Clean up the command (remove filler words at the start)
    filler_words = ["um", "uh", "well", "so", "like", "please"]
    words = command.split()
    while words and words[0].lower() in filler_words:
        words.pop(0)
    
    return " ".join(words) if words else None