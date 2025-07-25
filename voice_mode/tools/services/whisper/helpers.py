"""Helper functions for whisper service management."""

import os
import subprocess
import platform
import logging
from pathlib import Path
from typing import Optional, List, Dict, Union

logger = logging.getLogger("voice-mode")

def find_whisper_server() -> Optional[str]:
    """Find the whisper-server binary."""
    # Check common installation paths
    paths_to_check = [
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
    """Find a whisper model file."""
    from voice_mode.config import WHISPER_MODEL_PATH
    
    # Check configured model path
    model_dir = Path(WHISPER_MODEL_PATH)
    if model_dir.exists():
        # Look for ggml model files
        for model_file in model_dir.glob("ggml-*.bin"):
            return str(model_file)
    
    # Check default installation path
    default_path = Path.home() / ".voicemode" / "whisper.cpp" / "models"
    if default_path.exists():
        for model_file in default_path.glob("ggml-*.bin"):
            return str(model_file)
    
    return None


async def download_whisper_model(
    model: str,
    models_dir: Union[str, Path],
    force_download: bool = False
) -> Dict[str, Union[bool, str]]:
    """
    Download a single Whisper model.
    
    Args:
        model: Model name (e.g., 'large-v2', 'base.en')
        models_dir: Directory to download models to
        force_download: Re-download even if model exists
        
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
    
    # Use the download script from whisper.cpp
    download_script = models_dir / "download-ggml-model.sh"
    
    if not download_script.exists():
        # Create the download script if it doesn't exist
        # This happens when downloading models to a custom directory
        whisper_dir = Path.home() / ".voicemode" / "whisper.cpp"
        original_script = whisper_dir / "models" / "download-ggml-model.sh"
        
        if original_script.exists():
            import shutil
            shutil.copy2(original_script, download_script)
            os.chmod(download_script, 0o755)
        else:
            # Check if we're in the whisper.cpp directory already
            # (happens during install when models_dir is install_dir/models)
            parent_script = models_dir.parent / "models" / "download-ggml-model.sh"
            if parent_script.exists() and parent_script != download_script:
                import shutil
                shutil.copy2(parent_script, download_script)
                os.chmod(download_script, 0o755)
            else:
                return {
                    "success": False,
                    "error": "Download script not found. Please run whisper_install first."
                }
    
    logger.info(f"Downloading model: {model}")
    
    try:
        # Run download script
        result = subprocess.run(
            ["bash", str(download_script), model],
            cwd=str(models_dir),
            capture_output=True,
            text=True,
            check=True
        )
        
        # Verify download
        if not model_path.exists():
            return {
                "success": False,
                "error": f"Model file not found after download: {model_path}"
            }
        
        # Check for Core ML support on Apple Silicon
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            core_ml_result = await convert_to_coreml(model, models_dir)
            if core_ml_result["success"]:
                logger.info(f"Core ML conversion completed for {model}")
            else:
                logger.warning(f"Core ML conversion failed: {core_ml_result.get('error')}")
        
        return {
            "success": True,
            "path": str(model_path),
            "message": f"Model {model} downloaded successfully"
        }
        
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


async def convert_to_coreml(
    model: str,
    models_dir: Union[str, Path]
) -> Dict[str, Union[bool, str]]:
    """
    Convert a Whisper model to Core ML format for Apple Silicon.
    
    Args:
        model: Model name
        models_dir: Directory containing the model
        
    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    models_dir = Path(models_dir)
    model_path = models_dir / f"ggml-{model}.bin"
    coreml_path = models_dir / f"ggml-{model}-encoder.mlmodelc"
    
    # Check if already converted
    if coreml_path.exists():
        logger.info(f"Core ML model already exists for {model}")
        return {
            "success": True,
            "path": str(coreml_path),
            "message": "Core ML model already exists"
        }
    
    # Find the Core ML conversion script
    whisper_dir = Path.home() / ".voicemode" / "whisper.cpp"
    convert_script = whisper_dir / "models" / "generate-coreml-model.sh"
    
    if not convert_script.exists():
        return {
            "success": False,
            "error": "Core ML conversion script not found"
        }
    
    logger.info(f"Converting {model} to Core ML format...")
    
    try:
        # Run conversion script
        result = subprocess.run(
            ["bash", str(convert_script), model],
            cwd=str(models_dir),
            capture_output=True,
            text=True,
            check=True
        )
        
        if coreml_path.exists():
            return {
                "success": True,
                "path": str(coreml_path),
                "message": f"Core ML model created for {model}"
            }
        else:
            return {
                "success": False,
                "error": "Core ML model not created"
            }
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Core ML conversion failed: {e.stderr}")
        return {
            "success": False,
            "error": f"Conversion failed: {e.stderr}"
        }
    except Exception as e:
        logger.error(f"Error during Core ML conversion: {e}")
        return {
            "success": False,
            "error": str(e)
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