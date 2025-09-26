"""Installation tool for whisper.cpp"""

import os
import sys
import platform
import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
import asyncio
import aiohttp
try:
    from importlib.resources import files
except ImportError:
    # Python < 3.9 fallback
    from importlib_resources import files

from voice_mode.server import mcp
from voice_mode.config import SERVICE_AUTO_ENABLE
from voice_mode.utils.services.whisper_helpers import download_whisper_model
from voice_mode.utils.version_helpers import (
    get_git_tags, get_latest_stable_tag, get_current_version,
    checkout_version, is_version_installed
)
from voice_mode.utils.migration_helpers import auto_migrate_if_needed
from voice_mode.utils.gpu_detection import detect_gpu

logger = logging.getLogger("voice-mode")


async def update_whisper_service_files(
    install_dir: str,
    voicemode_dir: str,
    auto_enable: Optional[bool] = None
) -> Dict[str, Any]:
    """Update service files (plist/systemd) for whisper service.
    
    This function updates the service files without reinstalling whisper itself.
    It ensures paths are properly expanded and templates are up to date.
    
    Returns:
        Dict with success status and details about what was updated
    """
    system = platform.system()
    result = {"success": False, "updated": False}
    
    # Create bin directory if it doesn't exist
    bin_dir = os.path.join(install_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    
    # Create/update start script
    logger.info("Updating whisper-server start script...")
    
    # Load template script
    template_content = None
    source_template = Path(__file__).parent.parent.parent.parent / "templates" / "scripts" / "start-whisper-server.sh"
    if source_template.exists():
        logger.info(f"Loading template from source: {source_template}")
        template_content = source_template.read_text()
    else:
        try:
            template_resource = files("voice_mode.templates.scripts").joinpath("start-whisper-server.sh")
            template_content = template_resource.read_text()
            logger.info("Loaded template from package resources")
        except Exception as e:
            logger.warning(f"Failed to load template script: {e}. Using fallback inline script.")
    
    # Use fallback inline script if template not found
    if template_content is None:
        template_content = f"""#!/bin/bash

# Whisper Service Startup Script
# This script is used by both macOS (launchd) and Linux (systemd) to start the whisper service
# It sources the voicemode.env file to get configuration, especially VOICEMODE_WHISPER_MODEL

# Determine whisper directory (script is in bin/, whisper root is parent)
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
WHISPER_DIR="$(dirname "$SCRIPT_DIR")"

# Voicemode configuration directory
VOICEMODE_DIR="$HOME/.voicemode"
LOG_DIR="$VOICEMODE_DIR/logs/whisper"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file for this script (separate from whisper server logs)
STARTUP_LOG="$LOG_DIR/startup.log"

# Source voicemode configuration if it exists
if [ -f "$VOICEMODE_DIR/voicemode.env" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sourcing voicemode.env" >> "$STARTUP_LOG"
    source "$VOICEMODE_DIR/voicemode.env"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: voicemode.env not found" >> "$STARTUP_LOG"
fi

# Model selection with environment variable support
MODEL_NAME="${{VOICEMODE_WHISPER_MODEL:-base}}"
MODEL_PATH="$WHISPER_DIR/models/ggml-$MODEL_NAME.bin"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting whisper-server with model: $MODEL_NAME" >> "$STARTUP_LOG"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error: Model $MODEL_NAME not found at $MODEL_PATH" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Available models:" >> "$STARTUP_LOG"
    ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\\.bin$" >> "$STARTUP_LOG"
    
    # Try to find any available model as fallback
    FALLBACK_MODEL=$(ls -1 "$WHISPER_DIR/models/" 2>/dev/null | grep "^ggml-.*\\.bin$" | head -1)
    if [ -n "$FALLBACK_MODEL" ]; then
        MODEL_PATH="$WHISPER_DIR/models/$FALLBACK_MODEL"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using fallback model: $FALLBACK_MODEL" >> "$STARTUP_LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fatal: No whisper models found" >> "$STARTUP_LOG"
        exit 1
    fi
fi

# Port configuration (with environment variable support)
WHISPER_PORT="${{VOICEMODE_WHISPER_PORT:-2022}}"

# Determine server binary location
# Check new CMake build location first, then legacy location
if [ -f "$WHISPER_DIR/build/bin/whisper-server" ]; then
    SERVER_BIN="$WHISPER_DIR/build/bin/whisper-server"
elif [ -f "$WHISPER_DIR/server" ]; then
    SERVER_BIN="$WHISPER_DIR/server"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error: whisper-server binary not found" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checked: $WHISPER_DIR/build/bin/whisper-server" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checked: $WHISPER_DIR/server" >> "$STARTUP_LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using binary: $SERVER_BIN" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Model path: $MODEL_PATH" >> "$STARTUP_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port: $WHISPER_PORT" >> "$STARTUP_LOG"

# Start whisper-server
# Using exec to replace this script process with whisper-server
cd "$WHISPER_DIR"
exec "$SERVER_BIN" \\
    --host 0.0.0.0 \\
    --port "$WHISPER_PORT" \\
    --model "$MODEL_PATH" \\
    --inference-path /v1/audio/transcriptions \\
    --threads 8
"""
    
    start_script_path = os.path.join(bin_dir, "start-whisper-server.sh")
    with open(start_script_path, 'w') as f:
        f.write(template_content)
    os.chmod(start_script_path, 0o755)
    
    # Update service files based on platform
    if system == "Darwin":
        logger.info("Updating launchagent for whisper-server...")
        launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(launchagents_dir, exist_ok=True)
        
        # Create log directory
        log_dir = os.path.join(voicemode_dir, 'logs', 'whisper')
        os.makedirs(log_dir, exist_ok=True)
        
        plist_name = "com.voicemode.whisper.plist"
        plist_path = os.path.join(launchagents_dir, plist_name)
        
        # Load plist template
        source_template = Path(__file__).parent.parent.parent.parent / "templates" / "launchd" / "com.voicemode.whisper.plist"
        if source_template.exists():
            logger.info(f"Loading plist template from source: {source_template}")
            plist_content = source_template.read_text()
        else:
            template_resource = files("voice_mode.templates.launchd").joinpath("com.voicemode.whisper.plist")
            plist_content = template_resource.read_text()
            logger.info("Loaded plist template from package resources")
        
        # Replace placeholders with expanded paths
        plist_content = plist_content.replace("{START_SCRIPT_PATH}", start_script_path)
        plist_content = plist_content.replace("{LOG_DIR}", os.path.join(voicemode_dir, 'logs'))
        plist_content = plist_content.replace("{INSTALL_DIR}", install_dir)
        
        # Unload if already loaded (ignore errors)
        try:
            subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        except:
            pass
        
        # Write updated plist
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        result["success"] = True
        result["updated"] = True
        result["plist_path"] = plist_path
        result["start_script"] = start_script_path
        
        # Handle auto_enable if specified
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        if auto_enable:
            logger.info("Auto-enabling whisper service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("whisper")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False
    
    elif system == "Linux":
        logger.info("Updating systemd user service for whisper-server...")
        systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(systemd_user_dir, exist_ok=True)
        
        # Create log directory
        log_dir = os.path.join(voicemode_dir, 'logs', 'whisper')
        os.makedirs(log_dir, exist_ok=True)
        
        service_name = "voicemode-whisper.service"
        service_path = os.path.join(systemd_user_dir, service_name)
        
        service_content = f"""[Unit]
Description=Whisper.cpp Speech Recognition Server
After=network.target

[Service]
Type=simple
ExecStart={start_script_path}
Restart=on-failure
RestartSec=10
WorkingDirectory={install_dir}
StandardOutput=append:{os.path.join(voicemode_dir, 'logs', 'whisper', 'whisper.out.log')}
StandardError=append:{os.path.join(voicemode_dir, 'logs', 'whisper', 'whisper.err.log')}
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/cuda/bin"

[Install]
WantedBy=default.target
"""
        
        with open(service_path, 'w') as f:
            f.write(service_content)
        
        # Reload systemd
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            result["success"] = True
            result["updated"] = True
            result["service_path"] = service_path
            result["start_script"] = start_script_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to reload systemd: {e}")
            result["success"] = True  # Still consider it success if file was written
            result["updated"] = True
            result["service_path"] = service_path
            result["start_script"] = start_script_path
        
        # Handle auto_enable if specified
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        if auto_enable:
            logger.info("Auto-enabling whisper service...")
            from voice_mode.tools.service import enable_service
            enable_result = await enable_service("whisper")
            if "✅" in enable_result:
                result["enabled"] = True
            else:
                logger.warning(f"Auto-enable failed: {enable_result}")
                result["enabled"] = False
    
    else:
        result["success"] = False
        result["error"] = f"Unsupported platform: {system}"
    
    return result


@mcp.tool()
async def whisper_install(
    install_dir: Optional[str] = None,
    model: str = "base",
    use_gpu: Optional[Union[bool, str]] = None,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
    version: str = "latest"
) -> Dict[str, Any]:
    """
    Install whisper.cpp with automatic system detection and configuration.
    
    Supports macOS (with Metal) and Linux (with CUDA if available).
    
    Args:
        install_dir: Directory to install whisper.cpp (default: ~/.voicemode/whisper.cpp)
        model: Whisper model to download (tiny, base, small, medium, large-v2, large-v3, etc.)
               Default is base for good balance of speed and accuracy (142MB).
        use_gpu: Enable GPU support if available (default: auto-detect)
        force_reinstall: Force reinstallation even if already installed
        auto_enable: Enable service after install. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.
        version: Version to install (default: "latest" for latest stable release)
    
    Returns:
        Installation status with paths and configuration details
    """
    try:
        # Check for and migrate old installations
        migration_msg = auto_migrate_if_needed("whisper")
        
        # Set default install directory under ~/.voicemode
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "services", "whisper")
        else:
            install_dir = os.path.expanduser(install_dir)
        
        # Resolve version if "latest" is specified
        if version == "latest":
            tags = get_git_tags("https://github.com/ggerganov/whisper.cpp")
            if not tags:
                return {
                    "success": False,
                    "error": "Failed to fetch available versions"
                }
            version = get_latest_stable_tag(tags)
            if not version:
                return {
                    "success": False,
                    "error": "No stable versions found"
                }
            logger.info(f"Using latest stable version: {version}")
        
        # Check if already installed
        if os.path.exists(install_dir) and not force_reinstall:
            if os.path.exists(os.path.join(install_dir, "main")) or os.path.exists(os.path.join(install_dir, "build", "bin", "whisper-cli")):
                # Check if the requested version is already installed
                if is_version_installed(Path(install_dir), version):
                    current_version = get_current_version(Path(install_dir))
                    
                    # Always update service files even if whisper is already installed
                    logger.info("Whisper is already installed, updating service files...")
                    service_update_result = await update_whisper_service_files(
                        install_dir=install_dir,
                        voicemode_dir=voicemode_dir,
                        auto_enable=auto_enable
                    )
                    
                    model_path = os.path.join(install_dir, "models", f"ggml-{model}.bin")
                    
                    # Build response message
                    message = f"whisper.cpp version {current_version} already installed."
                    if service_update_result.get("updated"):
                        message += " Service files updated."
                    if service_update_result.get("enabled"):
                        message += " Service auto-enabled."
                    
                    return {
                        "success": True,
                        "install_path": install_dir,
                        "model_path": model_path,
                        "already_installed": True,
                        "service_files_updated": service_update_result.get("updated", False),
                        "version": current_version,
                        "plist_path": service_update_result.get("plist_path"),
                        "service_path": service_update_result.get("service_path"),
                        "start_script": service_update_result.get("start_script"),
                        "message": message
                    }
        
        # Detect system
        system = platform.system()
        is_macos = system == "Darwin"
        is_linux = system == "Linux"
        
        if not is_macos and not is_linux:
            return {
                "success": False,
                "error": f"Unsupported operating system: {system}"
            }
        
        # Auto-detect GPU if not specified
        if use_gpu is None:
            use_gpu, gpu_type = detect_gpu()
            logger.info(f"Auto-detected GPU: {gpu_type} (enabled: {use_gpu})")
        else:
            # User specified whether to use GPU
            if use_gpu:
                # Get the detected GPU type
                _, detected_type = detect_gpu()
                gpu_type = detected_type if detected_type != "cpu" else ("metal" if is_macos else "cuda")
            else:
                gpu_type = "cpu"
        
        logger.info(f"Installing whisper.cpp on {system} with {gpu_type} support")
        
        # Check prerequisites
        missing_deps = []
        
        if is_macos:
            # Check for Xcode Command Line Tools
            try:
                subprocess.run(["xcode-select", "-p"], capture_output=True, check=True)
            except:
                missing_deps.append("Xcode Command Line Tools (run: xcode-select --install)")
            
            # Check for Homebrew
            if not shutil.which("brew"):
                missing_deps.append("Homebrew (install from https://brew.sh)")
            
            # Check for cmake
            if not shutil.which("cmake"):
                # If homebrew is available, offer to install cmake automatically
                if shutil.which("brew"):
                    logger.info("cmake not found, attempting to install via homebrew...")
                    try:
                        subprocess.run(["brew", "install", "cmake"], check=True)
                        logger.info("Successfully installed cmake")
                    except subprocess.CalledProcessError:
                        missing_deps.append("cmake (failed to install, please run: brew install cmake)")
                else:
                    missing_deps.append("cmake (run: brew install cmake)")
        
        elif is_linux:
            # Check for build essentials
            if not shutil.which("gcc") or not shutil.which("make"):
                missing_deps.append("build-essential (run: sudo apt-get install build-essential)")
            
            if use_gpu and not shutil.which("nvcc"):
                missing_deps.append("CUDA toolkit (for GPU support)")
        
        if missing_deps:
            return {
                "success": False,
                "error": "Missing dependencies",
                "missing": missing_deps,
                "message": "Please install missing dependencies and try again"
            }
        
        # Remove existing installation if force_reinstall
        if force_reinstall and os.path.exists(install_dir):
            logger.info(f"Removing existing installation at {install_dir}")
            shutil.rmtree(install_dir)
        
        # Clone whisper.cpp if not exists
        if not os.path.exists(install_dir):
            logger.info(f"Cloning whisper.cpp repository (version {version})...")
            subprocess.run([
                "git", "clone", "https://github.com/ggerganov/whisper.cpp.git", install_dir
            ], check=True)
            # Checkout the specific version
            if not checkout_version(Path(install_dir), version):
                shutil.rmtree(install_dir)
                return {
                    "success": False,
                    "error": f"Failed to checkout version {version}"
                }
        else:
            logger.info(f"Using existing whisper.cpp directory, switching to version {version}...")
            # Clean any local changes and checkout the version
            subprocess.run(["git", "reset", "--hard"], cwd=install_dir, check=True)
            subprocess.run(["git", "clean", "-fd"], cwd=install_dir, check=True)
            if not checkout_version(Path(install_dir), version):
                return {
                    "success": False,
                    "error": f"Failed to checkout version {version}"
                }
        
        # Build whisper.cpp
        logger.info(f"Building whisper.cpp with {gpu_type} support...")
        original_dir = os.getcwd()
        os.chdir(install_dir)
        
        # Clean any previous build (only if Makefile exists)
        if os.path.exists("Makefile"):
            try:
                subprocess.run(["make", "clean"], check=True, 
                             capture_output=True, text=True)
            except subprocess.CalledProcessError:
                logger.warning("Make clean skipped (no previous build), continuing...")
        
        # Build with CMake for better control and Core ML support
        build_env = os.environ.copy()
        cmake_flags = []
        
        # Enable GPU support based on platform
        if is_macos:
            # On macOS, always enable Metal
            cmake_flags.append("-DGGML_METAL=ON")
            # On Apple Silicon, also enable Core ML for better performance
            if platform.machine() == "arm64":
                cmake_flags.append("-DWHISPER_COREML=ON")
                cmake_flags.append("-DWHISPER_COREML_ALLOW_FALLBACK=ON")
                logger.info("Enabling Core ML support with fallback for Apple Silicon")
        elif is_linux and use_gpu:
            cmake_flags.append("-DGGML_CUDA=ON")
        
        # Get number of CPU cores for parallel build
        cpu_count = os.cpu_count() or 4
        
        # Determine if we should show build output
        debug_mode = os.environ.get("VOICEMODE_DEBUG", "").lower() in ("true", "1", "yes")
        
        # Configure with CMake
        logger.info("Configuring whisper.cpp build...")
        cmake_cmd = ["cmake", "-B", "build"] + cmake_flags
        
        if debug_mode:
            subprocess.run(cmake_cmd, env=build_env, check=True)
        else:
            try:
                result = subprocess.run(cmake_cmd, env=build_env, 
                                      capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Configuration failed: {e}")
                if e.stderr:
                    logger.error(f"Configuration errors:\n{e.stderr}")
                raise
        
        # Build with CMake
        logger.info("Building whisper.cpp (this may take a few minutes)...")
        build_cmd = ["cmake", "--build", "build", "-j", str(cpu_count), "--config", "Release"]
        
        if debug_mode:
            subprocess.run(build_cmd, env=build_env, check=True)
        else:
            try:
                result = subprocess.run(build_cmd, env=build_env, 
                                      capture_output=True, text=True, check=True)
                logger.info("Build completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"Build failed: {e}")
                if e.stdout:
                    logger.error(f"Build output:\n{e.stdout}")
                if e.stderr:
                    logger.error(f"Build errors:\n{e.stderr}")
                raise
        
        # Note: whisper-server is now built as part of the main build target
        
        # Download model using shared helper
        logger.info(f"Downloading default model: {model}")
        models_dir = os.path.join(install_dir, "models")
        
        download_result = await download_whisper_model(
            model=model,
            models_dir=models_dir,
            force_download=False
        )
        
        if not download_result["success"]:
            return {
                "success": False,
                "error": f"Failed to download model: {download_result.get('error', 'Unknown error')}"
            }
        
        model_path = download_result["path"]
        
        # Test whisper with sample if available
        # With CMake build, binaries are in build/bin/
        main_path = os.path.join(install_dir, "build", "bin", "whisper-cli")
        sample_path = os.path.join(install_dir, "samples", "jfk.wav")
        if os.path.exists(sample_path) and os.path.exists(main_path):
            try:
                result = subprocess.run([
                    main_path, "-m", model_path, "-f", sample_path, "-np"
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    logger.warning(f"Test run failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning("Test run timed out")
        
        # Restore original directory
        if 'original_dir' in locals():
            os.chdir(original_dir)
        
        # Update service files (includes creating start script)
        logger.info("Installing/updating service files...")
        service_update_result = await update_whisper_service_files(
            install_dir=install_dir,
            voicemode_dir=voicemode_dir,
            auto_enable=auto_enable
        )
        
        if not service_update_result.get("success"):
            logger.error(f"Failed to update service files: {service_update_result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": f"Service file update failed: {service_update_result.get('error', 'Unknown error')}"
            }
        
        # Get the start script path from the result
        start_script_path = service_update_result.get("start_script")
        
        # Build return message based on results
        if system == "Darwin":
            current_version = get_current_version(Path(install_dir))
            enable_message = " Service auto-enabled." if service_update_result.get("enabled") else ""
            
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
                "version": current_version,
                "performance_info": {
                    "system": system,
                    "gpu_acceleration": gpu_type,
                    "model": model,
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main"),
                    "server_port": 2022,
                    "server_url": "http://localhost:2022"
                },
                "launchagent": service_update_result.get("plist_path"),
                "start_script": start_script_path,
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support and whisper-server on port 2022{enable_message}{' (' + migration_msg + ')' if migration_msg else ''}"
            }
        
        elif system == "Linux":
            current_version = get_current_version(Path(install_dir))
            enable_message = " Service auto-enabled." if service_update_result.get("enabled") else ""
            systemd_message = "Systemd service installed"
            
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
                "version": current_version,
                "performance_info": {
                    "system": system,
                    "gpu_acceleration": gpu_type,
                    "model": model,
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main"),
                    "server_port": 2022,
                    "server_url": "http://localhost:2022"
                },
                "systemd_service": service_update_result.get("service_path"),
                "systemd_enabled": service_update_result.get("enabled", False),
                "start_script": start_script_path,
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support. {systemd_message}{enable_message}{' (' + migration_msg + ')' if migration_msg else ''}"
            }
        
        else:
            current_version = get_current_version(Path(install_dir))
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
                "version": current_version,
                "performance_info": {
                    "system": system,
                    "gpu_acceleration": gpu_type,
                    "model": model,
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main")
                },
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support{enable_message}{' (' + migration_msg + ')' if migration_msg else ''}"
            }
        
    except subprocess.CalledProcessError as e:
        if 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Command failed: {e.cmd}",
            "stderr": e.stderr.decode() if e.stderr else None
        }
    except Exception as e:
        if 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": str(e)
        }