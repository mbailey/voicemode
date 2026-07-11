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
    TTS_TRAILING_SILENCE,
    logger
)
from . import config
from .control_channel import get_control_state
from .history_buffer import get_history_buffer
from .utils import get_event_logger, update_latest_symlinks


# VM-1676 control channel: how often a playback loop re-checks the control
# state while holding on a pause. ~50ms keeps the resume reaction imperceptible
# without busy-spinning the CPU. The per-chunk *stop* check itself is a single
# cheap snapshot, so stop latency is bounded by one chunk (~85ms at 4096 B PCM
# @ 24kHz) -- well under the ~200ms barge-in target.
CONTROL_POLL_INTERVAL = 0.05


async def _poll_control_channel() -> bool:
    """Honour the process-wide control channel between audio chunks (VM-1676/VM-1685).

    Called by every TTS streaming write loop just before it writes a chunk.

    * Returns ``True`` if playback should **break** now -- the caller must stop
      writing chunks and tear the stream down (abort, don't drain). Two reasons
      break playback: a control-channel **stop**, or a pending **transport
      request** (skip_back, VM-1685). The caller disambiguates by peeking
      ``ControlState.pending_transport`` after the break: a stop ends the turn, a
      transport request hands off to the skip-back replay loop. The request is
      left pending here (peek only) so converse consumes it with
      ``take_transport_request``.
    * On **pause**, holds here until the channel is resumed, stopped, or a
      transport request arrives, yielding to the event loop via ``asyncio.sleep``
      so we neither busy-spin the CPU nor block other coroutines. Returns
      ``True`` if the pause ended in a stop or a transport press (so "pause, then
      skip_back" breaks the hold and replays).
    * Returns ``False`` to continue normal playback.

    Inert until something drives the control state (the socket listener, wired
    in by later features): the singleton starts ``running`` with no pending
    transport, so this is a no-op on the default path.
    """
    control_state = get_control_state()
    snap = control_state.snapshot()
    # VM-1739: skip_forward aborts playback exactly like stop (same instant-cut).
    # The divergence (advance to record vs. control marker) lives in converse.
    if snap.is_stopped or snap.is_skip_forward:
        return True
    # VM-1685: a pending skip_back breaks playback so converse can abort the
    # in-flight utterance and replay cached audio. Left pending (peek) -- converse
    # reads-and-clears it via take_transport_request.
    if snap.pending_transport:
        return True
    if snap.is_paused:
        logger.info("TTS playback paused via control channel")
        # F4 (VM-1697): bound the pause. Holding here keeps the global audio lock,
        # so a pause that is never resumed would wedge every later converse. After
        # CONTROL_PAUSE_TIMEOUT seconds we self-heal: stop (clean return) or resume.
        timeout = getattr(config, "CONTROL_PAUSE_TIMEOUT", 300.0) or 0.0
        waited = 0.0
        while True:
            await asyncio.sleep(CONTROL_POLL_INTERVAL)
            snap = control_state.snapshot()
            # VM-1739: a skip_forward arriving during a pause-hold also aborts.
            if snap.is_stopped or snap.is_skip_forward:
                return True
            # VM-1685: "pause, then skip_back" -- a transport press while paused
            # breaks the hold so converse can replay the cached audio. Left
            # pending for converse to consume.
            if snap.pending_transport:
                logger.info("transport request received while paused -- breaking to replay")
                return True
            if not snap.is_paused:
                logger.info("TTS playback resumed via control channel")
                return False
            waited += CONTROL_POLL_INTERVAL
            if timeout and waited >= timeout:
                action = getattr(config, "CONTROL_PAUSE_TIMEOUT_ACTION", "stop")
                logger.warning(
                    "control-channel pause exceeded %.0fs with no resume; auto-%s",
                    timeout, action,
                )
                if action == "resume":
                    control_state.request_resume()
                    return False
                control_state.request_stop(hint="pause-timeout")
                return True
    return False


def _float_samples_to_pcm16(samples: np.ndarray) -> bytes:
    """Convert normalized float32 samples ([-1, 1)) back to 16-bit PCM bytes.

    The buffered (non-PCM) playback path decodes to float32 normalized by
    ``/ 32768.0``; the history buffer stores raw 16-bit PCM, so reverse that
    here, clipping to the int16 range to be safe.
    """
    scaled = np.clip(np.round(samples * 32768.0), -32768, 32767)
    return scaled.astype(np.int16).tobytes()


