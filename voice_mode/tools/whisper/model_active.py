"""MCP tool for showing/setting active Whisper model."""

from typing import Optional, Dict, Any
from voice_mode.tools.whisper.models import (
    get_active_model,
    set_active_model,
    is_whisper_model_installed,
    WHISPER_MODEL_REGISTRY
)


async def whisper_model_active(model_name: Optional[str] = None) -> Dict[str, Any]:
    """Show or set the active Whisper model.
    
    Args:
        model_name: Model to set as active (None to just show current)
        
    Returns:
        Dict with current/new active model info
    """
    if model_name is None:
        # Just show current
        current = get_active_model()
        return {
            "success": True,
            "active_model": current,
            "installed": is_whisper_model_installed(current),
            "message": f"Current active model: {current}"
        }
    
    # Validate model exists in registry
    if model_name not in WHISPER_MODEL_REGISTRY:
        return {
            "success": False,
            "error": f"Model {model_name} is not a valid Whisper model",
            "available_models": list(WHISPER_MODEL_REGISTRY.keys())
        }
    
    # Check if model is installed
    if not is_whisper_model_installed(model_name):
        return {
            "success": False,
            "error": f"Model {model_name} is not installed. Install it first with whisper_model_install()",
            "model": model_name
        }
    
    # Set new active model
    set_active_model(model_name)
    
    return {
        "success": True,
        "active_model": model_name,
        "message": f"Active model set to {model_name}. Restart whisper service for changes to take effect."
    }