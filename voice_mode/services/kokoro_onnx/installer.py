"""Installation tool for kokoro-onnx TTS service."""

import os
import sys
import platform
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
import asyncio

from voice_mode.config import (
    SERVICE_AUTO_ENABLE,
    KOKORO_ONNX_MODEL,
    KOKORO_ONNX_VOICES,
    MODELS_DIR,
)

logger = logging.getLogger("voicemode")

# Model download URLs from kokoro-onnx releases
MODEL_URLS = {
    "kokoro-v1.0.int8.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "kokoro-v1.0.fp16.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx",
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


async def download_file(url: str, dest: Path) -> bool:
    """Download a file from URL to destination."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                    return True
                else:
                    logger.error(f"Failed to download {url}: HTTP {response.status}")
                    return False
    except ImportError:
        # Fallback to curl if aiohttp not available
        try:
            result = subprocess.run(
                ["curl", "-L", "-o", str(dest), url],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


async def check_python_deps() -> Dict[str, bool]:
    """Check if required Python packages are installed."""
    deps = {
        "kokoro_onnx": False,
        "fastapi": False,
        "uvicorn": False,
    }

    for pkg in deps:
        try:
            __import__(pkg)
            deps[pkg] = True
        except ImportError:
            deps[pkg] = False

    return deps


async def install_python_deps() -> bool:
    """Install required Python packages."""
    try:
        # Try uv first, then pip
        packages = ["kokoro-onnx", "fastapi", "uvicorn"]

        # Check if uv is available
        uv_available = subprocess.run(
            ["uv", "--version"],
            capture_output=True
        ).returncode == 0

        if uv_available:
            cmd = ["uv", "pip", "install"] + packages
        else:
            cmd = [sys.executable, "-m", "pip", "install"] + packages

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Failed to install dependencies: {result.stderr}")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False


async def kokoro_onnx_install(
    models_dir: Optional[str] = None,
    model: Optional[str] = None,
    force_reinstall: bool = False,
    auto_enable: Optional[bool] = None,
    download_models: bool = True,
) -> Dict[str, Any]:
    """
    Install kokoro-onnx TTS service.

    Downloads model files and installs Python dependencies.

    Args:
        models_dir: Directory for model files (default: ~/.voicemode/models)
        model: Model file to download (default: kokoro-v1.0.int8.onnx)
        force_reinstall: Force re-download of models
        auto_enable: Enable service after install
        download_models: Whether to download model files

    Returns:
        Installation status with details
    """
    result = {
        "success": False,
        "models_dir": None,
        "model": None,
        "voices": None,
        "deps_installed": False,
    }

    try:
        # Set default directories
        if models_dir is None:
            models_dir = os.path.expanduser(MODELS_DIR)
        else:
            models_dir = os.path.expanduser(models_dir)

        if model is None:
            model = KOKORO_ONNX_MODEL

        voices = KOKORO_ONNX_VOICES

        result["models_dir"] = models_dir
        result["model"] = model
        result["voices"] = voices

        # Check Python dependencies
        deps = await check_python_deps()
        missing = [pkg for pkg, installed in deps.items() if not installed]

        if missing:
            logger.info(f"Installing missing dependencies: {', '.join(missing)}")
            if await install_python_deps():
                result["deps_installed"] = True
                logger.info("Dependencies installed successfully")
            else:
                result["error"] = "Failed to install Python dependencies"
                return result
        else:
            logger.info("All Python dependencies already installed")
            result["deps_installed"] = True

        # Download model files
        if download_models:
            models_path = Path(models_dir)
            models_path.mkdir(parents=True, exist_ok=True)

            # Download model file
            model_path = models_path / model
            if not model_path.exists() or force_reinstall:
                if model in MODEL_URLS:
                    logger.info(f"Downloading model: {model}")
                    if not await download_file(MODEL_URLS[model], model_path):
                        result["error"] = f"Failed to download model: {model}"
                        return result
                    logger.info(f"Model downloaded: {model_path}")
                else:
                    logger.warning(f"Unknown model: {model}, skipping download")
            else:
                logger.info(f"Model already exists: {model_path}")

            # Download voices file
            voices_path = models_path / voices
            if not voices_path.exists() or force_reinstall:
                if voices in MODEL_URLS:
                    logger.info(f"Downloading voices: {voices}")
                    if not await download_file(MODEL_URLS[voices], voices_path):
                        result["error"] = f"Failed to download voices: {voices}"
                        return result
                    logger.info(f"Voices downloaded: {voices_path}")
                else:
                    logger.warning(f"Unknown voices file: {voices}, skipping download")
            else:
                logger.info(f"Voices already exist: {voices_path}")

        # Install start script
        from voice_mode.tools.service import install_kokoro_onnx_start_script
        script_result = await install_kokoro_onnx_start_script()
        if not script_result.get("success"):
            result["error"] = f"Failed to install start script: {script_result.get('error')}"
            return result
        result["start_script"] = script_result.get("start_script")

        # Handle auto_enable
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE

        if auto_enable:
            from voice_mode.tools.service import enable_service
            logger.info("Auto-enabling kokoro-onnx service...")
            enable_result = await enable_service("kokoro-onnx")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False

        result["success"] = True
        return result

    except Exception as e:
        logger.error(f"Installation failed: {e}")
        result["error"] = str(e)
        return result
