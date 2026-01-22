"""
VoiceMode HTTP Bridge - HTTP server for remote voice interactions.

This module provides an HTTP bridge enabling voice conversations with Claude Code
from remote devices (like Pixel Watch) that don't have local microphone access.

Architecture:
- Runs on beelink (192.168.10.10:8890)
- Watch sends audio via HTTP POST
- Bridge converts via Whisper (STT) and Kokoro/OpenAI (TTS)
- Audio flows directly between watch and bridge

Endpoints:
- GET  /health               → Health check
- POST /session/start        → Create a new session
- GET  /session/{id}/status  → Get session status
- POST /audio/transcribe     → Upload audio, get transcription
- POST /audio/synthesize     → Send text, get audio response
- POST /converse             → Full conversation loop (STT → mock response → TTS)

Run with:
    uv run python -m voice_mode.http_bridge --port 8890

Or via systemd:
    sudo systemctl start voicemode-bridge
"""

import argparse
import asyncio
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web
import numpy as np
from pydub import AudioSegment

from .config import (
    OPENAI_API_KEY,
    STT_BASE_URLS,
    TTS_BASE_URLS,
    TTS_VOICES,
    setup_logging,
)
from .simple_failover import simple_stt_failover, simple_tts_failover

# Initialize logging
logger = logging.getLogger("voicemode.http_bridge")

# Version
VERSION = "0.1.0"

# Mock mode - set via environment or command line
MOCK_MODE = os.getenv("VOICEMODE_MOCK", "false").lower() == "true"


@dataclass
class Session:
    """Represents an active voice session."""
    id: str
    created_at: datetime
    last_activity: datetime
    status: str = "ready"  # ready, listening, processing, speaking, closed
    transcription_count: int = 0
    synthesis_count: int = 0
    metadata: dict = field(default_factory=dict)


class SessionManager:
    """Manages active voice sessions."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._session_timeout = 1800  # 30 minutes

    def create_session(self, metadata: Optional[dict] = None) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        session = Session(
            id=session_id,
            created_at=now,
            last_activity=now,
            metadata=metadata or {}
        )
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        session = self.sessions.get(session_id)
        if session:
            session.last_activity = datetime.now()
        return session

    def update_session(self, session_id: str, **kwargs) -> Optional[Session]:
        """Update session fields."""
        session = self.sessions.get(session_id)
        if session:
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.last_activity = datetime.now()
        return session

    def close_session(self, session_id: str) -> bool:
        """Close and remove a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Closed session: {session_id}")
            return True
        return False

    def cleanup_stale_sessions(self):
        """Remove sessions that have timed out."""
        now = datetime.now()
        stale = [
            sid for sid, s in self.sessions.items()
            if (now - s.last_activity).total_seconds() > self._session_timeout
        ]
        for sid in stale:
            self.close_session(sid)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale sessions")


# Global session manager
session_manager = SessionManager()


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    providers = {
        "tts": TTS_BASE_URLS,
        "stt": STT_BASE_URLS,
    }

    return web.json_response({
        "status": "ok",
        "version": VERSION,
        "mock_mode": MOCK_MODE,
        "timestamp": datetime.now().isoformat(),
        "providers": providers,
        "active_sessions": len(session_manager.sessions),
    })


async def handle_session_start(request: web.Request) -> web.Response:
    """Create a new voice session."""
    try:
        # Parse optional metadata from request body
        metadata = {}
        if request.content_type == "application/json":
            try:
                body = await request.json()
                metadata = body.get("metadata", {})
            except json.JSONDecodeError:
                pass

        session = session_manager.create_session(metadata)

        return web.json_response({
            "session_id": session.id,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
        })
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def handle_session_status(request: web.Request) -> web.Response:
    """Get session status."""
    session_id = request.match_info["session_id"]
    session = session_manager.get_session(session_id)

    if not session:
        return web.json_response(
            {"error": "Session not found"},
            status=404
        )

    return web.json_response({
        "session_id": session.id,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat(),
        "transcription_count": session.transcription_count,
        "synthesis_count": session.synthesis_count,
    })


async def handle_session_close(request: web.Request) -> web.Response:
    """Close a session."""
    session_id = request.match_info["session_id"]

    if session_manager.close_session(session_id):
        return web.json_response({"status": "closed"})
    else:
        return web.json_response(
            {"error": "Session not found"},
            status=404
        )


