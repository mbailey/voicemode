"""Installation tool for whisper.cpp"""

import os
import sys
import platform
import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
import aiohttp

from voice_mode.server import mcp
from voice_mode.config import SERVICE_AUTO_ENABLE
from .helpers import download_whisper_model
from ..version_helpers import (
    get_git_tags, get_latest_stable_tag, get_current_version,
    checkout_version, is_version_installed
)

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_install(
    install_dir: Optional[str] = None,
    model: str = "large-v2",
    use_gpu: Optional[bool] = None,
    force_reinstall: bool = False,
    auto_enable: Optional[bool] = None,
    version: str = "latest"
) -> Dict[str, Any]:
    """
    Install whisper.cpp with automatic system detection and configuration.
    
    Supports macOS (with Metal) and Linux (with CUDA if available).
    
    Args:
        install_dir: Directory to install whisper.cpp (default: ~/.voicemode/whisper.cpp)
        model: Whisper model to download (tiny, base, small, medium, large-v2, large-v3, etc.)
               Default is large-v2 for best accuracy. Note: large models require ~3GB RAM.
        use_gpu: Enable GPU support if available (default: auto-detect)
        force_reinstall: Force reinstallation even if already installed
        auto_enable: Enable service after install. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.
        version: Version to install (default: "latest" for latest stable release)
    
    Returns:
        Installation status with paths and configuration details
    """
    try:
        # Set default install directory under ~/.voicemode
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "whisper.cpp")
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
            if os.path.exists(os.path.join(install_dir, "main")):
                # Check if the requested version is already installed
                if is_version_installed(Path(install_dir), version):
                    current_version = get_current_version(Path(install_dir))
                    return {
                        "success": True,
                        "install_path": install_dir,
                        "model_path": os.path.join(install_dir, "models", f"ggml-{model}.bin"),
                        "already_installed": True,
                        "version": current_version,
                        "message": f"whisper.cpp version {current_version} already installed. Use force_reinstall=True to reinstall."
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
            if is_macos:
                # macOS always has Metal support
                use_gpu = True
                gpu_type = "metal"
            else:
                # Check for NVIDIA GPU on Linux
                try:
                    subprocess.run(["nvidia-smi"], capture_output=True, check=True)
                    use_gpu = True
                    gpu_type = "cuda"
                except:
                    use_gpu = False
                    gpu_type = "cpu"
        else:
            gpu_type = "metal" if is_macos and use_gpu else ("cuda" if is_linux and use_gpu else "cpu")
        
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
                subprocess.run(["make", "clean"], check=True)
            except subprocess.CalledProcessError:
                logger.warning("Make clean failed, continuing anyway...")
        
        # Build with appropriate flags
        build_env = os.environ.copy()
        
        if is_macos and use_gpu:
            build_env["WHISPER_METAL"] = "1"
        elif is_linux and use_gpu:
            build_env["WHISPER_CUDA"] = "1"
        
        # Get number of CPU cores for parallel build
        cpu_count = os.cpu_count() or 4
        
        subprocess.run(["make", f"-j{cpu_count}"], env=build_env, check=True)
        
        # Also build the server binary
        logger.info("Building whisper-server...")
        try:
            subprocess.run(["make", "server"], env=build_env, check=True)
        except subprocess.CalledProcessError:
            logger.warning("Failed to build whisper-server, it may not be available in this version")
        
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
        main_path = os.path.join(install_dir, "main")
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
        
        # Create start script for whisper-server
        logger.info("Creating whisper-server start script...")
        start_script_content = f"""#!/bin/bash

# Configuration
WHISPER_DIR="{install_dir}"
LOG_FILE="{os.path.join(voicemode_dir, 'whisper-server.log')}"

# Model selection with environment variable support
MODEL_NAME="${{VOICEMODE_WHISPER_MODEL:-{model}}}"
MODEL_PATH="$WHISPER_DIR/models/ggml-$MODEL_NAME.bin"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "Error: Model $MODEL_NAME not found at $MODEL_PATH" >> "$LOG_FILE"
    echo "Available models:" >> "$LOG_FILE"
    ls -1 "$WHISPER_DIR/models/" | grep "^ggml-.*\\.bin$" >> "$LOG_FILE"
    exit 1
fi

echo "Starting whisper-server with model: $MODEL_NAME" >> "$LOG_FILE"

# Check if whisper-server exists (it's in newer versions)
if [ ! -f "$WHISPER_DIR/build/bin/whisper-server" ] && [ ! -f "$WHISPER_DIR/server" ]; then
    echo "Building whisper-server..." >> "$LOG_FILE"
    cd "$WHISPER_DIR"
    make server >> "$LOG_FILE" 2>&1
fi

# Determine server binary location
if [ -f "$WHISPER_DIR/build/bin/whisper-server" ]; then
    SERVER_BIN="$WHISPER_DIR/build/bin/whisper-server"
elif [ -f "$WHISPER_DIR/server" ]; then
    SERVER_BIN="$WHISPER_DIR/server"
else
    echo "Error: whisper-server binary not found" >> "$LOG_FILE"
    exit 1
fi

# Start whisper-server
cd "$WHISPER_DIR"
exec "$SERVER_BIN" \\
    --model "$MODEL_PATH" \\
    --host 0.0.0.0 \\
    --port 2022 \\
    --inference-path /v1/audio/transcriptions \\
    --threads 8 \\
    >> "$LOG_FILE" 2>&1
"""
        
        start_script_path = os.path.join(install_dir, "start-whisper-server.sh")
        with open(start_script_path, 'w') as f:
            f.write(start_script_content)
        os.chmod(start_script_path, 0o755)
        
        # Install launchagent on macOS
        if system == "Darwin":
            logger.info("Installing launchagent for whisper-server...")
            launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launchagents_dir, exist_ok=True)
            
            plist_name = "com.voicemode.whisper.plist"
            plist_path = os.path.join(launchagents_dir, plist_name)
            
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.whisper</string>
    <key>ProgramArguments</key>
    <array>
        <string>{start_script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{install_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'whisper.out.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, 'logs', 'whisper.err.log')}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>"""
            
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            
            # Load the launchagent
            try:
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
            except:
                pass  # Ignore if not loaded
            
            subprocess.run(["launchctl", "load", plist_path], check=True)
            
            # Handle auto_enable
            enable_message = ""
            if auto_enable is None:
                auto_enable = SERVICE_AUTO_ENABLE
            
            if auto_enable:
                logger.info("Auto-enabling whisper service...")
                from voice_mode.tools.service import service
                enable_result = await service("whisper", "enable")
                if "✅" in enable_result:
                    enable_message = " Service auto-enabled."
                else:
                    logger.warning(f"Auto-enable failed: {enable_result}")
            
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
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main"),
                    "server_port": 2022,
                    "server_url": "http://localhost:2022"
                },
                "launchagent": plist_path,
                "start_script": start_script_path,
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support and whisper-server on port 2022{enable_message}"
            }
        
        # Install systemd service on Linux
        elif system == "Linux":
            logger.info("Installing systemd user service for whisper-server...")
            systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(systemd_user_dir, exist_ok=True)
            
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
StandardOutput=append:{os.path.join(voicemode_dir, 'logs', 'whisper.out.log')}
StandardError=append:{os.path.join(voicemode_dir, 'logs', 'whisper.err.log')}
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/cuda/bin"
Environment="VOICEMODE_WHISPER_MODEL={model}"

