"""MCP resources for Whisper model management."""

import os
import json
from pathlib import Path
from typing import Dict, Any, List

from ..server import mcp
from ..config import logger


@mcp.resource("whisper://models")
async def list_whisper_models() -> str:
    """
    List available Whisper models on the local system.
    
    Returns information about:
    - Installed models with size and location
    - Currently configured model (via WHISPER_MODEL env var)
    - Default model
    - Models directory location
    
    This resource helps users understand what models are available
    and which one is currently being used by the whisper server.
    """
    try:
        # Get whisper models directory
        models_dir = Path.home() / ".voicemode/whisper.cpp/models"
        
        # List all model files
        models: List[Dict[str, Any]] = []
        
        if models_dir.exists():
            for model_file in models_dir.glob("ggml-*.bin"):
                model_name = model_file.stem.replace("ggml-", "")
                file_size = model_file.stat().st_size
                
                models.append({
                    "name": model_name,
                    "path": str(model_file),
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 1),
                    "size_gb": round(file_size / (1024 * 1024 * 1024), 2)
                })
        
        # Sort models by name
        models.sort(key=lambda x: x["name"])
        
        # Get current configuration
        current_model = os.environ.get("VOICEMODE_WHISPER_MODEL", "large-v2")
        
        # Build response
        data = {
            "models_directory": str(models_dir),
            "installed_models": models,
            "total_models": len(models),
            "current_model": current_model,
            "default_model": "large-v2",
            "environment_variable": "VOICEMODE_WHISPER_MODEL",
            "total_size_mb": round(sum(m["size_mb"] for m in models), 1) if models else 0
        }
        
        # Add recommendations based on available models
        if not models:
            data["recommendation"] = "No models installed. Run 'install_whisper_cpp' tool to install models."
        elif current_model not in [m["name"] for m in models]:
            data["recommendation"] = f"Configured model '{current_model}' not found. Available models: {', '.join(m['name'] for m in models)}"
        
        return json.dumps(data, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error listing whisper models: {e}")
        return json.dumps({
            "error": str(e),
            "models_directory": str(Path.home() / ".voicemode/whisper.cpp/models"),
            "installed_models": [],
            "total_models": 0
        }, indent=2)