async def handle_transcribe(request: web.Request) -> web.Response:
    """
    Transcribe audio to text.

    Accepts: multipart/form-data with:
      - file: Audio file (OGG, WAV, MP3, etc.)
      - session_id: Optional session ID

    Returns: JSON with transcription result
    """
    start_time = time.perf_counter()

    try:
        # Parse multipart data
        reader = await request.multipart()
        audio_data = None
        session_id = None
        audio_format = None

        async for field in reader:
            if field.name == "file":
                audio_data = await field.read()
                # Try to determine format from content-type or filename
                content_type = field.content_type or ""
                filename = field.filename or ""

                if "ogg" in content_type or filename.endswith(".ogg"):
                    audio_format = "ogg"
                elif "wav" in content_type or filename.endswith(".wav"):
                    audio_format = "wav"
                elif "mp3" in content_type or "mpeg" in content_type or filename.endswith(".mp3"):
                    audio_format = "mp3"
                elif "opus" in content_type or filename.endswith(".opus"):
                    audio_format = "opus"
                else:
                    audio_format = "ogg"  # Default for watch recordings

            elif field.name == "session_id":
                session_id = (await field.read()).decode("utf-8")

        if not audio_data:
            return web.json_response(
                {"error": "No audio file provided"},
                status=400
            )

        # Update session if provided
        if session_id:
            session = session_manager.get_session(session_id)
            if session:
                session_manager.update_session(session_id, status="processing")

        logger.info(f"Received audio for transcription: {len(audio_data)} bytes, format: {audio_format}")

        # Convert audio to format expected by STT
        try:
            # Load audio using pydub
            audio_io = io.BytesIO(audio_data)
            if audio_format == "ogg":
                audio = AudioSegment.from_ogg(audio_io)
            elif audio_format == "opus":
                audio = AudioSegment.from_file(audio_io, format="opus")
            elif audio_format == "mp3":
                audio = AudioSegment.from_mp3(audio_io)
            elif audio_format == "wav":
                audio = AudioSegment.from_wav(audio_io)
            else:
                audio = AudioSegment.from_file(audio_io, format=audio_format)

            # Convert to mono 16kHz WAV for Whisper
            audio = audio.set_channels(1).set_frame_rate(16000)

            # Export to WAV bytes
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)
            wav_io.name = "audio.wav"  # Required by OpenAI client

            duration_ms = len(audio)
            logger.info(f"Audio converted: duration={duration_ms}ms")

        except Exception as e:
            logger.error(f"Failed to convert audio: {e}")
            return web.json_response(
                {"error": f"Failed to process audio: {str(e)}"},
                status=400
            )

        # Call STT
        result = await simple_stt_failover(wav_io, model="whisper-1")

        processing_time = (time.perf_counter() - start_time) * 1000

        if result is None:
            return web.json_response(
                {"error": "STT failed - unknown error"},
                status=500
            )

        if result.get("error_type") == "no_speech":
            # Update session
            if session_id:
                session_manager.update_session(session_id, status="ready")

            return web.json_response({
                "text": "",
                "no_speech": True,
                "duration_ms": duration_ms,
                "processing_ms": round(processing_time, 1),
            })

        if result.get("error_type") == "connection_failed":
            return web.json_response(
                {"error": "All STT providers failed", "details": result.get("attempted_endpoints")},
                status=503
            )

        # Success
        if session_id:
            session = session_manager.get_session(session_id)
            if session:
                session.transcription_count += 1
                session_manager.update_session(session_id, status="ready")

        return web.json_response({
            "text": result.get("text", ""),
            "duration_ms": duration_ms,
            "processing_ms": round(processing_time, 1),
            "provider": result.get("provider"),
        })

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def handle_synthesize(request: web.Request) -> web.Response:
    """
    Synthesize text to speech.

    Accepts: JSON with:
      - text: Text to synthesize
      - voice: Optional voice name (default: af_sky)
      - session_id: Optional session ID

    Returns: audio/mpeg (MP3) stream
    """
    start_time = time.perf_counter()

    try:
        # Parse JSON body
        body = await request.json()
        text = body.get("text")
        voice = body.get("voice", TTS_VOICES[0] if TTS_VOICES else "af_sky")
        session_id = body.get("session_id")

        if not text:
            return web.json_response(
                {"error": "No text provided"},
                status=400
            )

        # Update session if provided
        if session_id:
            session = session_manager.get_session(session_id)
            if session:
                session_manager.update_session(session_id, status="speaking")

        logger.info(f"Synthesizing TTS: text='{text[:50]}...', voice={voice}")

        # Call TTS API directly without playback
        from openai import AsyncOpenAI
        from .provider_discovery import detect_provider_type, is_local_provider

        audio_data = None
        used_voice = voice
        used_provider = None

        for base_url in TTS_BASE_URLS:
            provider_type = detect_provider_type(base_url)
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            # Map voice for OpenAI if needed
            if provider_type == "openai":
                openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
                if voice not in openai_voices:
                    voice_mapping = {
                        "af_sky": "nova", "af_sarah": "nova", "af_alloy": "alloy",
                        "am_adam": "onyx", "am_echo": "echo", "am_onyx": "onyx"
                    }
                    used_voice = voice_mapping.get(voice, "alloy")
                else:
                    used_voice = voice
            else:
                used_voice = voice

            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                max_retries=max_retries
            )

            try:
                response = await client.audio.speech.create(
                    model="tts-1",
                    input=text,
                    voice=used_voice,
                    response_format="mp3"
                )
                audio_data = response.content
                used_provider = provider_type
                logger.info(f"TTS succeeded with {base_url}")
                break
            except Exception as e:
                logger.warning(f"TTS failed for {base_url}: {e}")
                continue

        processing_time = (time.perf_counter() - start_time) * 1000

        if not audio_data:
            return web.json_response(
                {"error": "All TTS providers failed"},
                status=503
            )

        mp3_data = audio_data

        # Update session
        if session_id:
            session = session_manager.get_session(session_id)
            if session:
                session.synthesis_count += 1
                session_manager.update_session(session_id, status="ready")

        logger.info(f"TTS complete: {len(mp3_data)} bytes, {processing_time:.0f}ms")

        # Return audio stream
        return web.Response(
            body=mp3_data,
            content_type="audio/mpeg",
            headers={
                "X-Processing-Time-Ms": str(round(processing_time, 1)),
                "X-Voice": used_voice,
                "X-Provider": used_provider or "unknown",
            }
        )

    except json.JSONDecodeError:
        return web.json_response(
            {"error": "Invalid JSON body"},
            status=400
        )
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def handle_converse(request: web.Request) -> web.Response:
    """
    Full conversation loop: STT → Response → TTS

    Accepts: multipart/form-data with:
      - audio: Audio file (OGG from watch)
      - session_id: Optional session ID

    Returns: JSON with transcription, response, and TTS audio URL
    """
    start_time = time.perf_counter()

    try:
        # Parse multipart data
        reader = await request.multipart()
        audio_data = None
        session_id = None

        async for field in reader:
            if field.name == "audio" or field.name == "file":
                audio_data = await field.read()
            elif field.name == "session_id":
                session_id = (await field.read()).decode("utf-8")

        if not audio_data:
            return web.json_response(
                {"error": "No audio file provided"},
                status=400
            )

        # Update session
        if session_id:
            session_manager.update_session(session_id, status="processing")

        logger.info(f"Converse request: {len(audio_data)} bytes audio")

        # Step 1: Transcribe audio
        audio_io = io.BytesIO(audio_data)
        audio = AudioSegment.from_file(audio_io, format="ogg")
        audio = audio.set_channels(1).set_frame_rate(16000)

        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        stt_result = await simple_stt_failover(wav_io, model="whisper-1")

        if not stt_result or stt_result.get("error_type"):
            error_type = stt_result.get("error_type", "unknown") if stt_result else "unknown"
            return web.json_response({
                "error": f"Transcription failed: {error_type}",
                "transcription": None,
            }, status=503)

        transcription = stt_result.get("text", "")
        logger.info(f"Transcribed: {transcription[:100]}...")

        # Step 2: Generate response
        if MOCK_MODE:
            # Mock response for testing
            response_text = f"I heard you say: {transcription}. This is a mock response for testing the voice pipeline."
        else:
            # In production, this would call Claude or another LLM
            # For now, echo back the transcription
            response_text = f"You said: {transcription}"

        logger.info(f"Response: {response_text[:100]}...")

        # Step 3: Generate TTS (direct API call without playback)
        if session_id:
            session_manager.update_session(session_id, status="speaking")

        from openai import AsyncOpenAI
        from .provider_discovery import detect_provider_type, is_local_provider
        import base64

        voice = TTS_VOICES[0] if TTS_VOICES else "af_sky"
        tts_audio_data = None
        tts_provider = None
        used_voice = voice

        for base_url in TTS_BASE_URLS:
            provider_type = detect_provider_type(base_url)
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            # Map voice for OpenAI if needed
            if provider_type == "openai":
                openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
                if voice not in openai_voices:
                    voice_mapping = {
                        "af_sky": "nova", "af_sarah": "nova", "af_alloy": "alloy",
                        "am_adam": "onyx", "am_echo": "echo", "am_onyx": "onyx"
                    }
                    used_voice = voice_mapping.get(voice, "alloy")
                else:
                    used_voice = voice
            else:
                used_voice = voice

            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                max_retries=max_retries
            )

            try:
                response = await client.audio.speech.create(
                    model="tts-1",
                    input=response_text,
                    voice=used_voice,
                    response_format="mp3"
                )
                tts_audio_data = response.content
                tts_provider = provider_type
                logger.info(f"TTS succeeded with {base_url}")
                break
            except Exception as e:
                logger.warning(f"TTS failed for {base_url}: {e}")
                continue

        total_time = (time.perf_counter() - start_time) * 1000

        if not tts_audio_data:
            return web.json_response({
                "transcription": transcription,
                "response_text": response_text,
                "error": "TTS failed",
                "processing_ms": round(total_time, 1),
            }, status=503)

        # Convert to base64
        tts_audio_base64 = base64.b64encode(tts_audio_data).decode("utf-8")

        # Update session
        if session_id:
            session = session_manager.get_session(session_id)
            if session:
                session.transcription_count += 1
                session.synthesis_count += 1
            session_manager.update_session(session_id, status="ready")

        return web.json_response({
            "transcription": transcription,
            "response_text": response_text,
            "tts_audio": tts_audio_base64,
            "tts_format": "mp3",
            "mock_mode": MOCK_MODE,
            "processing_ms": round(total_time, 1),
            "stt_provider": stt_result.get("provider"),
            "tts_provider": tts_provider,
        })

    except Exception as e:
        logger.error(f"Converse error: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500
        )


