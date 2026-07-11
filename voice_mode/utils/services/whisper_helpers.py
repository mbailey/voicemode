"""Helper functions for whisper service management."""

import os
import re
import subprocess
import platform
import logging
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Union

# Core ML setup no longer needed - using pre-built models from Hugging Face
# from .coreml_setup import setup_coreml_venv, get_coreml_python

from voice_mode.utils.download import download_with_progress_async

logger = logging.getLogger("voicemode")

def find_whisper_server() -> Optional[str]:
    """Find the whisper-server binary."""
    # Check common installation paths
    paths_to_check = [
        Path.home() / ".voicemode" / "services" / "whisper" / "build" / "bin" / "whisper-server",  # New location
        Path.home() / ".voicemode" / "whisper.cpp" / "build" / "bin" / "whisper-server",  # Legacy location
        Path.home() / ".voicemode" / "whisper.cpp" / "whisper-server",
        Path.home() / ".voicemode" / "whisper.cpp" / "server",
        Path("/usr/local/bin/whisper-server"),
        Path("/opt/homebrew/bin/whisper-server"),
    ]
    
    for path in paths_to_check:
        if path.exists() and path.is_file():
            return str(path)
    
    # Try to find in PATH
    result = subprocess.run(["which", "whisper-server"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    
    return None


def find_whisper_model() -> Optional[str]:
    """Find the active whisper model file based on VOICEMODE_WHISPER_MODEL setting."""
    from voice_mode.config import WHISPER_MODEL_PATH, WHISPER_MODEL
    
    # First try to find the specific model configured in VOICEMODE_WHISPER_MODEL
    model_name = WHISPER_MODEL  # This reads from env/config
    model_filename = f"ggml-{model_name}.bin"
    
    # Check configured model path
    model_dir = Path(WHISPER_MODEL_PATH)
    if model_dir.exists():
        specific_model = model_dir / model_filename
        if specific_model.exists():
            return str(specific_model)
        
        # Fall back to any model if configured model not found
        for model_file in model_dir.glob("ggml-*.bin"):
            logger.warning(f"Configured model {model_name} not found, using {model_file.name}")
            return str(model_file)
    
    # Check default installation paths
    default_paths = [
        Path.home() / ".voicemode" / "services" / "whisper" / "models",
        Path.home() / ".voicemode" / "whisper.cpp" / "models"  # legacy path
    ]
    
    for default_path in default_paths:
        if default_path.exists():
            specific_model = default_path / model_filename
            if specific_model.exists():
                return str(specific_model)
            
            # Fall back to any model
            for model_file in default_path.glob("ggml-*.bin"):
                logger.warning(f"Configured model {model_name} not found, using {model_file.name}")
                return str(model_file)
    
    return None


async def download_whisper_model(
    model: str,
    models_dir: Union[str, Path],
    force_download: bool = False,
    skip_core_ml: bool = False
) -> Dict[str, Union[bool, str]]:
    """
    Download a single Whisper model.
    
    Args:
        model: Model name (e.g., 'large-v2', 'base.en')
        models_dir: Directory to download models to
        force_download: Re-download even if model exists
        skip_core_ml: Skip Core ML conversion even on Apple Silicon
        
    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = models_dir / f"ggml-{model}.bin"
    
    # Check if model already exists
    if model_path.exists() and not force_download:
        logger.info(f"Model {model} already exists at {model_path}")
        return {
            "success": True,
            "path": str(model_path),
            "message": "Model already exists"
        }
    
    # Download directly from Hugging Face with progress bar
    model_url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"

    logger.info(f"Downloading model: {model}")

    try:
        # Download with progress bar
        success = await download_with_progress_async(
            url=model_url,
            destination=model_path,
            description=f"Downloading Whisper model {model}"
        )

        if not success:
            return {
                "success": False,
                "error": f"Failed to download model {model}"
            }
        
        # Verify download
        if not model_path.exists():
            return {
                "success": False,
                "error": f"Model file not found after download: {model_path}"
            }
        
        # Initialize core_ml_result
        core_ml_result = None

        # Check for Core ML support on Apple Silicon (unless explicitly skipped)
        if platform.system() == "Darwin" and platform.machine() == "arm64" and not skip_core_ml:
            # Download pre-built Core ML model from Hugging Face
            # No Python dependencies or Xcode required!
            core_ml_result = await download_coreml_model(model, models_dir)
            if core_ml_result["success"]:
                logger.info(f"Core ML conversion completed for {model}")
            else:
                # Log appropriate level based on error category
                error_category = core_ml_result.get('error_category', 'unknown')
                if error_category in ['missing_pytorch', 'missing_coremltools', 'missing_whisper', 'missing_ane_transformers', 'missing_module']:
                    logger.info(f"Core ML conversion skipped - {core_ml_result.get('error', 'Missing dependencies')}. Whisper will use Metal acceleration.")
                else:
                    logger.warning(f"Core ML conversion failed ({error_category}): {core_ml_result.get('error', 'Unknown error')}")
        
        # Build response with appropriate status
        response = {
            "success": True,
            "path": str(model_path),
            "message": f"Model {model} downloaded successfully"
        }
        
        # Add Core ML status if attempted
        if core_ml_result:
            response["core_ml_status"] = core_ml_result
            response["acceleration"] = "coreml" if core_ml_result.get("success") else "metal"
        else:
            response["acceleration"] = "metal"
        
        return response
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to download model {model}: {e.stderr}")
        return {
            "success": False,
            "error": f"Download failed: {e.stderr}"
        }
    except Exception as e:
        logger.error(f"Error downloading model {model}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def download_coreml_model(
    model: str,
    models_dir: Union[str, Path]
) -> Dict[str, Union[bool, str]]:
    """
    Download pre-built Core ML model from Hugging Face.

    No Python dependencies or Xcode required - models are pre-compiled
    and ready to use on all Apple Silicon Macs.

    Args:
        model: Model name
        models_dir: Directory to download model to

    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    models_dir = Path(models_dir)
    coreml_dir = models_dir / f"ggml-{model}-encoder.mlmodelc"
    coreml_zip = models_dir / f"ggml-{model}-encoder.mlmodelc.zip"

    # Check if already exists
    if coreml_dir.exists():
        logger.info(f"Core ML model already exists for {model}")
        return {
            "success": True,
            "path": str(coreml_dir),
            "message": "Core ML model already exists"
        }

    # Construct Hugging Face URL
    coreml_url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}-encoder.mlmodelc.zip"

    logger.info(f"Downloading pre-built Core ML model for {model} from Hugging Face...")

    try:
        # Download with progress bar
        success = await download_with_progress_async(
            url=coreml_url,
            destination=coreml_zip,
            description=f"Downloading Core ML model for {model}"
        )

        if not success:
            return {
                "success": False,
                "error": "Failed to download Core ML model"
            }

        logger.info(f"Download complete. Extracting Core ML model...")

        # Extract the zip file
        shutil.unpack_archive(coreml_zip, models_dir, 'zip')

        # Handle large-v2 naming mismatch
        # The large-v2 zip contains "ggml-large-encoder.mlmodelc" instead of "ggml-large-v2-encoder.mlmodelc"
        if model == "large-v2" and not coreml_dir.exists():
            legacy_dir = models_dir / "ggml-large-encoder.mlmodelc"
            if legacy_dir.exists():
                logger.info(f"Fixing large-v2 naming: renaming {legacy_dir.name} to {coreml_dir.name}")
                shutil.move(str(legacy_dir), str(coreml_dir))

        # Clean up zip file
        coreml_zip.unlink()
        logger.info(f"Core ML model extracted to {coreml_dir}")

        # Verify extraction
        if not coreml_dir.exists():
            return {
                "success": False,
                "error": f"Extraction failed - {coreml_dir} not found after unpacking"
            }

        return {
            "success": True,
            "path": str(coreml_dir),
            "message": f"Core ML model downloaded and extracted for {model}"
        }

    except Exception as e:
        # Check if it's a 404 error (model not available)
        error_msg = str(e)
        if "404" in error_msg or "Not Found" in error_msg:
            logger.info(f"No pre-built Core ML model available for {model} (404)")
            return {
                "success": False,
                "error": f"No pre-built Core ML model available for {model}",
                "error_category": "not_available"
            }
        else:
            logger.error(f"Error downloading Core ML model: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_category": "download_failed"
            }


def get_available_models() -> List[str]:
    """Get list of available Whisper models."""
    return [
        "tiny", "tiny.en",
        "base", "base.en",
        "small", "small.en",
        "medium", "medium.en",
        "large-v1", "large-v2", "large-v3",
        "large-v3-turbo"
    ]