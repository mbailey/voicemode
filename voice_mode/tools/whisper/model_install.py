"""Download Whisper models with Core ML support."""

import os
import sys
import json
import logging
import platform
import subprocess
from pathlib import Path
from typing import Union, List, Dict, Any

from voice_mode.server import mcp
from voice_mode.config import logger, MODELS_DIR, DEFAULT_WHISPER_MODEL
from voice_mode.utils.services.whisper_helpers import download_whisper_model, get_available_models

logger = logging.getLogger("voicemode")


@mcp.tool()
async def whisper_model_install(
    model: Union[str, List[str]] = DEFAULT_WHISPER_MODEL,
    force_download: Union[bool, str] = False,
    skip_core_ml: Union[bool, str] = False
) -> str:
    """Download Whisper model(s) with pre-built Core ML support.

    Downloads whisper.cpp models to the configured directory. On Apple Silicon,
    automatically downloads pre-built Core ML models from Hugging Face for
    2-3x better performance. No Python dependencies or Xcode required!

    Args:
        model: Model name(s) to download. Can be:
               - Single model: "base"
               - List of models: ["base", "small"]
               - "all" to download all available models
        force_download: Re-download even if model exists (default: False)
        skip_core_ml: Skip Core ML download on Apple Silicon (default: False)
        
    Available models:
        - tiny, tiny.en
        - base, base.en
        - small, small.en
        - medium, medium.en
        - large-v1, large-v2, large-v3
        - large-v3-turbo
        
    Returns:
        Status message with download results
        
    Examples:
        # Download default model
        download_model()
        
        # Download specific model
        download_model("small.en")
        
        # Download multiple models
        download_model(["base", "small", "medium"])
        
        # Download all models
        download_model("all")
        
        # Force re-download
        download_model("large-v3", force_download=True)
    """
    try:
        # Get model directory from configuration
        models_dir = MODELS_DIR / "whisper"
        
        # Check both possible whisper installation locations
        whisper_install_dir = Path.home() / ".voicemode" / "services" / "whisper"
        legacy_install_dir = Path.home() / ".voicemode" / "whisper.cpp"
        
        if whisper_install_dir.exists():
            actual_models_dir = whisper_install_dir / "models"
        elif legacy_install_dir.exists():
            actual_models_dir = legacy_install_dir / "models"
        else:
            return json.dumps({
                "success": False,
                "error": "Whisper.cpp not installed. Please run whisper_install first."
            }, indent=2)
        
        # CoreML dependencies no longer needed - using pre-built models from Hugging Face!
        # Just check if we're on Apple Silicon and should download Core ML models
        if platform.system() == "Darwin" and platform.machine() == "arm64" and not skip_core_ml:
            logger.info("Apple Silicon detected - will download pre-built Core ML models for optimal performance")
        elif skip_core_ml:
            logger.info("Skipping Core ML models as requested")
        
        # Parse model input
        available_models = get_available_models()
        
        if isinstance(model, str):
            if model.lower() == "all":
                models_to_download = available_models
            else:
                models_to_download = [model]
        else:
            models_to_download = model
        
        # Validate models
        invalid_models = [m for m in models_to_download if m not in available_models]
        if invalid_models:
            return json.dumps({
                "success": False,
                "error": f"Invalid models: {', '.join(invalid_models)}",
                "available_models": available_models
            }, indent=2)
        
        # Download models
        results = []
        success_count = 0
        
        for model_name in models_to_download:
            logger.info(f"Processing model: {model_name}")
            result = await download_whisper_model(
                model_name,
                actual_models_dir,
                force_download=force_download,
                skip_core_ml=skip_core_ml
            )
            
            # Build comprehensive result entry
            model_result = {
                "model": model_name,
                "download_success": result["success"],
                "message": result.get("message", result.get("error", "Unknown error")),
                "acceleration": result.get("acceleration", "unknown")
            }
            
            # Include Core ML status if available
            if "core_ml_status" in result and not skip_core_ml:
                core_ml = result["core_ml_status"]
                model_result["core_ml"] = {
                    "attempted": True,
                    "success": core_ml.get("success", False),
                    "error_category": core_ml.get("error_category") if not core_ml.get("success") else None,
                    "error": core_ml.get("error") if not core_ml.get("success") else None,
                    "method": "pre-built download" if core_ml.get("success") else None
                }
            elif skip_core_ml:
                model_result["core_ml"] = {
                    "attempted": False,
                    "reason": "Skipped by user request"
                }
            
            results.append(model_result)
            
            if result["success"]:
                success_count += 1
        
        # Summary
        total_models = len(models_to_download)
        
        # Collect warnings and recommendations
        warnings = []
        recommendations = []
        
        # Check for Core ML issues
        core_ml_failures = [r for r in results if r.get("core_ml", {}).get("attempted") and not r.get("core_ml", {}).get("success")]
        if core_ml_failures:
            # Group by error category
            error_categories = {}
            for failure in core_ml_failures:
                category = failure["core_ml"].get("error_category", "unknown")
                if category not in error_categories:
                    error_categories[category] = failure["core_ml"]
            
            # Add warnings for each category
            if "not_available" in error_categories:
                warnings.append("Pre-built Core ML model not available for this model")
                recommendations.append("Model will use Metal acceleration which is still fast")
            elif "download_failed" in error_categories:
                warnings.append("Core ML model download failed - check network connection")
                recommendations.append("Try again later or use --skip-coreml to proceed without Core ML")

            # General Core ML recommendation
            if len(core_ml_failures) == len(results):
                recommendations.append("Models will use Metal acceleration. Core ML would provide 2-3x better performance.")
        
        summary = {
            "success": success_count > 0,
            "models_directory": str(actual_models_dir),
            "total_requested": total_models,
            "successful_downloads": success_count,
            "failed_downloads": total_models - success_count,
            "results": results,
            "core_ml_available": not skip_core_ml and os.uname().machine == "arm64",
        }
        
        # Add warnings and recommendations if present
        if warnings:
            summary["warnings"] = warnings
        if recommendations:
            summary["recommendations"] = recommendations
        
        # Add overall status message
        if success_count == total_models:
            if core_ml_failures:
                summary["status"] = "Models downloaded successfully but Core ML download failed. Using Metal acceleration."
            else:
                summary["status"] = "Models downloaded successfully with Core ML acceleration. Ready to use!"
        else:
            summary["status"] = "Some models failed to download. Check the results for details."
        
        return json.dumps(summary, indent=2)
        
    except Exception as e:
        logger.error(f"Error in download_model: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)


