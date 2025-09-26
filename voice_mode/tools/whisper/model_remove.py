"""MCP tool for removing Whisper models."""

from typing import Dict, Any
from voice_mode.tools.whisper.models import (
    remove_whisper_model,
    get_active_model,
    format_size
)


async def whisper_model_remove(model_name: str, remove_coreml: bool = True) -> Dict[str, Any]:
    """Remove an installed Whisper model.
    
    Args:
        model_name: Name of model to remove
        remove_coreml: Also remove Core ML version if exists
        
    Returns:
        Dict with removal status
    """
    # Check if trying to remove active model
    if model_name == get_active_model():
        return {
            "success": False,
            "error": f"Cannot remove active model {model_name}. Set a different model as active first using whisper_model_active()"
        }
    
    # Remove the model
    result = remove_whisper_model(model_name, remove_coreml)
    
    # Format the result for better readability
    if result["success"]:
        result["space_freed_formatted"] = format_size(result.get("space_freed_mb", 0))
        result["message"] = f"Successfully removed model {model_name}"
    
    return result