def _capture_utterance(
    text: str,
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int = 1,
    voice: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> None:
    """Append a rendered utterance to the process-wide history buffer (VM-1685).

    Called by each TTS playback loop after it finishes streaming an utterance,
    so skip-back can later re-play the cached audio. ``pcm_bytes`` is raw 16-bit
    PCM at ``sample_rate`` -- exactly what these loops already write to the
    output stream.

    Captures **regardless of SAVE_AUDIO**: the playback loops accumulate the PCM
    for this buffer whether or not the audio is also being saved to disk. Empty
    audio (nothing reached the device) is skipped. Capture must never break
    playback, so any failure here is logged and swallowed.
    """
    if not pcm_bytes:
        return
    try:
        get_history_buffer().append(
            text=text,
            pcm_bytes=pcm_bytes,
            sample_rate=sample_rate,
            channels=channels,
            voice=voice,
            conversation_id=conversation_id,
        )
    except Exception:
        logger.debug("Failed to capture utterance into history buffer", exc_info=True)


def _abort_stream(stream) -> None:
    """Tear down an output stream immediately on a control-channel stop.

    Prefers ``abort()`` (PortAudio ``Pa_AbortStream`` -- discards buffered audio
    for an instant cut) over ``stop()`` (which drains). Falls back to ``stop()``
    if ``abort`` is unavailable, and never raises -- teardown must not mask the
    stop.
    """
    try:
        stream.abort()
    except Exception:
        try:
            stream.stop()
        except Exception:
            logger.debug("Failed to abort/stop stream on control stop", exc_info=True)


# Terminal reasons a replay (play_cached_utterance) can end with.
REPLAY_COMPLETED = "completed"   # played to the end
REPLAY_STOPPED = "stopped"       # cut by a control-channel stop
REPLAY_TRANSPORT = "transport"   # cut by a further transport press (step back again)


async def play_cached_utterance(record, control_state=None) -> str:
    """Replay a cached utterance's PCM through the normal playback path (VM-1685).

    This is how skip-back re-plays already-spoken audio: ``record`` is an
    :class:`~voice_mode.history_buffer.UtteranceRecord` holding raw 16-bit PCM
    (exactly what the streaming loops write to the device), so we feed it
    straight to an ``sd.OutputStream`` with no decode step.

    It honours the control channel between chunks via :func:`_poll_control_channel`,
    so a replay **composes with pause** (hold / resume), can be **cut by a stop**,
    and can be **stepped past by a further skip_back** (a new transport press).
    The terminal reason is returned as one of ``REPLAY_COMPLETED`` /
    ``REPLAY_STOPPED`` / ``REPLAY_TRANSPORT``.

    Replay is a **playback-layer** operation only: it never captures into the
    history buffer (this is a re-play, not a new render) and never invokes STT or
    the model -- so skip-back can never start a new agent turn.
    """
    pcm = record.pcm_bytes
    if not pcm:
        return REPLAY_COMPLETED

    state = control_state or get_control_state()
    channels = max(record.channels, 1)
    # int16 = 2 bytes/sample; keep chunk boundaries frame-aligned so np.frombuffer
    # always sees whole samples.
    frame_bytes = 2 * channels
    chunk_bytes = max(frame_bytes, (STREAM_CHUNK_SIZE // frame_bytes) * frame_bytes)

    stream = None
    try:
        stream = sd.OutputStream(
            samplerate=record.sample_rate,
            channels=channels,
            dtype="int16",
        )
        stream.start()

        event_logger = get_event_logger()
        if event_logger:
            event_logger.log_event(event_logger.TTS_PLAYBACK_START)

        for offset in range(0, len(pcm), chunk_bytes):
            # Honour pause / resume / stop / skip_back before each chunk, exactly
            # like the live streaming loops.
            if await _poll_control_channel():
                reason = (
                    REPLAY_STOPPED
                    if state.snapshot().is_stopped
                    else REPLAY_TRANSPORT
                )
                logger.info("skip-back replay interrupted (%s)", reason)
                _abort_stream(stream)
                return reason

            chunk = pcm[offset:offset + chunk_bytes]
            audio_array = np.frombuffer(chunk, dtype=np.int16)
            stream.write(audio_array)

        # Played to the end -- drain naturally.
        stream.stop()
        return REPLAY_COMPLETED

    except Exception:
        logger.error("Failed to replay cached utterance", exc_info=True)
        return REPLAY_COMPLETED
    finally:
        if stream:
            try:
                stream.close()
            except Exception:
                logger.debug("Failed to close replay stream", exc_info=True)


async def _hold_and_play_remainder(stream, remainder_chunks, control_state) -> str:
    """Resume a paused utterance from its drained-to-buffer remainder (VM-1685).

    impl-drain-restart decouples receiving from playing: when a **pause** arrives
    mid-stream, the receive loop stops feeding the device but keeps draining the
    rest of the utterance into the capture buffer (freeing the provider). This
    plays that buffered remainder back through the **same** still-open output
    stream once the channel resumes -- so resume plays local audio instead of
    re-pulling the provider.

    Holds while paused via :func:`_poll_control_channel` (same hold/timeout
    semantics as live playback), then writes the un-played 16-bit PCM chunks back
    verbatim (same granularity the live loop used), honouring the control channel
    between chunks. Returns one of ``REPLAY_COMPLETED`` / ``REPLAY_STOPPED`` /
    ``REPLAY_TRANSPORT`` -- a stop ends the turn, a further skip_back hands off to
    the replay loop (which restarts the now fully-captured current utterance).
    """
    # Even with nothing left to play (pause landed on the final chunk), honour the
    # hold so a resume/stop/skip_back still resolves cleanly.
    if not remainder_chunks:
        if await _poll_control_channel():
            return REPLAY_STOPPED if control_state.snapshot().is_stopped else REPLAY_TRANSPORT
        return REPLAY_COMPLETED

    for chunk in remainder_chunks:
        # First iteration holds until resume; later iterations honour a re-pause /
        # stop / a further skip_back exactly like the live loop.
        if await _poll_control_channel():
            reason = (
                REPLAY_STOPPED
                if control_state.snapshot().is_stopped
                else REPLAY_TRANSPORT
            )
            logger.info("paused-utterance remainder interrupted (%s)", reason)
            return reason
        stream.write(np.frombuffer(chunk, dtype=np.int16))
    return REPLAY_COMPLETED


def _pydub_format(fmt: str) -> str:
    """Map TTS response_format to the container format pydub/ffmpeg expects.

    Opus is always wrapped in an Ogg (or WebM) container -- ffmpeg has no
    raw 'opus' demuxer. TTS providers (Kokoro, OpenAI) return Ogg/Opus when
    response_format='opus', so we tell pydub format='ogg' for decoding.
    """
    return "ogg" if fmt == "opus" else fmt


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
    # VM-1676: True when playback was cut short by a control-channel stop
    # (vs. finishing naturally or erroring). Lets converse return normally with
    # a control hint instead of treating the short utterance as a full one.
    control_stopped: bool = False
    # VM-1685: True when playback was cut short by a transport request
    # (skip_back) rather than a stop. The in-flight utterance is aborted (and
    # deliberately NOT captured, like a stop) so converse can hand control to the
    # skip-back replay loop. Distinct from control_stopped: a transport interrupt
    # does not end the turn, it triggers a replay.
    transport_interrupted: bool = False


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
    # VM-1685: always accumulate the rendered PCM so it can feed the history
    # buffer even when SAVE_AUDIO is off. The on-disk save below reads from the
    # same buffer when saving is enabled.
    audio_buffer = io.BytesIO()
    control_stopped = False
    transport_interrupted = False
    # VM-1685 (impl-drain-restart): when an interrupt we can recover from arrives
    # mid-stream -- a skip_back ("transport") or a "pause" -- we stop playing but
    # keep draining the rest of the utterance into audio_buffer so the FULL
    # utterance is captured. drain_reason records which; remainder_chunks collects
    # the un-played chunks so a paused stream can resume from the buffer.
    drain_reason = None
    remainder_chunks = []
    captured = False

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

        aborted = False

        def _abort_once():
            # Tear the device down exactly once regardless of how many control
            # branches fire (keeps the mock-asserted single abort honest).
            nonlocal aborted
            if not aborted:
                _abort_stream(stream)
                aborted = True
        
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
            
            playing = True

            # Stream chunks as they arrive
            async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
                if not chunk:
                    continue
                if playing:
                    # VM-1676/VM-1739: a stop or skip_forward cuts immediately --
                    # abort the device and discard the rest of the stream.
                    # VM-1685 (impl-drain-restart): a skip_back or a pause instead
                    # STOPS PLAYING but keeps DRAINING the stream into the capture
                    # buffer, so the full utterance is captured (skip_back can then
                    # restart the CURRENT utterance; pause resumes from the buffer).
                    snap = get_control_state().snapshot()
                    if snap.is_stopped:
                        control_stopped = True
                        _abort_once()
                        break
                    if snap.is_skip_forward:
                        transport_interrupted = True
                        _abort_once()
                        break
                    if snap.pending_transport:
                        # skip_back: barge-in now (silence the device), then keep
                        # draining the remainder so converse replays the full
                        # current utterance from its start.
                        transport_interrupted = True
                        drain_reason = "transport"
                        playing = False
                        _abort_once()
                    elif snap.is_paused:
                        # pause: stop feeding the device (it drains what's buffered
                        # and goes quiet) but keep pulling the rest into the buffer
                        # to free the provider; resume plays the remainder.
                        drain_reason = "pause"
                        playing = False

                # Track first chunk received (TTFA is receipt-based, independent of
                # whether playback is currently suppressed).
                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter()
                    chunk_receive_time = first_chunk_time - start_time
                    logger.info(f"First audio chunk received after {chunk_receive_time:.3f}s")

                    # Log TTS first audio event
                    event_logger = get_event_logger()
                    if event_logger:
                        event_logger.log_event(event_logger.TTS_FIRST_AUDIO)

                # Accumulate for the history buffer (and on-disk save) REGARDLESS of
                # playback suppression -- this is what makes the full utterance
                # available for skip-back replay / a pause resume.
                audio_buffer.write(chunk)

                # Play the chunk immediately, unless an interrupt suppressed playback.
                if playing:
                    audio_array = np.frombuffer(chunk, dtype=np.int16)
                    stream.write(audio_array)
                    metrics.chunks_played = chunk_count + 1
                else:
                    # Suppressed by a pause: keep the un-played chunk to replay
                    # verbatim from the buffer on resume (skip_back discards this).
                    remainder_chunks.append(chunk)

                chunk_count += 1
                bytes_received += len(chunk)
                metrics.chunks_received = chunk_count

                if debug and chunk_count % 10 == 0:
                    logger.debug(f"Streamed {chunk_count} chunks, {bytes_received} bytes")

        # VM-1676/VM-1739: stop / skip_forward broke out of the loop having already
        # aborted the device -- discard (do NOT capture) and return with the
        # appropriate metric so converse handles it. control_stopped ends the turn;
        # a skip_forward (transport_interrupted with no drain) advances to record.
        if control_stopped:
            logger.info("TTS playback stopped via control channel")
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.control_stopped = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"control_stopped": True, "chunks": chunk_count}
                })
            return True, metrics

        if transport_interrupted and drain_reason is None:
            logger.info("TTS playback interrupted by skip_forward (advancing to record)")
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.transport_interrupted = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"transport_interrupted": True, "chunks": chunk_count}
                })
            return True, metrics

        # From here the stream drained to completion: a natural finish, or a
        # recoverable interrupt (skip_back / pause) whose remainder we drained into
        # audio_buffer. The FULL utterance is captured for replay regardless.
        full_pcm = audio_buffer.getvalue()

        if drain_reason == "pause":
            # Capture the complete utterance now, then hold for resume and play the
            # buffered remainder through the same still-open stream.
            _capture_utterance(
                text=text,
                pcm_bytes=full_pcm,
                sample_rate=SAMPLE_RATE,
                channels=1,
                voice=request_params.get("voice"),
                conversation_id=conversation_id,
            )
            captured = True
            outcome = await _hold_and_play_remainder(
                stream, remainder_chunks, get_control_state()
            )
            if outcome == REPLAY_STOPPED:
                control_stopped = True
            elif outcome == REPLAY_TRANSPORT:
                transport_interrupted = True
                drain_reason = "transport"
            # REPLAY_COMPLETED -> fall through to the normal finish below.

        if control_stopped:
            logger.info("TTS playback stopped via control channel (after pause-drain)")
            _abort_once()
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.control_stopped = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"control_stopped": True, "chunks": chunk_count}
                })
            return True, metrics

        if drain_reason == "transport":
            # skip_back: the device is already silenced; the full utterance is
            # captured. Hand off to converse's replay loop (restart current).
            logger.info("TTS playback interrupted by transport request (skip_back) -- full utterance captured")
            _abort_once()
            if not captured:
                _capture_utterance(
                    text=text,
                    pcm_bytes=full_pcm,
                    sample_rate=SAMPLE_RATE,
                    channels=1,
                    voice=request_params.get("voice"),
                    conversation_id=conversation_id,
                )
                captured = True
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.transport_interrupted = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"transport_interrupted": True, "chunks": chunk_count}
                })
            return True, metrics

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

        # VM-1685: capture the rendered utterance for skip-back replay. Raw PCM
        # is already in audio_buffer; this runs regardless of SAVE_AUDIO. Skipped
        # if a pause-drain already captured the full utterance above.
        if not captured:
            _capture_utterance(
                text=text,
                pcm_bytes=full_pcm,
                sample_rate=SAMPLE_RATE,
                channels=1,
                voice=request_params.get("voice"),
                conversation_id=conversation_id,
            )

        # Save audio if enabled
        if save_audio and audio_dir:
            try:
                from .core import save_debug_file
                audio_buffer.seek(0)
                audio_data = audio_buffer.read()
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
                            # Update latest symlinks for quick access to most recent TTS audio
                            update_latest_symlinks(audio_path, "tts")
            except Exception as e:
                logger.error(f"Failed to save TTS audio: {e}")
        
        return True, metrics
        
    except Exception as e:
        logger.error(f"PCM streaming failed: {e}")
        return False, metrics
        
    finally:
        if stream:
            stream.close()