[Install]
WantedBy=default.target
"""
            
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd and enable service
            try:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
                subprocess.run(["systemctl", "--user", "start", service_name], check=True)
                
                systemd_enabled = True
                systemd_message = "Systemd service installed and started"
            except subprocess.CalledProcessError as e:
                systemd_enabled = False
                systemd_message = f"Systemd service created but not started: {e}"
                logger.warning(systemd_message)
            
            # Handle auto_enable
            enable_message = ""
            if auto_enable is None:
                auto_enable = SERVICE_AUTO_ENABLE
            
            if auto_enable:
                logger.info("Auto-enabling whisper service...")
                from voice_mode.tools.service import service
                enable_result = await service("whisper", "enable")
                if "✅" in enable_result:
                    enable_message = " Service auto-enabled."
                else:
                    logger.warning(f"Auto-enable failed: {enable_result}")
            
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
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main"),
                    "server_port": 2022,
                    "server_url": "http://localhost:2022"
                },
                "systemd_service": service_path,
                "systemd_enabled": systemd_enabled,
                "start_script": start_script_path,
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support. {systemd_message}{enable_message}"
            }
        
        else:
            # Handle auto_enable for other systems (if we add Windows support later)
            enable_message = ""
            if auto_enable is None:
                auto_enable = SERVICE_AUTO_ENABLE
            
            if auto_enable:
                logger.info("Auto-enable not supported on this platform")
            
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
                "message": f"Successfully installed whisper.cpp {current_version} with {gpu_type} support{enable_message}"
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