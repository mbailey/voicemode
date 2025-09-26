"""Whisper model registry and utilities."""

import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict
from voice_mode.config import WHISPER_MODEL_PATH, WHISPER_MODEL


class ModelInfo(TypedDict):
    """Information about a Whisper model."""
    size_mb: int  # Download size in MB
    languages: str  # Language support description
    description: str  # Brief description
    filename: str  # Expected filename when downloaded


# Registry of all available Whisper models
WHISPER_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "tiny": {
        "size_mb": 39,
        "languages": "Multilingual",
        "description": "Fastest, least accurate",
        "filename": "ggml-tiny.bin"
    },
    "tiny.en": {
        "size_mb": 39,
        "languages": "English only",
        "description": "Fastest English model",
        "filename": "ggml-tiny.en.bin"
    },
    "base": {
        "size_mb": 142,
        "languages": "Multilingual",
        "description": "Good balance of speed and accuracy",
        "filename": "ggml-base.bin"
    },
    "base.en": {
        "size_mb": 142,
        "languages": "English only",
        "description": "Good English model",
        "filename": "ggml-base.en.bin"
    },
    "small": {
        "size_mb": 466,
        "languages": "Multilingual",
        "description": "Better accuracy, slower",
        "filename": "ggml-small.bin"
    },
    "small.en": {
        "size_mb": 466,
        "languages": "English only",
        "description": "Better English accuracy",
        "filename": "ggml-small.en.bin"
    },
    "medium": {
        "size_mb": 1500,
        "languages": "Multilingual",
        "description": "High accuracy, slow",
        "filename": "ggml-medium.bin"
    },
    "medium.en": {
        "size_mb": 1500,
        "languages": "English only",
        "description": "High English accuracy",
        "filename": "ggml-medium.en.bin"
    },
    "large-v1": {
        "size_mb": 2900,
        "languages": "Multilingual",
        "description": "Original large model",
        "filename": "ggml-large-v1.bin"
    },
    "large-v2": {
        "size_mb": 2900,
        "languages": "Multilingual",
        "description": "Improved large model (recommended)",
        "filename": "ggml-large-v2.bin"
    },
    "large-v3": {
        "size_mb": 3100,
        "languages": "Multilingual",
        "description": "Latest large model",
        "filename": "ggml-large-v3.bin"
    },
    "large-v3-turbo": {
        "size_mb": 1600,
        "languages": "Multilingual",
        "description": "Faster large model with good accuracy",
        "filename": "ggml-large-v3-turbo.bin"
    }
}


def get_model_directory() -> Path:
    """Get the directory where Whisper models are stored."""
    # Use the configured path from config.py
    model_dir = Path(WHISPER_MODEL_PATH)
    
    # If config path doesn't exist, check service installation
    if not model_dir.exists():
        service_models = Path.home() / ".voicemode" / "services" / "whisper" / "models"
        if service_models.exists():
            return service_models
    
    return model_dir


def get_active_model() -> str:
    """Get the currently selected Whisper model."""
    # Use the configured model from config.py
    model = WHISPER_MODEL
    
    # Validate it's a known model
    if model not in WHISPER_MODEL_REGISTRY:
        return "base"  # Default fallback
    
    return model


def is_whisper_model_installed(model_name: str) -> bool:
    """Check if a Whisper model is installed."""
    if model_name not in WHISPER_MODEL_REGISTRY:
        return False
    
    model_dir = get_model_directory()
    model_info = WHISPER_MODEL_REGISTRY[model_name]
    model_path = model_dir / model_info["filename"]
    
    return model_path.exists()


def has_whisper_coreml_model(model_name: str) -> bool:
    """Check if a Core ML model is available for the given Whisper model.
    
    Core ML models are only used on macOS with Apple Silicon.
    They have the extension .mlmodelc and provide faster inference.
    """
    import platform
    
    # Core ML is only relevant on macOS
    if platform.system() != "Darwin":
        return False
    
    if model_name not in WHISPER_MODEL_REGISTRY:
        return False
    
    model_dir = get_model_directory()
    model_info = WHISPER_MODEL_REGISTRY[model_name]
    
    # Core ML models can be either compiled (.mlmodelc) or package (.mlpackage)
    # Check for both formats
    coreml_compiled = model_dir / f"ggml-{model_name}-encoder.mlmodelc"
    coreml_package = model_dir / f"coreml-encoder-{model_name}.mlpackage"
    
    return coreml_compiled.exists() or coreml_package.exists()


