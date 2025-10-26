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


async def convert_to_coreml(
    model: str,
    models_dir: Union[str, Path]
) -> Dict[str, Union[bool, str]]:
    """
    DEPRECATED: Use download_coreml_model instead.

    This function is kept for backward compatibility but now just
    calls download_coreml_model to get pre-built models from Hugging Face.

    Args:
        model: Model name
        models_dir: Directory containing the model

    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    logger.info(f"convert_to_coreml is deprecated - using download_coreml_model instead")
    return await download_coreml_model(model, models_dir)


async def convert_to_coreml_legacy(
    model: str,
    models_dir: Union[str, Path]
) -> Dict[str, Union[bool, str]]:
    """
    Legacy Core ML conversion that builds models locally.
    Kept for reference but should not be used.

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
    # Try new location first, then fall back to old location
    whisper_dir = Path.home() / ".voicemode" / "services" / "whisper"
    if not whisper_dir.exists():
        whisper_dir = Path.home() / ".voicemode" / "whisper.cpp"
    
    # Use the uv wrapper script if it exists, otherwise fallback to original
    convert_script = whisper_dir / "models" / "generate-coreml-model-uv.sh"
    if not convert_script.exists():
        convert_script = whisper_dir / "models" / "generate-coreml-model.sh"
    
    if not convert_script.exists():
        return {
            "success": False,
            "error": f"Core ML conversion script not found at {convert_script}"
        }
    
    logger.info(f"Converting {model} to Core ML format...")
    
    try:
        # Legacy conversion - now deprecated in favor of pre-built models
        # This code path should not be used anymore
        logger.warning("Legacy Core ML conversion attempted - use download_coreml_model instead")

        # Try to find existing Python with Core ML deps (legacy)
        coreml_python = None
        venv_coreml_python = whisper_dir / "venv-coreml" / "bin" / "python"
        if venv_coreml_python.exists():
            try:
                result = subprocess.run(
                    [str(venv_coreml_python), "-c", "import torch, coremltools"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    coreml_python = str(venv_coreml_python)
            except:
                pass

        if coreml_python:
            # Use the CoreML-enabled Python environment
            logger.info(f"Using CoreML Python environment: {coreml_python}")
            script_path = whisper_dir / "models" / "convert-whisper-to-coreml.py"
            result = subprocess.run(
                [coreml_python, str(script_path),
                 "--model", model, "--encoder-only", "True", "--optimize-ane", "True"],
                cwd=str(whisper_dir / "models"),
                capture_output=True,
                text=True,
                check=True
            )
            
            # Now compile the mlpackage to mlmodelc using coremlc
            mlpackage_path = models_dir / f"coreml-encoder-{model}.mlpackage"
            if mlpackage_path.exists():
                logger.info(f"Compiling Core ML model with coremlc...")
                compile_result = subprocess.run(
                    ["xcrun", "coremlc", "compile", str(mlpackage_path), str(models_dir)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Move the compiled model to the correct name
                compiled_path = models_dir / f"coreml-encoder-{model}.mlmodelc"
                if compiled_path.exists():
                    shutil.rmtree(coreml_path, ignore_errors=True)
                    shutil.move(str(compiled_path), str(coreml_path))
        else:
            # No suitable Python environment available
            logger.warning("No suitable Python environment for CoreML conversion")
            # Run from the whisper models directory where the script is located
            script_dir = convert_script.parent
            result = subprocess.run(
                ["bash", str(convert_script), model],
                cwd=str(script_dir),
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
        error_text = e.stderr if e.stderr else ""
        stdout_text = e.stdout if e.stdout else ""
        # Combine both for error detection since Python errors can appear in either
        combined_output = error_text + stdout_text
        
        # Enhanced error detection with specific categories
        error_details = {
            "success": False,
            "error_type": "subprocess_error",
            "return_code": e.returncode,
            "command": " ".join(e.cmd) if hasattr(e, 'cmd') else "conversion script",
        }
        
        # Detect specific missing dependencies
        if "ModuleNotFoundError" in combined_output:
            if "torch" in combined_output:
                error_details.update({
                    "error_category": "missing_pytorch",
                    "error": "PyTorch not installed - required for Core ML conversion",
                    "install_command": "uv pip install torch",
                    "manual_install": "pip install torch",
                    "package_size": "~2.5GB"
                })
            elif "coremltools" in combined_output:
                error_details.update({
                    "error_category": "missing_coremltools",
                    "error": "CoreMLTools not installed",
                    "install_command": "uv pip install coremltools",
                    "manual_install": "pip install coremltools",
                    "package_size": "~50MB"
                })
            elif "whisper" in combined_output:
                error_details.update({
                    "error_category": "missing_whisper",
                    "error": "OpenAI Whisper package not installed",
                    "install_command": "uv pip install openai-whisper",
                    "manual_install": "pip install openai-whisper",
                    "package_size": "~100MB"
                })
            elif "ane_transformers" in combined_output:
                error_details.update({
                    "error_category": "missing_ane_transformers",
                    "error": "ANE Transformers not installed for Apple Neural Engine optimization",
                    "install_command": "uv pip install ane_transformers",
                    "manual_install": "pip install ane_transformers",
                    "package_size": "~10MB"
                })
            else:
                # Generic module not found
                module_match = re.search(r"No module named '([^']+)'", combined_output)
                module_name = module_match.group(1) if module_match else "unknown"
                error_details.update({
                    "error_category": "missing_module",
                    "error": f"Python module '{module_name}' not installed",
                    "install_command": f"uv pip install {module_name}",
                    "manual_install": f"pip install {module_name}"
                })
        elif "xcrun: error" in combined_output and "coremlc" in combined_output:
            error_details.update({
                "error_category": "missing_coremlc",
                "error": "Core ML compiler (coremlc) not found - requires full Xcode installation",
                "install_command": "Install Xcode from Mac App Store",
                "note": "Command Line Tools alone are insufficient. Full Xcode provides coremlc for Core ML compilation.",
                "alternative": "Models will work with Metal acceleration without Core ML compilation"
            })
        elif "xcrun: error" in combined_output:
            error_details.update({
                "error_category": "missing_xcode_tools",
                "error": "Xcode Command Line Tools not installed or xcrun not available",
                "install_command": "xcode-select --install",
                "note": "Requires Xcode Command Line Tools"
            })
        elif "timeout" in combined_output.lower():
            error_details.update({
                "error_category": "conversion_timeout",
                "error": "Core ML conversion timed out",
                "suggestion": "Try with a smaller model or increase timeout"
            })
        else:
            # Generic conversion failure
            error_details.update({
                "error_category": "conversion_failure",
                "error": f"Core ML conversion failed",
                "stderr": error_text[:500] if error_text else None,  # Truncate long errors
                "stdout": stdout_text[:500] if stdout_text else None
            })
        
        logger.error(f"Core ML conversion failed - Category: {error_details.get('error_category', 'unknown')}, Error: {error_text[:200]}")
        return error_details
        
    except subprocess.TimeoutExpired as e:
        logger.error(f"Core ML conversion timed out after {e.timeout} seconds")
        return {
            "success": False,
            "error_category": "timeout",
            "error": f"Core ML conversion timed out after {e.timeout} seconds",
            "suggestion": "Model conversion is taking too long. Try again or use a smaller model."
        }
    except Exception as e:
        logger.error(f"Unexpected error during Core ML conversion: {e}")
        return {
            "success": False,
            "error_category": "unexpected_error",
            "error": str(e),
            "error_type": type(e).__name__
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