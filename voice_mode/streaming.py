"""
Streaming audio playback for voice-mode.

This module provides progressive audio playback to reduce latency
by playing audio chunks as they arrive from the TTS service.
"""

import asyncio
import io
import logging
import time
import queue
import threading
from typing import Optional, Tuple, AsyncIterator
from dataclasses import dataclass
from pathlib import Path
import numpy as np

import sounddevice as sd
from pydub import AudioSegment

from .config import (
    STREAM_CHUNK_SIZE,
    STREAM_BUFFER_MS,
    STREAM_MAX_BUFFER,
    SAMPLE_RATE,
    logger
)
from .utils import get_event_logger



@dataclass
class StreamMetrics:
    """Metrics for streaming playback performance."""
    ttfa: float = 0.0  # Time to first audio
    generation_time: float = 0.0
    playback_time: float = 0.0
    buffer_underruns: int = 0
    chunks_received: int = 0
    chunks_played: int = 0
    audio_path: Optional[str] = None  # Path to saved audio file


class AudioStreamPlayer:
    """Manages streaming audio playback with buffering."""
    
    def __init__(self, format: str, sample_rate: int = SAMPLE_RATE, channels: int = 1):
        self.format = format
        self.sample_rate = sample_rate
        self.channels = channels
        self.metrics = StreamMetrics()
        
        # Buffering
        self.audio_queue = queue.Queue(maxsize=int(STREAM_MAX_BUFFER * sample_rate))
        self.min_buffer_samples = int((STREAM_BUFFER_MS / 1000.0) * sample_rate)
        
        # State
        self.playing = False
        self.finished_downloading = False
        self.playback_started = False
        self.start_time = time.perf_counter()
        
        # Partial data buffer for format-specific decoding
        self.partial_data = b''
        
        # Initialize decoder based on format
        self.decoder = self._get_decoder()
        
        # Sounddevice stream
        self.stream = None
        self._lock = threading.Lock()
        
    def _get_decoder(self):
        """Get appropriate decoder for the audio format."""
        if self.format == "pcm":
            # PCM needs no decoding
            return None
        else:
            # For MP3, Opus, AAC, etc. we'll use PyDub
            return "pydub"
    
    def _audio_callback(self, outdata, frames, time_info, status):
        """Sounddevice callback for audio playback."""
        if status:
            logger.debug(f"Sounddevice status: {status}")
            
        try:
            # Fill output buffer from queue
            for i in range(frames):
                try:
                    sample = self.audio_queue.get_nowait()
                    outdata[i] = sample
                except queue.Empty:
                    # Buffer underrun
                    outdata[i] = 0
                    if self.playing:
                        self.metrics.buffer_underruns += 1
                        
            # Track playback progress
            if self.playing:
                self.metrics.chunks_played += 1
                
        except Exception as e:
            logger.error(f"Error in audio callback: {e}")
            outdata.fill(0)
    
    async def start(self):
        """Start the audio stream."""
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self._audio_callback,
            blocksize=1024,
            dtype='float32'
        )
        self.stream.start()
        logger.debug("Audio stream started")
    
    async def add_chunk(self, chunk: bytes) -> bool:
        """Add an audio chunk for playback.
        
        Returns True if this was the first chunk (TTFA moment).
        """
        first_chunk = self.metrics.chunks_received == 0
        self.metrics.chunks_received += 1
        
        # Combine with any partial data
        data = self.partial_data + chunk
        
        try:
            # Decode chunk based on format
            samples = await self._decode_chunk(data)
            
            if samples is not None:
                # Successfully decoded - clear partial data
                self.partial_data = b''
                
                # Add samples to playback queue
                await self._queue_samples(samples)
                
                # Check if we should start playback
                if not self.playback_started and self.audio_queue.qsize() >= self.min_buffer_samples:
                    self.playback_started = True
                    self.playing = True
                    self.metrics.ttfa = time.perf_counter() - self.start_time
                    logger.info(f"Starting playback - TTFA: {self.metrics.ttfa:.3f}s")
                    return True
            else:
                # Partial data - save for next chunk
                self.partial_data = data
                
        except Exception as e:
            logger.error(f"Error decoding chunk: {e}")
            # Skip this chunk but try to continue
            self.partial_data = b''
            
        return first_chunk and self.playback_started
    
    async def _decode_chunk(self, data: bytes) -> Optional[np.ndarray]:
        """Decode audio chunk to samples."""
        if self.format == "pcm":
            # PCM is raw samples - just convert
            if len(data) % 2 != 0:
                # Incomplete sample - save for next chunk
                return None
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            return samples

        elif self.decoder == "pydub":
            # Use PyDub for MP3, Opus, AAC, etc.
            # This is tricky because we need complete frames
            try:
                # Try to decode what we have
                audio = AudioSegment.from_file(io.BytesIO(data), format=self.format)
                samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
                return samples
            except Exception:
                # Need more data for a complete frame
                return None

        return None
    
    async def _queue_samples(self, samples: np.ndarray):
        """Add samples to the playback queue."""
        for sample in samples:
            try:
                self.audio_queue.put_nowait(sample)
            except queue.Full:
                # Buffer overflow - drop oldest samples
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(sample)
                except queue.Empty:
                    pass
    
    async def finish(self):
        """Signal that downloading is complete."""
        self.finished_downloading = True
        self.metrics.generation_time = time.perf_counter() - self.start_time
        
        # Process any remaining partial data
        if self.partial_data:
            # For formats like MP3, we might have a complete frame now
            samples = await self._decode_chunk(self.partial_data)
            if samples is not None:
                await self._queue_samples(samples)
        
        # Wait for playback to complete
        while not self.audio_queue.empty() or self.playing:
            await asyncio.sleep(0.1)
            
        self.metrics.playback_time = time.perf_counter() - self.start_time
        
    async def stop(self):
        """Stop playback and cleanup."""
        self.playing = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        logger.debug("Audio stream stopped")


