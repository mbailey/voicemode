"""Version information tools for voice services."""

import subprocess
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from voice_mode.server import mcp
from voice_mode.config import BASE_DIR
from voice_mode.utils.services.whisper_helpers import find_whisper_server
from voice_mode.utils.services.kokoro_helpers import find_kokoro_fastapi
from voice_mode.utils.services.common import find_process_by_port
from voice_mode.utils.version_helpers import get_current_version

logger = logging.getLogger("voice-mode")


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


@mcp.tool()
async def service_version(
    service_name: Optional[str] = None
) -> Dict[str, Any]:
    """Get version information for voice services.
    
    Shows detailed version, installation, and runtime information for Whisper and/or Kokoro.
    
    Args:
        service_name: Specific service to check ("whisper" or "kokoro"). If not specified, checks both.
    
    Returns:
        Dictionary with version information for requested service(s)
    """
    result = {}
    
    if service_name is None or service_name == "whisper":
        result["whisper"] = get_whisper_version()
    
    if service_name is None or service_name == "kokoro":
        result["kokoro"] = get_kokoro_version()
    
    # Add voice-mode version info
    result["voice_mode"] = {
        "version": "2.15.0",  # This should ideally come from package metadata
        "config_dir": str(BASE_DIR),
        "service_files_version": get_service_files_version()
    }
    
    return result


def get_service_files_version() -> Dict[str, str]:
    """Get version info for service files."""
    versions_file = Path(__file__).parent.parent.parent / "data" / "versions.json"
    if versions_file.exists():
        try:
            with open(versions_file) as f:
                data = json.load(f)
                return data.get("service_files", {})
        except:
            pass
    return {}


@mcp.tool()
async def check_updates(
    service_name: Optional[str] = None
) -> Dict[str, Any]:
    """Check for available updates for voice services.
    
    Checks if newer versions are available for Whisper and/or Kokoro.
    
    Args:
        service_name: Specific service to check ("whisper" or "kokoro"). If not specified, checks both.
    
    Returns:
        Dictionary with update availability information
    """
    result = {}
    
    if service_name is None or service_name == "whisper":
        whisper_info = {
            "current_version": None,
            "latest_version": None,
            "update_available": False,
            "error": None
        }
        
        try:
            # Get current version
            version_info = get_whisper_version()
            if version_info["installed"] and version_info["version"]:
                whisper_info["current_version"] = version_info["version"]
            
            # Check latest from GitHub
            import httpx
            response = httpx.get(
                "https://api.github.com/repos/ggerganov/whisper.cpp/commits/master",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                latest_commit = data.get("sha", "")[:7]
                latest_message = data.get("commit", {}).get("message", "").split('\n')[0]
                whisper_info["latest_version"] = f"{latest_commit} {latest_message}"
                
                # Simple check if update available (if current version commit != latest)
                if whisper_info["current_version"] and latest_commit not in whisper_info["current_version"]:
                    whisper_info["update_available"] = True
                    
        except Exception as e:
            whisper_info["error"] = str(e)
        
        result["whisper"] = whisper_info
    
    if service_name is None or service_name == "kokoro":
        kokoro_info = {
            "current_version": None,
            "latest_version": None,
            "update_available": False,
            "error": None
        }
        
        try:
            # Get current version
            version_info = get_kokoro_version()
            if version_info["installed"] and version_info["version"]:
                kokoro_info["current_version"] = version_info["version"]
            
            # Check latest from GitHub
            import httpx
            response = httpx.get(
                "https://api.github.com/repos/remsky/Kokoro-FastAPI/commits/main",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                latest_commit = data.get("sha", "")[:7]
                latest_message = data.get("commit", {}).get("message", "").split('\n')[0]
                kokoro_info["latest_version"] = f"{latest_commit} {latest_message}"
                
                # Simple check if update available
                if kokoro_info["current_version"] and latest_commit not in kokoro_info["current_version"]:
                    kokoro_info["update_available"] = True
                    
        except Exception as e:
            kokoro_info["error"] = str(e)
        
        result["kokoro"] = kokoro_info
    
    return result