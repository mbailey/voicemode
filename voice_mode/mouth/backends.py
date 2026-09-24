"""Backends: text in, a stream of mono float32 audio blocks out.

A backend is anything with ``name``, ``sample_rate`` and
``stream(text, voice, speed) -> Iterator[np.ndarray]``. The first block
coming back is what ``gen_s`` measures. Three ship:

- ``kokoro``: an OpenAI-compatible ``/audio/speech`` server with native
  voice names (``af_sky``); ``VOICEMODE_MOUTH_KOKORO_URL``, default the
  mlx-audio service on 8890 with ``mlx-community/Kokoro-82M-bf16``.
- ``clone``: the same endpoint with ``ref_audio``/``ref_text`` for the
  voices under ``~/.voicemode/voices`` (``pip``, ``laurie``), resolved by
  ``voice_profiles.resolve_voice`` exactly as converse resolves them.
- ``silence``: no server, no sound; paced blocks of zeros, one second per
  15 characters. For tests and dry runs.

``auto`` picks ``clone`` when the voice resolves to a clone, else ``kokoro``.
"""

from __future__ import annotations

import os
from typing import Iterator, Optional, Protocol

import numpy as np

SAMPLE_RATE = 24000
BLOCK_S = 0.05  # 50 ms: how often playback looks for a stop


class Backend(Protocol):
    name: str
    sample_rate: int

    def stream(self, text: str, voice: str, speed: Optional[float]) -> Iterator[np.ndarray]: ...


class OpenAISpeech:
    """POST {base_url}/audio/speech, response_format pcm (s16le mono), streamed."""

    def __init__(self, name: str, base_url: str, model: str, *,
                 extra_body: Optional[dict] = None, sample_rate: int = SAMPLE_RATE,
                 api_key: Optional[str] = None, timeout: float = 60.0) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.extra_body = extra_body or {}
        self.sample_rate = sample_rate
        self.api_key = api_key
        self.timeout = timeout

    def stream(self, text: str, voice: str, speed: Optional[float]) -> Iterator[np.ndarray]:
        import httpx

        body = {"model": self.model, "input": text, "voice": voice, "response_format": "pcm",
                **self.extra_body}
        if speed is not None:
            body["speed"] = speed
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        carry = b""
        with httpx.stream("POST", f"{self.base_url}/audio/speech", json=body,
                          headers=headers, timeout=self.timeout) as r:
            if r.status_code != 200:
                r.read()
                raise RuntimeError(f"{self.name}: HTTP {r.status_code}: {r.text[:200]}")
            for chunk in r.iter_bytes():
                data = carry + chunk
                cut = len(data) - (len(data) % 2)  # s16: never split a sample
                carry = data[cut:]
                if cut:
                    yield np.frombuffer(data[:cut], dtype="<i2").astype(np.float32) / 32768.0


class Silence:
    """A backend with no server and no sound: zeros, 15 characters a second."""

    name = "silence"
    sample_rate = SAMPLE_RATE

    def __init__(self, chars_per_s: float = 15.0, gen_s: float = 0.0) -> None:
        self.chars_per_s = chars_per_s
        self.gen_s = gen_s

    def stream(self, text: str, voice: str, speed: Optional[float]) -> Iterator[np.ndarray]:
        import time

        if self.gen_s:
            time.sleep(self.gen_s)
        total = int(max(len(text), 1) / self.chars_per_s / (speed or 1.0) * self.sample_rate)
        step = int(self.sample_rate * BLOCK_S)
        for i in range(0, total, step):
            yield np.zeros(min(step, total - i), dtype=np.float32)


def resolve(backend: str, voice: str) -> tuple[Backend, str]:
    """(backend, the voice name to send it). Raises ValueError, loudly, on a bad pair."""
    if backend == "silence":
        return Silence(), voice
    if backend in ("auto", "clone"):
        from voice_mode.voice_profiles import VoiceResolutionError, resolve_voice

        try:
            res = resolve_voice(voice)
        except VoiceResolutionError as e:
            if backend == "clone":
                raise ValueError(str(e)) from e
            res = None
        if res is not None and res.profile is not None:
            p = res.profile
            return OpenAISpeech("clone", p.base_url, p.model, extra_body={
                "ref_audio": p.ref_audio, "ref_text": p.ref_text, "stream": True,
                "streaming_interval": 0.3, "lang_code": "auto"}), voice
        if backend == "clone":
            raise ValueError(f"voice {voice!r} is not a clone voice")
        if res is not None:
            voice = res.resolved
    if backend in ("auto", "kokoro"):
        return OpenAISpeech(
            "kokoro",
            os.environ.get("VOICEMODE_MOUTH_KOKORO_URL", "http://127.0.0.1:8890/v1"),
            os.environ.get("VOICEMODE_MOUTH_KOKORO_MODEL", "mlx-community/Kokoro-82M-bf16"),
        ), voice
    raise ValueError(f"unknown backend {backend!r}: auto, kokoro, clone or silence")