async def stream_pcm_audio(
    text: str,
    openai_client,
    request_params: dict,
    debug: bool = False,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None
) -> Tuple[bool, StreamMetrics]:
    """Stream PCM audio with true HTTP streaming for minimal latency.
    
    Uses the OpenAI SDK's streaming response with iter_bytes() for real-time playback.
    """
    metrics = StreamMetrics()
    start_time = time.perf_counter()
    stream = None
    first_chunk_time = None
    save_buffer = io.BytesIO() if save_audio else None
    
    try:
        # Setup sounddevice stream for PCM playback
        # PCM parameters: 16-bit, mono, 24kHz (standard for TTS)
        audio_started = False
        audio_start_time = None
        
        def audio_callback(outdata, frames, time_info, status):
            """Callback to track when audio actually starts playing."""
            nonlocal audio_started, audio_start_time
            if not audio_started and frames > 0:
                audio_started = True
                audio_start_time = time.perf_counter()
        
        stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,  # Standard TTS sample rate (24kHz)
            channels=1,
            dtype='int16'  # PCM is 16-bit integers
            # Note: Can't use callback and write() together
        )
        stream.start()
        
        # Log TTS playback start when we start the stream
        event_logger = get_event_logger()
        if event_logger:
            event_logger.log_event(event_logger.TTS_PLAYBACK_START)
        
        # Don't add stream parameter - Kokoro defaults to true, OpenAI doesn't support it
        
        logger.info("Starting true HTTP streaming with iter_bytes()")
        
        # Use the streaming response API
        async with openai_client.audio.speech.with_streaming_response.create(
            **request_params
        ) as response:
            chunk_count = 0
            bytes_received = 0
            
            # Stream chunks as they arrive
            async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
                if chunk:
                    # Track first chunk received
                    if first_chunk_time is None:
                        first_chunk_time = time.perf_counter()
                        chunk_receive_time = first_chunk_time - start_time
                        logger.info(f"First audio chunk received after {chunk_receive_time:.3f}s")
                        
                        # Log TTS first audio event
                        event_logger = get_event_logger()
                        if event_logger:
                            event_logger.log_event(event_logger.TTS_FIRST_AUDIO)
                    
                    # Convert bytes to numpy array for sounddevice
                    # PCM data is already in the right format
                    audio_array = np.frombuffer(chunk, dtype=np.int16)
                    
                    # Play the chunk immediately
                    stream.write(audio_array)
                    
                    # Save chunk if enabled
                    if save_buffer:
                        save_buffer.write(chunk)
                    
                    chunk_count += 1
                    bytes_received += len(chunk)
                    metrics.chunks_received = chunk_count
                    metrics.chunks_played = chunk_count
                    
                    if debug and chunk_count % 10 == 0:
                        logger.debug(f"Streamed {chunk_count} chunks, {bytes_received} bytes")
        
        # Wait for playback to finish
        stream.stop()
        
        end_time = time.perf_counter()

        # Log TTS playback end with metrics
        if event_logger:
            tts_event_data = {
                "metrics": {
                    "ttfa_ms": round((first_chunk_time - start_time) * 1000, 1) if first_chunk_time else 0,
                    "total_time_ms": round((end_time - start_time) * 1000, 1),
                    "bytes_received": bytes_received,
                    "chunks": chunk_count,
                    "format": "pcm",
                    "sample_rate_hz": SAMPLE_RATE
                }
            }
            event_logger.log_event(event_logger.TTS_PLAYBACK_END, tts_event_data)
        metrics.generation_time = first_chunk_time - start_time if first_chunk_time else 0
        metrics.playback_time = end_time - start_time
        
        # Calculate true TTFA based on actual audio playback or chunk receipt
        if debug and audio_start_time:
            # Use actual playback start time when available
            metrics.ttfa = audio_start_time - start_time
            logger.info(f"True TTFA (audio started): {metrics.ttfa:.3f}s")
        elif first_chunk_time:
            # Fall back to first chunk time
            metrics.ttfa = first_chunk_time - start_time
            logger.info(f"TTFA (first chunk): {metrics.ttfa:.3f}s")
        
        logger.info(f"Streaming complete - TTFA: {metrics.ttfa:.3f}s, "
                   f"Total: {metrics.playback_time:.3f}s, "
                   f"Chunks: {metrics.chunks_received}")
        
        # Save audio if enabled
        if save_audio and save_buffer and audio_dir:
            try:
                from .core import save_debug_file
                save_buffer.seek(0)
                audio_data = save_buffer.read()
                # PCM format needs special handling - save as WAV
                if audio_data:
                    # For PCM, we need to save as WAV with proper headers
                    import wave
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
                        with wave.open(tmp_wav.name, 'wb') as wav_file:
                            wav_file.setnchannels(1)
                            wav_file.setsampwidth(2)  # 16-bit
                            wav_file.setframerate(SAMPLE_RATE)
                            wav_file.writeframes(audio_data)
                        # Read back the WAV file
                        with open(tmp_wav.name, 'rb') as f:
                            wav_data = f.read()
                        import os
                        os.unlink(tmp_wav.name)
                        audio_path = save_debug_file(wav_data, "tts", "wav", audio_dir, True, conversation_id)
                        if audio_path:
                            logger.info(f"TTS audio saved to: {audio_path}")
                            # Store audio path in metrics for the caller
                            metrics.audio_path = audio_path
            except Exception as e:
                logger.error(f"Failed to save TTS audio: {e}")
        
        return True, metrics
        
    except Exception as e:
        logger.error(f"PCM streaming failed: {e}")
        return False, metrics
        
    finally:
        if stream:
            stream.close()


