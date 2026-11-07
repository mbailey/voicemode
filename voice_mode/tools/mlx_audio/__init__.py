"""mlx-audio service tools.

Unified Whisper STT + Kokoro TTS + Qwen3-TTS clone-voice service for
Apple Silicon. Uses ``uv tool install mlx-audio`` (pinned ``>=0.5.7,<0.6``)
with no service-local venv. The upstream server.py is used unmodified:
voicemode used to ship a ``mlx_audio_server.patch`` for MLX Metal
serialisation (upstream since 0.4.3, VM-1126) and OpenAI-style STT
``response_format`` (upstream since 0.4.4, VM-2338); both are native now.
"""

from voice_mode.tools.mlx_audio.install import mlx_audio_install
from voice_mode.tools.mlx_audio.status import mlx_audio_status
from voice_mode.tools.mlx_audio.uninstall import mlx_audio_uninstall

__all__ = [
    "mlx_audio_install",
    "mlx_audio_status",
    "mlx_audio_uninstall",
]
