"""Backend implementations for transcription."""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx

from voice_mode.config import OPENAI_API_KEY, STT_EXTRA_HEADERS
from .types import TranscriptionResult


async def transcribe_with_openai(
    audio_path: Path,
    word_timestamps: bool = False,
    language: Optional[str] = None,
    model: str = "whisper-1"
) -> TranscriptionResult:
    """
    Transcribe using OpenAI API with optional word-level timestamps.
    """
    
    # Import OpenAI client
    from openai import AsyncOpenAI
    
    # Get API key from VoiceMode config
    api_key = OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend="openai",
            success=False,
            error="OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
        )
    
    # Initialize async client (automatically respects OPENAI_BASE_URL env var)
    client = AsyncOpenAI(api_key=api_key, default_headers=STT_EXTRA_HEADERS or None)
    
    # Prepare timestamp granularities
    timestamp_granularities = ["segment"]
    if word_timestamps:
        timestamp_granularities.append("word")
    
    try:
        # Open and transcribe the audio file
        with open(audio_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=timestamp_granularities,
                language=language
            )
        
        # Convert response to dictionary
        result = transcription.model_dump() if hasattr(transcription, 'model_dump') else transcription.dict()
        
        # Format response
        formatted = TranscriptionResult(
            text=result.get("text", ""),
            language=result.get("language", ""),
            duration=result.get("duration", 0),
            segments=[],
            backend="openai",
            model=model,
            success=True
        )
        
        # Process segments
        for segment in result.get("segments", []):
            seg_data = {
                "id": segment.get("id"),
                "text": segment.get("text", "").strip(),
                "start": segment.get("start", 0),
                "end": segment.get("end", 0)
            }
            formatted["segments"].append(seg_data)
        
        # Handle word timestamps - OpenAI returns them at the top level
        if word_timestamps and "words" in result:
            formatted["words"] = [
                {
                    "word": w.get("word", ""),
                    "start": w.get("start", 0),
                    "end": w.get("end", 0)
                }
                for w in result.get("words", [])
            ]
        else:
            formatted["words"] = []
        
        return formatted
        
    except Exception as e:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend="openai",
            success=False,
            error=str(e)
        )


async def transcribe_with_whisperx(
    audio_path: Path,
    word_timestamps: bool = True,
    language: Optional[str] = None
) -> TranscriptionResult:
    """
    Transcribe using WhisperX for enhanced word-level alignment.
    """
    
    try:
        # Try importing WhisperX
        import whisperx
        import torch
    except ImportError:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend="whisperx",
            success=False,
            error="WhisperX not installed. Install with: pip install git+https://github.com/m-bain/whisperX.git"
        )
    
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        # Load model
        model = whisperx.load_model("large-v3", device, compute_type=compute_type)
        
        # Load audio
        audio = whisperx.load_audio(str(audio_path))
        
        # Transcribe
        result = model.transcribe(audio, batch_size=16, language=language)
        
        # Align for word timestamps if requested
        if word_timestamps:
            # Load alignment model
            model_a, metadata = whisperx.load_align_model(
                language_code=result.get("language", language or "en"),
                device=device
            )
            
            # Align
            result = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False
            )
        
        # Format response
        formatted = TranscriptionResult(
            text=" ".join(s.get("text", "") for s in result.get("segments", [])),
            language=result.get("language", ""),
            segments=result.get("segments", []),
            backend="whisperx",
            success=True
        )
        
        # Add enhanced_alignment flag
        if word_timestamps:
            formatted["enhanced_alignment"] = True
        
        # Flatten words if available
        if word_timestamps:
            formatted["words"] = []
            for segment in formatted["segments"]:
                if "words" in segment:
                    formatted["words"].extend(segment["words"])
        
        return formatted
        
    except Exception as e:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend="whisperx",
            success=False,
            error=str(e)
        )


async def transcribe_with_whisper_cpp(
    audio_path: Path,
    word_timestamps: bool = False,
    language: Optional[str] = None
) -> TranscriptionResult:
    """
    Transcribe using local whisper.cpp server.
    """
    
    # Check if whisper-server is running (using localhost:2022 as configured)
    server_url = "http://localhost:2022/v1/audio/transcriptions"
    
    # Convert audio to WAV if needed
    if audio_path.suffix.lower() != ".wav":
        # Use ffmpeg to convert
        wav_path = Path(tempfile.mktemp(suffix=".wav"))
        try:
            subprocess.run([
                "ffmpeg", "-i", str(audio_path),
                "-ar", "16000", "-ac", "1", "-f", "wav",
                str(wav_path)
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return TranscriptionResult(
                text="",
                language="",
                segments=[],
                backend="whisper-cpp",
                success=False,
                error=f"Failed to convert audio to WAV: {e.stderr.decode() if e.stderr else str(e)}"
            )
    else:
        wav_path = audio_path
    
    try:
        # Read audio file
        with open(wav_path, "rb") as f:
            audio_data = f.read()
        
        # Prepare request
        files = {"file": ("audio.wav", audio_data, "audio/wav")}
        data = {
            "response_format": "verbose_json" if word_timestamps else "json",
            "word_timestamps": "true" if word_timestamps else "false"
        }
        if language:
            data["language"] = language
        
        # Send request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                server_url,
                files=files,
                data=data,
                timeout=120.0
            )
        
        if response.status_code != 200:
            raise Exception(f"Whisper server error: {response.text}")
        
        result = response.json()
        
        # Format response
        formatted = TranscriptionResult(
            text=result.get("text", ""),
            language=result.get("language", ""),
            segments=result.get("segments", []),
            backend="whisper-cpp",
            success=True
        )
        
        # Add word timestamps if available
        if word_timestamps and "words" in result:
            formatted["words"] = result["words"]
        
        return formatted
        
    except Exception as e:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend="whisper-cpp",
            success=False,
            error=str(e)
        )
        
    finally:
        # Clean up temp file if created
        if wav_path != audio_path and wav_path.exists():
            wav_path.unlink()