"""
Kokoro ONNX TTS Server - OpenAI-compatible TTS endpoint using kokoro-onnx.

This server provides a lightweight alternative to the PyTorch-based Kokoro FastAPI,
using ONNX Runtime for faster CPU inference and lower memory usage.

Exposes OpenAI-compatible endpoint:
    POST /v1/audio/speech
"""

import asyncio
import io
import logging
import os
import struct
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("voicemode.kokoro_onnx")

# Lazy-loaded kokoro instance
_kokoro: Optional["Kokoro"] = None


def get_models_dir() -> Path:
    """Get the models directory path."""
    base_dir = Path(os.environ.get("VOICEMODE_BASE_DIR", Path.home() / ".voicemode"))
    return Path(os.environ.get("VOICEMODE_KOKORO_ONNX_MODELS_DIR", base_dir / "models"))


def get_model_path() -> Path:
    """Get the ONNX model file path."""
    models_dir = get_models_dir()
    model_name = os.environ.get("VOICEMODE_KOKORO_ONNX_MODEL", "kokoro-v1.0.int8.onnx")
    return models_dir / model_name


def get_voices_path() -> Path:
    """Get the voices file path."""
    models_dir = get_models_dir()
    voices_name = os.environ.get("VOICEMODE_KOKORO_ONNX_VOICES", "voices-v1.0.bin")
    return models_dir / voices_name


def get_kokoro() -> "Kokoro":
    """Get or initialize the Kokoro ONNX instance."""
    global _kokoro
    if _kokoro is None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise RuntimeError(
                "kokoro-onnx is not installed. "
                "Install with: pip install kokoro-onnx"
            )

        model_path = get_model_path()
        voices_path = get_voices_path()

        if not model_path.exists():
            raise RuntimeError(
                f"Model not found: {model_path}\n"
                "Download from: https://github.com/thewh1teagle/kokoro-onnx/releases\n"
                "Recommended: kokoro-v1.0.int8.onnx (88MB)"
            )

        if not voices_path.exists():
            raise RuntimeError(
                f"Voices file not found: {voices_path}\n"
                "Download from: https://github.com/thewh1teagle/kokoro-onnx/releases\n"
                "Required: voices-v1.0.bin"
            )

        logger.info(f"Loading Kokoro ONNX model from {model_path}")
        _kokoro = Kokoro(str(model_path), str(voices_path))
        logger.info("Kokoro ONNX model loaded successfully")

    return _kokoro


# FastAPI app
app = FastAPI(
    title="Kokoro ONNX TTS",
    description="OpenAI-compatible TTS using Kokoro ONNX",
    version="1.0.0",
)


class SpeechRequest(BaseModel):
    """OpenAI-compatible speech request."""
    model: str = Field(default="kokoro", description="Model name (ignored, uses kokoro-onnx)")
    input: str = Field(..., description="Text to synthesise")
    voice: str = Field(default="af_heart", description="Voice name")
    response_format: str = Field(default="pcm", description="Audio format: pcm, wav, mp3")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speech speed")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "kokoro-onnx"}


@app.get("/v1/voices")
async def list_voices():
    """List available voices."""
    # Standard Kokoro voices
    voices = [
        "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
        "am_adam", "am_michael",
        "bf_emma", "bf_isabella",
        "bm_george", "bm_lewis",
    ]
    return {"voices": voices}


@app.post("/v1/audio/speech")
async def create_speech(request: SpeechRequest):
    """
    OpenAI-compatible text-to-speech endpoint.

    Returns audio in the requested format (pcm, wav, or mp3).
    """
    try:
        kokoro = get_kokoro()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not request.input.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    try:
        # Generate audio
        samples, sample_rate = kokoro.create(
            request.input,
            voice=request.voice,
            speed=request.speed,
        )

        # Convert to requested format
        if request.response_format == "pcm":
            # Raw PCM: 16-bit signed little-endian
            audio_data = (samples * 32767).astype(np.int16).tobytes()
            media_type = "audio/pcm"

        elif request.response_format == "wav":
            # WAV format
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes((samples * 32767).astype(np.int16).tobytes())
            audio_data = buffer.getvalue()
            media_type = "audio/wav"

        elif request.response_format == "mp3":
            # MP3 requires pydub/ffmpeg
            try:
                from pydub import AudioSegment

                # Create AudioSegment from raw samples
                audio_segment = AudioSegment(
                    data=(samples * 32767).astype(np.int16).tobytes(),
                    sample_width=2,
                    frame_rate=sample_rate,
                    channels=1,
                )

                buffer = io.BytesIO()
                audio_segment.export(buffer, format="mp3", bitrate="64k")
                audio_data = buffer.getvalue()
                media_type = "audio/mpeg"
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="MP3 format requires pydub. Use pcm or wav instead."
                )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {request.response_format}. Use pcm, wav, or mp3."
            )

        return Response(content=audio_data, media_type=media_type)

    except Exception as e:
        logger.exception("TTS generation failed")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")


def main():
    """Run the server."""
    import uvicorn

    port = int(os.environ.get("VOICEMODE_KOKORO_ONNX_PORT", "8881"))
    host = os.environ.get("VOICEMODE_KOKORO_ONNX_HOST", "0.0.0.0")

    logger.info(f"Starting Kokoro ONNX server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