# Audio storage for push notifications
# Maps audio_id -> (audio_bytes, created_at, text)
_audio_storage: dict[str, tuple[bytes, datetime, str]] = {}
_audio_cleanup_interval = 300  # 5 minutes
_audio_max_age = 600  # 10 minutes


# ============================================================================
# Ask Session Management - Claude Code voice questions via watch
# ============================================================================

@dataclass
class AskSession:
    """
    Represents an ask session where Claude Code asks a question via voice
    and waits for the user's spoken response.
    """
    id: str
    question: str
    status: str  # pending, listening, completed, timeout, error
    audio_id: str
    response_text: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    timeout_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class AskSessionManager:
    """Manages active ask sessions for Claude Code voice questions."""

    def __init__(self):
        self.sessions: dict[str, AskSession] = {}
        self._default_timeout = 1800  # 30 minutes default

    def create_session(
        self,
        question: str,
        audio_id: str,
        timeout_seconds: int = None
    ) -> AskSession:
        """Create a new ask session."""
        session_id = str(uuid.uuid4())[:8]
        timeout = timeout_seconds or self._default_timeout
        now = datetime.now()

        session = AskSession(
            id=session_id,
            question=question,
            status="pending",
            audio_id=audio_id,
            created_at=now,
            timeout_at=now + __import__('datetime').timedelta(seconds=timeout)
        )
        self.sessions[session_id] = session
        logger.info(f"Created ask session: {session_id} (timeout={timeout}s)")
        return session

    def get_session(self, session_id: str) -> Optional[AskSession]:
        """Get a session by ID, checking for timeout."""
        session = self.sessions.get(session_id)
        if session and session.status == "pending":
            # Check if timed out
            if datetime.now() > session.timeout_at:
                session.status = "timeout"
                logger.info(f"Ask session {session_id} timed out")
        return session

    def complete_session(
        self,
        session_id: str,
        response_text: str
    ) -> Optional[AskSession]:
        """Mark session as completed with response."""
        session = self.sessions.get(session_id)
        if session:
            session.status = "completed"
            session.response_text = response_text
            session.completed_at = datetime.now()
            logger.info(f"Ask session {session_id} completed: '{response_text[:50]}...'")
        return session

    def set_listening(self, session_id: str) -> Optional[AskSession]:
        """Mark session as listening (user is recording)."""
        session = self.sessions.get(session_id)
        if session:
            session.status = "listening"
            logger.info(f"Ask session {session_id} now listening")
        return session

    def set_error(self, session_id: str, error: str) -> Optional[AskSession]:
        """Mark session as errored."""
        session = self.sessions.get(session_id)
        if session:
            session.status = "error"
            session.error = error
            logger.error(f"Ask session {session_id} error: {error}")
        return session

    def cleanup_old_sessions(self, max_age_seconds: int = 3600):
        """Remove sessions older than max age."""
        now = datetime.now()
        old = [
            sid for sid, s in self.sessions.items()
            if (now - s.created_at).total_seconds() > max_age_seconds
        ]
        for sid in old:
            del self.sessions[sid]
        if old:
            logger.info(f"Cleaned up {len(old)} old ask sessions")


