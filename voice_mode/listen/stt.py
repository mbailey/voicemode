"""Transcription for ``listen``, behind one small interface.

``STT.transcribe(audio) -> str`` takes 16 kHz mono int16 and returns text.
Whisper (today's local server) is the only backend now; Apple on-device
speech is spec task 3.5 and slots in beside it.
"""

from __future__ import annotations

import io
import os
import re
import time
import wave
from typing import Protocol

import numpy as np

from .sources import SAMPLE_RATE

DEFAULT_WHISPER_URL = os.getenv("VOICEMODE_LISTEN_STT_URL", "http://127.0.0.1:2022/v1")
DEFAULT_WHISPER_MODEL = os.getenv("VOICEMODE_LISTEN_STT_MODEL", "whisper-1")


class STTError(RuntimeError):
    pass


# whisper's non-speech annotations: "[BLANK_AUDIO]", "(static)", "[BEEP]",
# "(upbeat music)", "*sighs*". Heard on m5 04:10 Thu 2026-09-24 from a noise
# tail in ~/.cora/apple-fm/scratch/vad/fixture.wav; left in, they would turn
# a quiet room's hiss into partials and turns.
_ANNOTATION = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")


def strip_annotations(text: str) -> str:
    """Remove bracketed non-speech tags; collapse the whitespace left behind."""
    return " ".join(_ANNOTATION.sub(" ", text).split())


class STT(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray) -> str:
        ...


def to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(np.asarray(audio, dtype=np.int16).tobytes())
    return buf.getvalue()


class WhisperSTT:
    """OpenAI-compatible ``POST {base_url}/audio/transcriptions`` (whisper.cpp on :2022)."""

    name = "whisper"

    def __init__(
        self,
        base_url: str = DEFAULT_WHISPER_URL,
        *,
        model: str = DEFAULT_WHISPER_MODEL,
        timeout: float = 30.0,
        language: str | None = None,
        drop_annotations: bool = True,
        connect_retries: int = 1,
        retry_delay_s: float = 0.3,
    ) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.drop_annotations = drop_annotations
        self.connect_retries = connect_retries
        self.retry_delay_s = retry_delay_s
        self._client = httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))

    def transcribe(self, audio: np.ndarray) -> str:
        data = {"model": self.model, "response_format": "json"}
        if self.language:
            data["language"] = self.language
        import httpx

        wav = to_wav_bytes(audio)
        for attempt in range(1 + self.connect_retries):
            try:
                resp = self._client.post(
                    f"{self.base_url}/audio/transcriptions",
                    files={"file": ("chunk.wav", wav, "audio/wav")},
                    data=data,
                )
                resp.raise_for_status()
                text = str(resp.json().get("text", "")).strip()
                break
            except httpx.ConnectError as exc:
                # A refused connection is retried: seen once on m5 04:11 Thu
                # 2026-09-24 mid-listen, and it cost that chunk's words.
                if attempt < self.connect_retries:
                    time.sleep(self.retry_delay_s)
                    continue
                raise STTError(f"whisper at {self.base_url}: {exc}") from exc
            except Exception as exc:
                raise STTError(f"whisper at {self.base_url}: {exc}") from exc
        return strip_annotations(text) if self.drop_annotations else text

    def close(self) -> None:
        self._client.close()