def get_installed_whisper_models() -> List[str]:
    """Get list of installed Whisper models."""
    installed = []
    for model_name in WHISPER_MODEL_REGISTRY:
        if is_whisper_model_installed(model_name):
            installed.append(model_name)
    return installed


def get_total_size(models: Optional[List[str]] = None) -> int:
    """Get total size of models in MB.
    
    Args:
        models: List of model names. If None, uses all models.
    
    Returns:
        Total size in MB
    """
    if models is None:
        models = list(WHISPER_MODEL_REGISTRY.keys())
    
    total = 0
    for model in models:
        if model in WHISPER_MODEL_REGISTRY:
            total += WHISPER_MODEL_REGISTRY[model]["size_mb"]
    
    return total


def format_size(size_mb: int) -> str:
    """Format size in MB to human-readable string."""
    if size_mb < 1000:
        return f"{size_mb} MB"
    else:
        size_gb = size_mb / 1000
        return f"{size_gb:.1f} GB"


def is_macos() -> bool:
    """Check if running on macOS."""
    import platform
    return platform.system() == "Darwin"


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon (M1/M2/M3/M4)."""
    import platform
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def set_active_model(model_name: str) -> None:
    """Set the active Whisper model.
    
    Args:
        model_name: Name of the model to set as active
    
    Updates the voicemode.env configuration file for persistence.
    """
    from pathlib import Path
    import re
    
    # Configuration file path
    config_path = Path.home() / ".voicemode" / "voicemode.env"
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing configuration
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match = re.match(r'^([A-Z_]+)=(.*)$', line)
                if match:
                    key, value = match.groups()
                    value = value.strip('"').strip("'")
                    config[key] = value
    
    # Update the model
    config['VOICEMODE_WHISPER_MODEL'] = model_name
    
    # Write back to file, preserving structure
    lines = []
    updated_keys = set()
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    match = re.match(r'^([A-Z_]+)=', stripped)
                    if match:
                        key = match.group(1)
                        if key == 'VOICEMODE_WHISPER_MODEL':
                            lines.append(f"VOICEMODE_WHISPER_MODEL={model_name}\n")
                            updated_keys.add(key)
                        elif key in config:
                            lines.append(f"{key}={config[key]}\n")
                            updated_keys.add(key)
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
    
    # Add VOICEMODE_WHISPER_MODEL if it wasn't in the file
    if 'VOICEMODE_WHISPER_MODEL' not in updated_keys:
        if lines and not lines[-1].strip() == '':
            lines.append('\n')
        lines.append("# Whisper Configuration\n")
        lines.append(f"VOICEMODE_WHISPER_MODEL={model_name}\n")
    
    # Write the updated configuration
    with open(config_path, 'w') as f:
        f.writelines(lines)


def remove_whisper_model(model_name: str, remove_coreml: bool = True) -> Dict[str, Any]:
    """Remove a whisper model and optionally its Core ML version.
    
    Args:
        model_name: Name of the model to remove
        remove_coreml: Also remove Core ML version if it exists
        
    Returns:
        Dict with success status and space freed
    """
    model_dir = get_model_directory()
    
    if model_name not in WHISPER_MODEL_REGISTRY:
        return {"success": False, "error": f"Model {model_name} not recognized"}
    
    model_info = WHISPER_MODEL_REGISTRY[model_name]
    model_file = model_dir / model_info["filename"]
    
    if not model_file.exists():
        return {"success": False, "error": f"Model {model_name} not found"}
    
    space_freed = model_file.stat().st_size
    model_file.unlink()
    
    if remove_coreml and has_whisper_coreml_model(model_name):
        # Remove both possible Core ML formats
        coreml_compiled = model_dir / f"ggml-{model_name}-encoder.mlmodelc"
        coreml_package = model_dir / f"coreml-encoder-{model_name}.mlpackage"
        
        if coreml_compiled.exists():
            import shutil
            shutil.rmtree(coreml_compiled)
            # Estimate size since it's a directory
            space_freed += 100 * 1024 * 1024  # Approximate 100MB
            
        if coreml_package.exists():
            import shutil
            shutil.rmtree(coreml_package)
            space_freed += 100 * 1024 * 1024  # Approximate 100MB
    
    return {
        "success": True,
        "model": model_name,
        "space_freed": space_freed,
        "space_freed_mb": space_freed // (1024 * 1024)
    }


def benchmark_whisper_model(model_name: str, sample_file: Optional[str] = None) -> Dict[str, Any]:
    """Run performance benchmark on a whisper model.
    
    Args:
        model_name: Name of the model to benchmark
        sample_file: Optional audio file to use (defaults to JFK sample)
        
    Returns:
        Dict with benchmark results
    """
    import subprocess
    import re
    from pathlib import Path
    
    if not is_whisper_model_installed(model_name):
        return {
            "success": False,
            "error": f"Model {model_name} is not installed"
        }
    
    # Find whisper-cli binary
    whisper_bin = Path.home() / ".voicemode" / "services" / "whisper" / "build" / "bin" / "whisper-cli"
    if not whisper_bin.exists():
        return {
            "success": False,
            "error": "Whisper CLI not found. Please install whisper.cpp first."
        }
    
    # Use sample file or default JFK sample
    if sample_file is None:
        sample_file = Path.home() / ".voicemode" / "services" / "whisper" / "samples" / "jfk.wav"
        if not sample_file.exists():
            return {
                "success": False,
                "error": "Default sample file not found"
            }
    
    model_dir = get_model_directory()
    model_info = WHISPER_MODEL_REGISTRY[model_name]
    model_path = model_dir / model_info["filename"]
    
    # Run benchmark
    try:
        result = subprocess.run(
            [
                str(whisper_bin),
                "--model", str(model_path),
                "--file", str(sample_file),
                "--threads", "8",
                "--beam-size", "1"
            ],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Parse timing information
        output = result.stderr + result.stdout
        
        # Extract timings using regex
        encode_match = re.search(r'encode time\s*=\s*([\d.]+)\s*ms', output)
        total_match = re.search(r'total time\s*=\s*([\d.]+)\s*ms', output)
        load_match = re.search(r'load time\s*=\s*([\d.]+)\s*ms', output)
        
        encode_time = float(encode_match.group(1)) if encode_match else 0
        total_time = float(total_match.group(1)) if total_match else 0
        load_time = float(load_match.group(1)) if load_match else 0
        
        # Calculate real-time factor (11 seconds for JFK sample)
        rtf = 11000 / total_time if total_time > 0 else 0
        
        return {
            "success": True,
            "model": model_name,
            "load_time_ms": load_time,
            "encode_time_ms": encode_time,
            "total_time_ms": total_time,
            "real_time_factor": round(rtf, 1),
            "sample_duration_s": 11.0
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Benchmark timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Backwards compatibility - deprecated functions
def get_current_model() -> str:
    """DEPRECATED: Use get_active_model() instead."""
    warnings.warn(
        "get_current_model() is deprecated. Use get_active_model() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return get_active_model()


def set_current_model(model_name: str) -> None:
    """DEPRECATED: Use set_active_model() instead."""
    warnings.warn(
        "set_current_model() is deprecated. Use set_active_model() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return set_active_model(model_name)


def is_model_installed(model_name: str) -> bool:
    """DEPRECATED: Use is_whisper_model_installed() instead."""
    warnings.warn(
        "is_model_installed() is deprecated. Use is_whisper_model_installed() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return is_whisper_model_installed(model_name)


def get_installed_models() -> List[str]:
    """DEPRECATED: Use get_installed_whisper_models() instead."""
    warnings.warn(
        "get_installed_models() is deprecated. Use get_installed_whisper_models() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return get_installed_whisper_models()


def has_coreml_model(model_name: str) -> bool:
    """DEPRECATED: Use has_whisper_coreml_model() instead."""
    warnings.warn(
        "has_coreml_model() is deprecated. Use has_whisper_coreml_model() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return has_whisper_coreml_model(model_name)


# Also provide WHISPER_MODELS as alias for backwards compatibility
WHISPER_MODELS = WHISPER_MODEL_REGISTRY