# Global ask session manager
ask_session_manager = AskSessionManager()


def cleanup_old_audio():
    """Remove audio files older than max age."""
    now = datetime.now()
    expired = [
        aid for aid, (_, created, _) in _audio_storage.items()
        if (now - created).total_seconds() > _audio_max_age
    ]
    for aid in expired:
        del _audio_storage[aid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired audio files")


async def handle_push(request: web.Request) -> web.Response:
    """
    Generate TTS and push notification to watch.

    Accepts: JSON with:
      - text: Text to speak
      - voice: Optional voice name

    Returns: JSON with status
    """
    import aiohttp
    import ssl

    try:
        body = await request.json()
        text = body.get("text")
        voice = body.get("voice", TTS_VOICES[0] if TTS_VOICES else "af_sky")

        if not text:
            return web.json_response({"error": "No text provided"}, status=400)

        logger.info(f"Push request: text='{text[:50]}...'")

        # Generate TTS
        from openai import AsyncOpenAI
        from .provider_discovery import detect_provider_type, is_local_provider

        audio_data = None
        used_provider = None
        used_voice = voice

        for base_url in TTS_BASE_URLS:
            provider_type = detect_provider_type(base_url)
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            if provider_type == "openai":
                openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
                if voice not in openai_voices:
                    voice_mapping = {
                        "af_sky": "nova", "af_sarah": "nova", "af_alloy": "alloy",
                        "am_adam": "onyx", "am_echo": "echo", "am_onyx": "onyx"
                    }
                    used_voice = voice_mapping.get(voice, "alloy")
                else:
                    used_voice = voice
            else:
                used_voice = voice

            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                max_retries=max_retries
            )

            try:
                response = await client.audio.speech.create(
                    model="tts-1",
                    input=text,
                    voice=used_voice,
                    response_format="mp3"
                )
                audio_data = response.content
                used_provider = provider_type
                logger.info(f"TTS succeeded with {base_url}")
                break
            except Exception as e:
                logger.warning(f"TTS failed for {base_url}: {e}")
                continue

        if not audio_data:
            return web.json_response({"error": "TTS failed"}, status=503)

        # Store audio with unique ID
        audio_id = str(uuid.uuid4())[:8]
        _audio_storage[audio_id] = (audio_data, datetime.now(), text)
        logger.info(f"Stored audio {audio_id}: {len(audio_data)} bytes")

        # Clean up old audio
        cleanup_old_audio()

        # Build audio URL (watch will fetch from bridge)
        # Use the bridge's own URL
        audio_url = f"https://192.168.10.10:8890/audio/{audio_id}"

        # Send notification via Argus
        argus_url = "https://beelink.local:8080/api/notifications"
        notification_payload = {
            "title": "Grotto",
            "body": text[:100],
            "to_athena": True,
            "data": {
                "type": "grotto_audio",
                "audio_url": audio_url,
                "audio_id": audio_id,
                "text": text
            }
        }

        # Load mTLS certs for Argus call
        cert_dir = Path.home() / ".config" / "argus"
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_cert_chain(
            cert_dir / "client.crt",
            cert_dir / "client.key"
        )
        ssl_ctx.load_verify_locations(cert_dir / "ca.crt")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                argus_url,
                json=notification_payload,
                ssl=ssl_ctx
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    sent = result.get("sent", 0)
                    logger.info(f"Notification sent to {sent} device(s)")
                    return web.json_response({
                        "status": "ok",
                        "audio_id": audio_id,
                        "audio_url": audio_url,
                        "audio_size": len(audio_data),
                        "devices_notified": sent
                    })
                else:
                    error_text = await resp.text()
                    logger.error(f"Argus notification failed: {error_text}")
                    return web.json_response({
                        "error": "Notification failed",
                        "details": error_text
                    }, status=502)

    except Exception as e:
        logger.error(f"Push error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_audio_fetch(request: web.Request) -> web.Response:
    """
    Serve stored audio by ID.

    GET /audio/{audio_id}
    """
    audio_id = request.match_info["audio_id"]

    if audio_id not in _audio_storage:
        return web.json_response({"error": "Audio not found"}, status=404)

    audio_data, created, text = _audio_storage[audio_id]

    return web.Response(
        body=audio_data,
        content_type="audio/mpeg",
        headers={
            "X-Audio-Id": audio_id,
            "X-Text": text[:100],
            "Content-Length": str(len(audio_data))
        }
    )


# Track which audio IDs have been fetched by the watch
_fetched_audio_ids: set[str] = set()


async def handle_audio_pending(request: web.Request) -> web.Response:
    """
    Check for pending audio that hasn't been fetched yet.

    GET /audio/pending

    Returns: JSON with pending audio info, or empty if none
    """
    # Find audio that hasn't been fetched yet
    pending = []
    for audio_id, (audio_data, created, text) in _audio_storage.items():
        if audio_id not in _fetched_audio_ids:
            pending.append({
                "audio_id": audio_id,
                "text": text,
                "size": len(audio_data),
                "created_at": created.isoformat()
            })

    if not pending:
        return web.json_response({"pending": []})

    # Sort by creation time, newest first
    pending.sort(key=lambda x: x["created_at"], reverse=True)

    return web.json_response({"pending": pending})


async def handle_audio_fetch_latest(request: web.Request) -> web.Response:
    """
    Fetch the latest unfetched audio and mark it as fetched.

    GET /audio/latest

    Returns: Audio data if available, or 204 No Content if none
    """
    # Find latest unfetched audio
    latest_id = None
    latest_created = None

    for audio_id, (audio_data, created, text) in _audio_storage.items():
        if audio_id not in _fetched_audio_ids:
            if latest_created is None or created > latest_created:
                latest_id = audio_id
                latest_created = created

    if latest_id is None:
        return web.Response(status=204)  # No Content

    # Mark as fetched
    _fetched_audio_ids.add(latest_id)

    audio_data, created, text = _audio_storage[latest_id]

    logger.info(f"Serving latest audio {latest_id}: {len(audio_data)} bytes")

    return web.Response(
        body=audio_data,
        content_type="audio/mpeg",
        headers={
            "X-Audio-Id": latest_id,
            "X-Text": text[:100],
            "Content-Length": str(len(audio_data))
        }
    )


# ============================================================================
# Ask Endpoints - Claude Code voice questions
# ============================================================================

async def handle_ask_create(request: web.Request) -> web.Response:
    """
    Create a new ask session - Claude Code asks a question via voice.

    POST /ask

    Accepts: JSON with:
      - question: Text of the question to ask
      - timeout_seconds: Optional timeout (default 1800 = 30 min)
      - voice: Optional TTS voice

    Returns: JSON with session_id, status, audio_url
    """
    import aiohttp
    import ssl

    try:
        body = await request.json()
        question = body.get("question")
        timeout_seconds = body.get("timeout_seconds", 1800)
        voice = body.get("voice", TTS_VOICES[0] if TTS_VOICES else "af_sky")

        if not question:
            return web.json_response({"error": "No question provided"}, status=400)

        logger.info(f"Ask request: question='{question[:50]}...', timeout={timeout_seconds}s")

        # Generate TTS for the question
        from openai import AsyncOpenAI
        from .provider_discovery import detect_provider_type, is_local_provider

        audio_data = None
        used_provider = None
        used_voice = voice

        for base_url in TTS_BASE_URLS:
            provider_type = detect_provider_type(base_url)
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            if provider_type == "openai":
                openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
                if voice not in openai_voices:
                    voice_mapping = {
                        "af_sky": "nova", "af_sarah": "nova", "af_alloy": "alloy",
                        "am_adam": "onyx", "am_echo": "echo", "am_onyx": "onyx"
                    }
                    used_voice = voice_mapping.get(voice, "alloy")
                else:
                    used_voice = voice
            else:
                used_voice = voice

            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                max_retries=max_retries
            )

            try:
                response = await client.audio.speech.create(
                    model="tts-1",
                    input=question,
                    voice=used_voice,
                    response_format="mp3"
                )
                audio_data = response.content
                used_provider = provider_type
                logger.info(f"Ask TTS succeeded with {base_url}")
                break
            except Exception as e:
                logger.warning(f"Ask TTS failed for {base_url}: {e}")
                continue

        if not audio_data:
            return web.json_response({"error": "TTS failed"}, status=503)

        # Store audio
        audio_id = str(uuid.uuid4())[:8]
        _audio_storage[audio_id] = (audio_data, datetime.now(), question)
        logger.info(f"Stored ask audio {audio_id}: {len(audio_data)} bytes")

        # Create ask session
        session = ask_session_manager.create_session(
            question=question,
            audio_id=audio_id,
            timeout_seconds=timeout_seconds
        )

        # Clean up old audio
        cleanup_old_audio()

        # Build audio URL
        audio_url = f"https://192.168.10.10:8890/audio/{audio_id}"

        # Send notification via Argus with ask type
        argus_url = "https://beelink.local:8080/api/notifications"
        notification_payload = {
            "title": "Grotto",
            "body": question[:100],
            "to_athena": True,
            "data": {
                "type": "grotto_ask",
                "session_id": session.id,
                "audio_url": audio_url,
                "audio_id": audio_id,
                "question": question
            }
        }

        # Load mTLS certs for Argus call
        cert_dir = Path.home() / ".config" / "argus"
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_cert_chain(
            cert_dir / "client.crt",
            cert_dir / "client.key"
        )
        ssl_ctx.load_verify_locations(cert_dir / "ca.crt")

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                argus_url,
                json=notification_payload,
                ssl=ssl_ctx
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    sent = result.get("sent", 0)
                    logger.info(f"Ask notification sent to {sent} device(s)")
                    return web.json_response({
                        "session_id": session.id,
                        "status": session.status,
                        "audio_url": audio_url,
                        "audio_id": audio_id,
                        "devices_notified": sent,
                        "timeout_seconds": timeout_seconds
                    })
                else:
                    error_text = await resp.text()
                    logger.error(f"Argus notification failed: {error_text}")
                    # Session created but notification failed
                    return web.json_response({
                        "session_id": session.id,
                        "status": session.status,
                        "audio_url": audio_url,
                        "audio_id": audio_id,
                        "warning": "Notification delivery failed",
                        "details": error_text
                    }, status=202)  # Accepted but notification issue

    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    except Exception as e:
        logger.error(f"Ask create error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ask_status(request: web.Request) -> web.Response:
    """
    Get ask session status - poll for completion.

    GET /ask/{session_id}/status

    Returns: JSON with status, response_text (if completed), elapsed_ms
    """
    session_id = request.match_info["session_id"]
    session = ask_session_manager.get_session(session_id)

    if not session:
        return web.json_response({"error": "Session not found"}, status=404)

    elapsed_ms = int((datetime.now() - session.created_at).total_seconds() * 1000)

    response = {
        "session_id": session.id,
        "status": session.status,
        "question": session.question,
        "elapsed_ms": elapsed_ms,
    }

    if session.status == "completed":
        response["response_text"] = session.response_text
        if session.completed_at:
            response["completed_at"] = session.completed_at.isoformat()

    if session.status == "timeout":
        response["timeout_at"] = session.timeout_at.isoformat()

    if session.status == "error":
        response["error"] = session.error

    return web.json_response(response)


async def handle_ask_respond(request: web.Request) -> web.Response:
    """
    Submit response to ask session - watch uploads recorded audio.

    POST /ask/{session_id}/respond

    Accepts: multipart/form-data with:
      - audio: OGG audio file

    Returns: JSON with status, transcription
    """
    session_id = request.match_info["session_id"]
    session = ask_session_manager.get_session(session_id)

    if not session:
        return web.json_response({"error": "Session not found"}, status=404)

    if session.status == "completed":
        return web.json_response({
            "error": "Session already completed",
            "response_text": session.response_text
        }, status=409)

    if session.status == "timeout":
        return web.json_response({"error": "Session timed out"}, status=410)

    try:
        # Parse multipart data
        reader = await request.multipart()
        audio_data = None

        async for field in reader:
            if field.name == "audio" or field.name == "file":
                audio_data = await field.read()

        if not audio_data:
            return web.json_response({"error": "No audio file provided"}, status=400)

        logger.info(f"Ask respond: session={session_id}, audio_bytes={len(audio_data)}")

        # Mark as listening (processing)
        ask_session_manager.set_listening(session_id)

        # Convert audio to WAV for STT
        audio_io = io.BytesIO(audio_data)
        audio = AudioSegment.from_file(audio_io, format="ogg")
        audio = audio.set_channels(1).set_frame_rate(16000)

        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        # Transcribe
        stt_result = await simple_stt_failover(wav_io, model="whisper-1")

        if not stt_result or stt_result.get("error_type"):
            error_type = stt_result.get("error_type", "unknown") if stt_result else "unknown"
            ask_session_manager.set_error(session_id, f"STT failed: {error_type}")
            return web.json_response({
                "error": f"Transcription failed: {error_type}",
                "status": "error"
            }, status=503)

        transcription = stt_result.get("text", "")
        logger.info(f"Ask response transcribed: '{transcription[:100]}...'")

        # Complete the session
        ask_session_manager.complete_session(session_id, transcription)

        return web.json_response({
            "status": "ok",
            "transcription": transcription,
            "session_id": session_id,
            "provider": stt_result.get("provider")
        })

    except Exception as e:
        logger.error(f"Ask respond error: {e}", exc_info=True)
        ask_session_manager.set_error(session_id, str(e))
        return web.json_response({"error": str(e)}, status=500)


async def handle_ask_listening(request: web.Request) -> web.Response:
    """
    Mark ask session as listening - watch started recording.

    POST /ask/{session_id}/listening

    Returns: JSON with status
    """
    session_id = request.match_info["session_id"]
    session = ask_session_manager.get_session(session_id)

    if not session:
        return web.json_response({"error": "Session not found"}, status=404)

    if session.status != "pending":
        return web.json_response({
            "error": f"Cannot set listening - current status is {session.status}"
        }, status=409)

    ask_session_manager.set_listening(session_id)

    return web.json_response({
        "status": "ok",
        "session_id": session_id,
        "session_status": "listening"
    })


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application()

    # Add routes
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)  # Root also returns health

    # Session management
    app.router.add_post("/session/start", handle_session_start)
    app.router.add_get("/session/{session_id}/status", handle_session_status)
    app.router.add_post("/session/{session_id}/close", handle_session_close)

    # Audio endpoints
    app.router.add_post("/audio/transcribe", handle_transcribe)
    app.router.add_post("/audio/synthesize", handle_synthesize)

    # Full conversation
    app.router.add_post("/converse", handle_converse)

    # Push notifications (CLI to watch)
    app.router.add_post("/push", handle_push)

    # Polling fallback (for when FCM doesn't work)
    # NOTE: Specific routes before wildcard to avoid matching issues
    app.router.add_get("/audio/pending", handle_audio_pending)
    app.router.add_get("/audio/latest", handle_audio_fetch_latest)
    app.router.add_get("/audio/{audio_id}", handle_audio_fetch)

    # Ask endpoints (Claude Code voice questions)
    app.router.add_post("/ask", handle_ask_create)
    app.router.add_get("/ask/{session_id}/status", handle_ask_status)
    app.router.add_post("/ask/{session_id}/respond", handle_ask_respond)
    app.router.add_post("/ask/{session_id}/listening", handle_ask_listening)

    return app


