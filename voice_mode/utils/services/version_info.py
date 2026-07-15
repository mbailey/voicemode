"""Version information tools for voice services.

These are CLI helper functions, not MCP tools. The @mcp.tool() decorators
were removed because:
1. This module is in utils/services/, not tools/, so they weren't auto-loaded
2. Importing server.py triggers tools/__init__.py which imports converse.py
   which imports pydub, causing audioop deprecation warnings for simple CLI commands
"""

import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from voice_mode.config import BASE_DIR
from voice_mode.utils.services.whisper_helpers import find_whisper_server
from voice_mode.utils.services.kokoro_helpers import find_kokoro_fastapi
from voice_mode.utils.services.common import find_process_by_port
from voice_mode.utils.version_helpers import get_current_version

logger = logging.getLogger("voicemode")


def get_whisper_version() -> Dict[str, Any]:
    """Get Whisper installation and version information."""
    info = {
        "installed": False,
        "version": None,
        "binary_path": None,
        "build_info": None,
        "model_info": {},
        "running": False,
        "error": None
    }
    
    try:
        # Check if whisper is installed
        whisper_bin = find_whisper_server()
        if not whisper_bin:
            # Try to find main whisper binary as fallback
            whisper_main = BASE_DIR / "whisper.cpp" / "main"
            if whisper_main.exists():
                whisper_bin = str(whisper_main)
        
        if whisper_bin:
            info["installed"] = True
            info["binary_path"] = whisper_bin
            
            # Try to get version from whisper binary
            try:
                # whisper.cpp doesn't have a --version flag, but we can check git info
                whisper_dir = BASE_DIR / "whisper.cpp"
                if whisper_dir.exists():
                    # Get version using version helper
                    version = get_current_version(whisper_dir)
                    if version:
                        info["version"] = version
                    
                    # Get build info from CMakeCache if available
                    cmake_cache = whisper_dir / "build" / "CMakeCache.txt"
                    if cmake_cache.exists():
                        build_info = {}
                        with open(cmake_cache) as f:
                            for line in f:
                                if "CMAKE_BUILD_TYPE" in line:
                                    build_info["build_type"] = line.split("=")[1].strip()
                                elif "WHISPER_METAL" in line:
                                    build_info["metal_enabled"] = "ON" in line
                                elif "WHISPER_CUDA" in line:
                                    build_info["cuda_enabled"] = "ON" in line
                        info["build_info"] = build_info
            except Exception as e:
                logger.debug(f"Could not get whisper version info: {e}")
            
            # Check available models
            models_dir = whisper_dir / "models" if whisper_dir else None
            if models_dir and models_dir.exists():
                models = []
                for model_file in models_dir.glob("ggml-*.bin"):
                    model_info = {
                        "name": model_file.name,
                        "size_mb": model_file.stat().st_size / (1024 * 1024),
                        "modified": datetime.fromtimestamp(model_file.stat().st_mtime).isoformat()
                    }
                    models.append(model_info)
                info["model_info"]["models"] = models
                info["model_info"]["count"] = len(models)
        
        # Check if running
        proc = find_process_by_port(2022)
        if proc:
            info["running"] = True
            info["pid"] = proc.pid
            try:
                info["uptime_seconds"] = int(proc.create_time())
            except:
                pass
                
    except Exception as e:
        info["error"] = str(e)
        logger.error(f"Error getting whisper version info: {e}")
    
    return info


def get_kokoro_version() -> Dict[str, Any]:
    """Get Kokoro installation and version information."""
    info = {
        "installed": False,
        "version": None,
        "installation_path": None,
        "api_version": None,
        "models_info": {},
        "running": False,
        "error": None
    }
    
    try:
        # Check if kokoro is installed
        kokoro_dir = find_kokoro_fastapi()
        if kokoro_dir:
            info["installed"] = True
            info["installation_path"] = kokoro_dir
            
            # Try to get version from git
            try:
                version = get_current_version(Path(kokoro_dir))
                if version:
                    info["version"] = version
            except:
                pass
            
            # Check if running and get API version
            proc = find_process_by_port(8880)
            if proc:
                info["running"] = True
                info["pid"] = proc.pid
                try:
                    info["uptime_seconds"] = int(proc.create_time())
                except:
                    pass
                
                # Try to get version from API
                try:
                    import httpx
                    response = httpx.get("http://localhost:8880/", timeout=2.0)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict):
                            info["api_version"] = data.get("version", "unknown")
                            # Extract other useful info
                            if "models" in data:
                                info["models_info"]["available_models"] = data["models"]
                except Exception as e:
                    logger.debug(f"Could not get Kokoro API info: {e}")
            
            # Check for models
            models_dir = Path(kokoro_dir) / "models"
            if not models_dir.exists():
                # Check alternative location
                models_dir = BASE_DIR / "kokoro-models"
            
            if models_dir.exists():
                model_files = list(models_dir.glob("*.onnx")) + list(models_dir.glob("*.bin"))
                info["models_info"]["count"] = len(model_files)
                info["models_info"]["total_size_mb"] = sum(f.stat().st_size for f in model_files) / (1024 * 1024)
                
    except Exception as e:
        info["error"] = str(e)
        logger.error(f"Error getting kokoro version info: {e}")
    
    return info