async def stream_tts_audio(
    text: str,
    openai_client,
    request_params: dict,
    debug: bool = False,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None
) -> Tuple[bool, StreamMetrics]:
    """Stream TTS audio with progressive playback.
    
    Args:
        text: Text to convert to speech
        openai_client: OpenAI client instance
        request_params: Parameters for TTS request
        debug: Enable debug logging
        
    Returns:
        Tuple of (success, metrics)
    """
    format = request_params.get('response_format', 'pcm')
    logger.info(f"Starting streaming TTS with format: {format}")
    
    # PCM is best for streaming (no decoding needed)
    # For other formats, we may need buffering
    if format == 'pcm':
        return await stream_pcm_audio(
            text=text,
            openai_client=openai_client,
            request_params=request_params,
            debug=debug,
            save_audio=save_audio,
            audio_dir=audio_dir,
            conversation_id=conversation_id
        )
    else:
        # Use buffered streaming for formats that need decoding
        return await stream_with_buffering(
            text=text,
            openai_client=openai_client,
            request_params=request_params,
            debug=debug,
            save_audio=save_audio,
            audio_dir=audio_dir,
            conversation_id=conversation_id
        )


# Fallback for complex formats - buffer and decode complete file
async def stream_with_buffering(
    text: str,
    openai_client,
    request_params: dict,
    sample_rate: int = 24000,  # TTS standard sample rate
    debug: bool = False,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None
) -> Tuple[bool, StreamMetrics]:
    """Fallback streaming that buffers enough data to decode reliably.
    
    This is used for formats like MP3, Opus, etc where frame boundaries are critical.
    For Opus, we download the complete audio before playing.
    """
    format = request_params.get('response_format', 'pcm')
    logger.info(f"Using buffered streaming for format: {format}")
    
    metrics = StreamMetrics()
    start_time = time.perf_counter()
    
    # Buffer for accumulating chunks
    buffer = io.BytesIO()
    # Separate buffer for saving complete audio
    save_buffer = io.BytesIO() if save_audio else None
    audio_started = False
    stream = None
    
    try:
        # Setup sounddevice stream
        stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype='float32'
        )
        stream.start()
        
        # Don't add stream parameter - Kokoro defaults to true, OpenAI doesn't support it
        
        # Use the streaming response API for true HTTP streaming
        async with openai_client.audio.speech.with_streaming_response.create(
            **request_params
        ) as response:
            first_chunk_time = None
            
            # Stream chunks as they arrive
            async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
                if chunk:
                    # Track first chunk for TTFA
                    if first_chunk_time is None:
                        first_chunk_time = time.perf_counter()
                        metrics.ttfa = first_chunk_time - start_time
                        logger.info(f"First chunk received - TTFA: {metrics.ttfa:.3f}s")
                    
                    buffer.write(chunk)
                    metrics.chunks_received += 1
                    
                    # Also accumulate in save buffer if saving is enabled
                    if save_buffer:
                        save_buffer.write(chunk)
                    
                    # Try to decode when we have enough data (e.g., 32KB)
                    if buffer.tell() > 32768 and not audio_started:
                        buffer.seek(0)
                        try:
                            # Attempt to decode what we have
                            audio = AudioSegment.from_file(buffer, format=format)
                            samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
                            
                            # Start playback
                            metrics.ttfa = time.perf_counter() - start_time
                            audio_started = True
                            logger.info(f"Buffered streaming started - TTFA: {metrics.ttfa:.3f}s")
                            
                            # Play audio
                            stream.write(samples)
                            metrics.chunks_played += len(samples) // 1024
                            
                            # Reset buffer for next batch
                            buffer = io.BytesIO()
                            
                        except Exception as e:
                            # Not enough valid data yet
                            buffer.seek(0, io.SEEK_END)
        
        # Process any remaining data
        if buffer.tell() > 0:
            buffer.seek(0)
            try:
                audio = AudioSegment.from_file(buffer, format=format)
                samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
                
                if not audio_started:
                    metrics.ttfa = time.perf_counter() - start_time
                    
                stream.write(samples)
                metrics.chunks_played += len(samples) // 1024
                
            except Exception as e:
                logger.error(f"Failed to decode final buffer: {e}")
        
        metrics.generation_time = time.perf_counter() - start_time
        metrics.playback_time = metrics.generation_time  # Approximate
        
        # Save audio if enabled
        if save_audio and save_buffer and audio_dir:
            try:
                from .core import save_debug_file
                save_buffer.seek(0)
                audio_data = save_buffer.read()
                audio_path = save_debug_file(audio_data, "tts", format, audio_dir, True, conversation_id)
                if audio_path:
                    logger.info(f"TTS audio saved to: {audio_path}")
            except Exception as e:
                logger.error(f"Failed to save TTS audio: {e}")
        
        return True, metrics
        
    except Exception as e:
        logger.error(f"Buffered streaming failed: {e}")
        return False, metrics
        
    finally:
        if stream:
            stream.stop()
            stream.close()