async def run_server(host: str, port: int, ssl_cert: str = None, ssl_key: str = None, ssl_ca: str = None):
    """Run the HTTP server."""
    import ssl

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()

    # Configure SSL if certs provided
    ssl_context = None
    protocol = "http"
    if ssl_cert and ssl_key:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(ssl_cert, ssl_key)
        # Require client certificate (mTLS)
        if ssl_ca:
            ssl_context.load_verify_locations(ssl_ca)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
        protocol = "https"

    site = web.TCPSite(runner, host, port, ssl_context=ssl_context)

    logger.info(f"Starting VoiceMode HTTP Bridge v{VERSION}")
    logger.info(f"  Listening on: {protocol}://{host}:{port}")
    logger.info(f"  Mock mode: {MOCK_MODE}")
    logger.info(f"  TTS endpoints: {TTS_BASE_URLS}")
    logger.info(f"  STT endpoints: {STT_BASE_URLS}")
    if ssl_context:
        logger.info(f"  mTLS: enabled (ca={ssl_ca})")

    await site.start()

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
            session_manager.cleanup_stale_sessions()
    finally:
        await runner.cleanup()


def main():
    """Entry point for the HTTP bridge."""
    parser = argparse.ArgumentParser(description="VoiceMode HTTP Bridge")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8890, help="Port to listen on")
    parser.add_argument("--mock", action="store_true", help="Enable mock mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--ssl-cert", help="Path to SSL certificate")
    parser.add_argument("--ssl-key", help="Path to SSL private key")
    parser.add_argument("--ssl-ca", help="Path to CA certificate for client verification (mTLS)")
    args = parser.parse_args()

    # Set up logging
    setup_logging()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("voicemode").setLevel(logging.DEBUG)

    # Set mock mode
    global MOCK_MODE
    if args.mock:
        MOCK_MODE = True

    # Run server
    asyncio.run(run_server(args.host, args.port, args.ssl_cert, args.ssl_key, args.ssl_ca))


if __name__ == "__main__":
    main()
