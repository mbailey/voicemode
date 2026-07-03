"""faster-whisper (speaches) service tools.

OpenAI-compatible STT service backed by faster-whisper via speaches.
Exposes /v1/audio/transcriptions on port 2023 by default.
"""

from voice_mode.tools.faster_whisper.install import faster_whisper_install

__all__ = [
    "faster_whisper_install",
]