async def stream_cartesia_pcm(
    text: str,
    voice_id: Optional[str],
    speed: Optional[float] = None,
    sample_rate: int = SAMPLE_RATE,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[bool, StreamMetrics]:
    """Stream raw PCM int16 from Cartesia SSE and play chunks as they arrive."""
    from . import cartesia_tts

    metrics = StreamMetrics()
    start_time = time.perf_counter()
    stream = None
    first_chunk_time = None
    # VM-1685: always accumulate the rendered PCM for the history buffer (used
    # whether or not SAVE_AUDIO is on); the on-disk save reads from it too.
    audio_buffer = io.BytesIO()
    bytes_received = 0
    chunk_count = 0
    control_stopped = False
    transport_interrupted = False
    # VM-1685 (impl-drain-restart): drain-on-interrupt state (see stream_pcm_audio).
    drain_reason = None
    remainder_chunks = []
    captured = False
    event_logger = get_event_logger()

    try:
        stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
        stream.start()

        aborted = False

        def _abort_once():
            nonlocal aborted
            if not aborted:
                _abort_stream(stream)
                aborted = True

        if event_logger:
            event_logger.log_event(event_logger.TTS_PLAYBACK_START)

        logger.info("Starting Cartesia SSE streaming")

        playing = True
        async for chunk in cartesia_tts.stream(
            text=text,
            voice_id=voice_id,
            sample_rate=sample_rate,
            speed=speed,
        ):
            if not chunk:
                continue
            if playing:
                # VM-1676/VM-1739: stop / skip_forward cut immediately + discard.
                # VM-1685: skip_back / pause stop playing but keep DRAINING into the
                # buffer so the full utterance is captured (see stream_pcm_audio).
                snap = get_control_state().snapshot()
                if snap.is_stopped:
                    control_stopped = True
                    _abort_once()
                    break
                if snap.is_skip_forward:
                    transport_interrupted = True
                    _abort_once()
                    break
                if snap.pending_transport:
                    transport_interrupted = True
                    drain_reason = "transport"
                    playing = False
                    _abort_once()
                elif snap.is_paused:
                    drain_reason = "pause"
                    playing = False

            if first_chunk_time is None:
                first_chunk_time = time.perf_counter()
                logger.info(
                    f"Cartesia first audio chunk after {first_chunk_time - start_time:.3f}s"
                )
                if event_logger:
                    event_logger.log_event(event_logger.TTS_FIRST_AUDIO)

            audio_buffer.write(chunk)
            if playing:
                audio_array = np.frombuffer(chunk, dtype=np.int16)
                stream.write(audio_array)
            else:
                remainder_chunks.append(chunk)

            chunk_count += 1
            bytes_received += len(chunk)

        # VM-1676/VM-1739: stop / skip_forward already aborted + discard.
        if control_stopped:
            logger.info("Cartesia TTS playback stopped via control channel")
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0.0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.control_stopped = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"control_stopped": True, "chunks": chunk_count, "provider": "cartesia"}
                })
            return True, metrics

        if transport_interrupted and drain_reason is None:
            logger.info("Cartesia TTS playback interrupted by skip_forward (advancing to record)")
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0.0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.transport_interrupted = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"transport_interrupted": True, "chunks": chunk_count, "provider": "cartesia"}
                })
            return True, metrics

        # Stream drained to completion (natural or a recoverable skip_back / pause).
        full_pcm = audio_buffer.getvalue()

        if drain_reason == "pause":
            _capture_utterance(
                text=text,
                pcm_bytes=full_pcm,
                sample_rate=sample_rate,
                channels=1,
                voice=voice_id,
                conversation_id=conversation_id,
            )
            captured = True
            outcome = await _hold_and_play_remainder(
                stream, remainder_chunks, get_control_state()
            )
            if outcome == REPLAY_STOPPED:
                control_stopped = True
            elif outcome == REPLAY_TRANSPORT:
                transport_interrupted = True
                drain_reason = "transport"

        if control_stopped:
            logger.info("Cartesia TTS playback stopped via control channel (after pause-drain)")
            _abort_once()
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0.0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.control_stopped = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"control_stopped": True, "chunks": chunk_count, "provider": "cartesia"}
                })
            return True, metrics

        if drain_reason == "transport":
            logger.info("Cartesia TTS interrupted by transport request (skip_back) -- full utterance captured")
            _abort_once()
            if not captured:
                _capture_utterance(
                    text=text,
                    pcm_bytes=full_pcm,
                    sample_rate=sample_rate,
                    channels=1,
                    voice=voice_id,
                    conversation_id=conversation_id,
                )
                captured = True
            metrics.chunks_received = chunk_count
            metrics.chunks_played = chunk_count
            metrics.generation_time = (first_chunk_time - start_time) if first_chunk_time else 0.0
            metrics.playback_time = time.perf_counter() - start_time
            metrics.ttfa = metrics.generation_time
            metrics.transport_interrupted = True
            if event_logger:
                event_logger.log_event(event_logger.TTS_PLAYBACK_END, {
                    "metrics": {"transport_interrupted": True, "chunks": chunk_count, "provider": "cartesia"}
                })
            return True, metrics

        stream.stop()
        end_time = time.perf_counter()

        metrics.chunks_received = chunk_count
        metrics.chunks_played = chunk_count
        metrics.generation_time = (
            (first_chunk_time - start_time) if first_chunk_time else 0.0
        )
        metrics.playback_time = end_time - start_time
        metrics.ttfa = metrics.generation_time

        if event_logger:
            event_logger.log_event(
                event_logger.TTS_PLAYBACK_END,
                {
                    "metrics": {
                        "ttfa_ms": round(metrics.ttfa * 1000, 1),
                        "total_time_ms": round(metrics.playback_time * 1000, 1),
                        "bytes_received": bytes_received,
                        "chunks": chunk_count,
                        "format": "pcm",
                        "sample_rate_hz": sample_rate,
                        "provider": "cartesia",
                    }
                },
            )

        logger.info(
            f"Cartesia streaming complete - TTFA: {metrics.ttfa:.3f}s, "
            f"Total: {metrics.playback_time:.3f}s, Chunks: {chunk_count}"
        )

        # VM-1685: capture the rendered utterance for skip-back replay (raw PCM
        # already accumulated above), regardless of SAVE_AUDIO. Skipped if a
        # pause-drain already captured the full utterance.
        if not captured:
            _capture_utterance(
                text=text,
                pcm_bytes=full_pcm,
                sample_rate=sample_rate,
                channels=1,
                voice=voice_id,
                conversation_id=conversation_id,
            )

        if save_audio and audio_dir and bytes_received > 0:
            try:
                from .core import save_debug_file
                import wave
                import tempfile
                import os

                audio_buffer.seek(0)
                pcm_data = audio_buffer.read()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                    with wave.open(tmp_wav.name, "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(pcm_data)
                    with open(tmp_wav.name, "rb") as f:
                        wav_data = f.read()
                    os.unlink(tmp_wav.name)
                audio_path = save_debug_file(
                    wav_data, "tts", "wav", audio_dir, True, conversation_id
                )
                if audio_path:
                    metrics.audio_path = audio_path
                    update_latest_symlinks(audio_path, "tts")
            except Exception as e:
                logger.error(f"Failed to save Cartesia TTS audio: {e}")

        return True, metrics

    except Exception as e:
        logger.error(f"Cartesia streaming failed: {e}")
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
    # Separate buffer for saving complete audio (encoded bytes, e.g. opus/mp3)
    save_buffer = io.BytesIO() if save_audio else None
    # VM-1685: accumulate the DECODED PCM for the history buffer. save_buffer
    # holds the encoded container, which can't feed the PCM-based replay buffer,
    # so we collect int16 PCM at each playback write instead. Independent of
    # SAVE_AUDIO.
    pcm_parts: list = []
    audio_started = False
    stream = None
    control_stopped = False
    transport_interrupted = False
    # VM-1685 (impl-drain-restart): on skip_back this fallback keeps draining +
    # decoding the rest of the response so the FULL utterance is captured (so a
    # mid-playback skip_back restarts the CURRENT utterance). It does NOT play the
    # remainder (barge-in). Pause keeps the existing hold-in-loop behaviour here:
    # this path buffers-then-plays (opus decodes once at the end), so there is no
    # well-defined "remainder" to resume into and no provider backpressure to free.
    drain_reason = None

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
            
            playing = True

            # Stream chunks as they arrive
            async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
                if chunk:
                    if playing:
                        # VM-1676: honour an external pause/resume/stop before
                        # buffering/playing each chunk (pause holds in the poll).
                        if await _poll_control_channel():
                            # VM-1676/VM-1739: a stop or skip_forward cuts + discards.
                            snap = get_control_state().snapshot()
                            if snap.is_stopped:
                                control_stopped = True
                                break
                            if snap.is_skip_forward:
                                transport_interrupted = True
                                break
                            # VM-1685: skip_back -- stop playing but keep draining +
                            # decoding the rest so the full utterance is captured.
                            transport_interrupted = True
                            drain_reason = "transport"
                            playing = False
                            _abort_stream(stream)

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

                    # Try to decode when we have enough data (e.g., 32KB).
                    # Skip for Opus/Ogg: the container has codec-setup pages only at the
                    # start, so resetting the buffer after a partial decode leaves the
                    # remaining bytes unparseable. For Opus we buffer the full response
                    # and decode once below (matches the docstring's stated intent).
                    if (playing
                            and buffer.tell() > 32768
                            and not audio_started
                            and format != "opus"):
                        buffer.seek(0)
                        try:
                            # Attempt to decode what we have
                            audio = AudioSegment.from_file(buffer, format=_pydub_format(format))
                            # Normalize decoded audio to match the playback stream:
                            #   - frame rate: Opus always decodes to 48kHz; the stream is
                            #     opened at sample_rate (24kHz default). Without resampling,
                            #     audio plays at 2x speed and sounds chipmunk-like.
                            #   - sample width: Opus decodes to 32-bit, but the / 32768.0
                            #     normalization assumes 16-bit, producing ~12,000x amplitude
                            #     and instant clipping. Force 16-bit to match.
                            if audio.frame_rate != sample_rate:
                                audio = audio.set_frame_rate(sample_rate)
                            if audio.sample_width != 2:
                                audio = audio.set_sample_width(2)
                            samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0

                            # Start playback
                            metrics.ttfa = time.perf_counter() - start_time
                            audio_started = True
                            logger.info(f"Buffered streaming started - TTFA: {metrics.ttfa:.3f}s")

                            # Play audio
                            stream.write(samples)
                            metrics.chunks_played += len(samples) // 1024
                            pcm_parts.append(_float_samples_to_pcm16(samples))

                            # Reset buffer for next batch
                            buffer = io.BytesIO()

                        except Exception as e:
                            # Not enough valid data yet
                            buffer.seek(0, io.SEEK_END)

        # VM-1676/VM-1739: a stop / skip_forward broke out -- discard, no capture.
        # (A skip_back instead sets drain_reason and falls through to decode +
        # capture the full utterance below, then return as a transport interrupt.)
        if transport_interrupted and drain_reason is None:
            logger.info("Buffered TTS playback interrupted by skip_forward (advancing to record)")
            metrics.transport_interrupted = True
            metrics.generation_time = time.perf_counter() - start_time
            metrics.playback_time = metrics.generation_time
            return True, metrics

        if control_stopped:
            logger.info("Buffered TTS playback stopped via control channel")
            metrics.control_stopped = True
            metrics.generation_time = time.perf_counter() - start_time
            metrics.playback_time = metrics.generation_time
            return True, metrics

        # Decode any remaining buffered data. On a skip_back drain we decode (to
        # capture the FULL utterance) but do NOT play it (the device is already
        # silenced -- barge-in); otherwise this is the normal final decode + play.
        play_final = drain_reason != "transport"
        if buffer.tell() > 0:
            buffer.seek(0)
            try:
                audio = AudioSegment.from_file(buffer, format=_pydub_format(format))
                # Normalize decoded audio to match the playback stream. Opus always
                # decodes to 48kHz / 32-bit, but the stream is opened at sample_rate
                # (24kHz default) and the / 32768.0 line below assumes 16-bit. Without
                # both conversions, audio is at 2x speed and ~12,000x amplitude
                # (chipmunk-like and clipped to silence-by-distortion).
                if audio.frame_rate != sample_rate:
                    audio = audio.set_frame_rate(sample_rate)
                if audio.sample_width != 2:
                    audio = audio.set_sample_width(2)
                samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0

                # Append trailing silence to guarantee the real content plays out
                # before the stream is stopped. On macOS CoreAudio (and especially
                # with aggregate devices), `stream.stop()` does not always wait for
                # the host buffer to drain, and PortAudio's `stream.latency`
                # underestimates the true end-to-end latency, so the time-based
                # drain sleep below isn't always sufficient. Padding the samples
                # with silence makes the fix robust regardless of how the device
                # chain buffers — even if the tail is truncated, only silence
                # is lost.
                if play_final and TTS_TRAILING_SILENCE > 0:
                    pad = np.zeros(int(sample_rate * TTS_TRAILING_SILENCE), dtype=np.float32)
                    samples = np.concatenate([samples, pad])

                if not audio_started:
                    metrics.ttfa = time.perf_counter() - start_time

                if play_final:
                    stream.write(samples)
                    metrics.chunks_played += len(samples) // 1024
                pcm_parts.append(_float_samples_to_pcm16(samples))

                if play_final:
                    # Belt-and-braces drain in addition to the silence padding above.
                    # Sleep for the reported output latency plus a small safety margin
                    # so that even if a future change removes the silence pad, the
                    # tail still plays through on systems where stream.stop() drains
                    # correctly.
                    drain_secs = (stream.latency or 0.0) + 0.3
                    await asyncio.sleep(drain_secs)

            except Exception as e:
                logger.error(f"Failed to decode final buffer: {e}")

        metrics.generation_time = time.perf_counter() - start_time
        metrics.playback_time = metrics.generation_time  # Approximate

        # VM-1685: capture the rendered utterance (decoded PCM) for skip-back
        # replay, regardless of SAVE_AUDIO. On a skip_back drain this is the full
        # utterance, so converse replays the CURRENT one from its start.
        _capture_utterance(
            text=text,
            pcm_bytes=b"".join(pcm_parts),
            sample_rate=sample_rate,
            channels=1,
            voice=request_params.get("voice"),
            conversation_id=conversation_id,
        )

        # VM-1685: skip_back drain captured the full utterance -- hand off to the
        # replay loop (restart current) instead of finishing normally.
        if drain_reason == "transport":
            logger.info("Buffered TTS interrupted by transport request (skip_back) -- full utterance captured")
            metrics.transport_interrupted = True
            return True, metrics

        # Save audio if enabled
        if save_audio and save_buffer and audio_dir:
            try:
                from .core import save_debug_file
                save_buffer.seek(0)
                audio_data = save_buffer.read()
                audio_path = save_debug_file(audio_data, "tts", format, audio_dir, True, conversation_id)
                if audio_path:
                    logger.info(f"TTS audio saved to: {audio_path}")
                    # Update latest symlinks for quick access to most recent TTS audio
                    update_latest_symlinks(audio_path, "tts")
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