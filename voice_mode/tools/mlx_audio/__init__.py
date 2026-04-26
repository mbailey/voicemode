"""mlx-audio service tools.

Unified Whisper STT + Kokoro TTS + Qwen3-TTS clone-voice service for
Apple Silicon. Mirrors the kokoro install pattern but uses a single
``uv pip install mlx-audio`` step instead of cloning a repo and running
service-specific start scripts.

See: VM-1076 (research), VM-1078 (this scaffolding).
"""

from voice_mode.tools.mlx_audio import install  # noqa: F401
from voice_mode.tools.mlx_audio import uninstall  # noqa: F401
