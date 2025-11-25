"""Core transcription functionality."""

import asyncio
from pathlib import Path
from typing import Optional, Union, BinaryIO, Dict, Any

from .types import TranscriptionResult, TranscriptionBackend, OutputFormat
from .backends import (
    transcribe_with_openai,
    transcribe_with_whisperx,
    transcribe_with_whisper_cpp,
    transcribe_with_whisper_cli
)
from .formats import convert_to_format


async def transcribe_audio(
    audio_file: Union[str, Path, BinaryIO],
    word_timestamps: bool = False,
    backend: TranscriptionBackend = TranscriptionBackend.OPENAI,
    output_format: OutputFormat = OutputFormat.JSON,
    language: Optional[str] = None,
    model: str = "whisper-1"
) -> TranscriptionResult:
    """
    Transcribe audio with optional word-level timestamps.
    
    This is the main API entry point for VoiceMode transcription.
    
    Args:
        audio_file: Path to audio file or file-like object
        word_timestamps: Include word-level timestamps
        backend: Which transcription backend to use
        output_format: Output format for transcription
        language: Language code (e.g., 'en', 'es', 'fr')
        model: Model to use (for OpenAI backend)
        
    Returns:
        TranscriptionResult with transcription data
    """
    # Convert path to Path object
    if isinstance(audio_file, str):
        audio_path = Path(audio_file)
    elif isinstance(audio_file, Path):
        audio_path = audio_file
    else:
        # Handle BinaryIO case
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_file.read())
            audio_path = Path(tmp.name)
    
    # Validate file exists
    if not audio_path.exists():
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend=backend.value,
            success=False,
            error=f"Audio file not found: {audio_path}"
        )
    
    # Call appropriate backend
    try:
        if backend == TranscriptionBackend.OPENAI:
            result = await transcribe_with_openai(
                audio_path,
                word_timestamps=word_timestamps,
                language=language,
                model=model
            )
        elif backend == TranscriptionBackend.WHISPERX:
            result = await transcribe_with_whisperx(
                audio_path,
                word_timestamps=word_timestamps,
                language=language
            )
        elif backend == TranscriptionBackend.WHISPER_CPP:
            result = await transcribe_with_whisper_cpp(
                audio_path,
                word_timestamps=word_timestamps,
                language=language
            )
        elif backend == TranscriptionBackend.WHISPER_CLI:
            result = await transcribe_with_whisper_cli(
                audio_path,
                word_timestamps=word_timestamps,
                language=language
            )
        else:
            return TranscriptionResult(
                text="",
                language="",
                segments=[],
                backend=backend.value,
                success=False,
                error=f"Unknown backend: {backend}"
            )
        
        # Convert format if needed
        if output_format != OutputFormat.JSON and result.get("success", False):
            formatted_content = convert_to_format(result, output_format)
            result["formatted_content"] = formatted_content
        
        return result
        
    except Exception as e:
        return TranscriptionResult(
            text="",
            language="",
            segments=[],
            backend=backend.value,
            success=False,
            error=str(e)
        )
    finally:
        # Clean up temp file if created from BinaryIO
        if not isinstance(audio_file, (str, Path)) and audio_path.exists():
            audio_path.unlink()


def transcribe_audio_sync(
    audio_file: Union[str, Path, BinaryIO],
    word_timestamps: bool = False,
    backend: TranscriptionBackend = TranscriptionBackend.OPENAI,
    output_format: OutputFormat = OutputFormat.JSON,
    language: Optional[str] = None,
    model: str = "whisper-1"
) -> TranscriptionResult:
    """
    Synchronous wrapper for transcribe_audio.
    
    Useful for CLI and non-async contexts.
    """
    return asyncio.run(transcribe_audio(
        audio_file=audio_file,
        word_timestamps=word_timestamps,
        backend=backend,
        output_format=output_format,
        language=language,
        model=model
    ))