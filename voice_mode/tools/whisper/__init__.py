"""Whisper service tools."""

from voice_mode.tools.whisper.install import whisper_install
from voice_mode.tools.whisper.uninstall import whisper_uninstall
from voice_mode.tools.whisper.model_install import whisper_model_install
from voice_mode.tools.whisper.list_models import whisper_models
from voice_mode.tools.whisper.model_active import whisper_model_active
from voice_mode.tools.whisper.model_remove import whisper_model_remove
from voice_mode.tools.whisper.model_benchmark import whisper_model_benchmark

__all__ = [
    'whisper_install',
    'whisper_uninstall', 
    'whisper_model_install',
    'whisper_models',
    'whisper_model_active',
    'whisper_model_remove',
    'whisper_model_benchmark'
]

# Backwards compatibility aliases
download_model = whisper_model_install  # Deprecated alias
whisper_list_models = whisper_models    # Deprecated alias