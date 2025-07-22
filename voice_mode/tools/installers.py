"""
Installation tools for whisper.cpp and kokoro-fastapi
"""
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

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def install_whisper_cpp(
    install_dir: Optional[str] = None,
    model: str = "large-v2",
    use_gpu: Optional[bool] = None,
    force_reinstall: bool = False
) -> Dict[str, Any]:
    """
    Install whisper.cpp with automatic system detection and configuration.
    
    Supports macOS (with Metal) and Linux (with CUDA if available).
    On macOS, also installs a launchagent to run whisper-server on port 2022.
    
    Args:
        install_dir: Directory to install whisper.cpp (default: ~/.voicemode/whisper.cpp)
        model: Whisper model to download (tiny, base, small, medium, large-v2, large-v3, etc.)
               Default is large-v2 for best accuracy. Note: large models require ~3GB RAM.
        use_gpu: Enable GPU support if available (default: auto-detect)
        force_reinstall: Force reinstallation even if already installed
    
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
        
        # Check if already installed
        if os.path.exists(install_dir) and not force_reinstall:
            if os.path.exists(os.path.join(install_dir, "main")):
                return {
                    "success": True,
                    "install_path": install_dir,
                    "model_path": os.path.join(install_dir, "models", f"ggml-{model}.bin"),
                    "already_installed": True,
                    "message": "whisper.cpp already installed. Use force_reinstall=True to reinstall."
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
            logger.info("Cloning whisper.cpp repository...")
            subprocess.run([
                "git", "clone", "https://github.com/ggerganov/whisper.cpp.git", install_dir
            ], check=True)
        else:
            logger.info("Using existing whisper.cpp directory...")
        
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
        
        # Download model
        logger.info(f"Downloading model: {model}")
        models_dir = os.path.join(install_dir, "models")
        os.makedirs(models_dir, exist_ok=True)
        
        # Use the download script
        download_script = os.path.join(models_dir, "download-ggml-model.sh")
        subprocess.run(["bash", download_script, model], check=True)
        
        # Verify installation
        logger.info("Verifying installation...")
        model_path = os.path.join(models_dir, f"ggml-{model}.bin")
        
        if not os.path.exists(model_path):
            return {
                "success": False,
                "error": f"Model file not found: {model_path}"
            }
        
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
            
            plist_name = "com.voicemode.whisper-server.plist"
            plist_path = os.path.join(launchagents_dir, plist_name)
            
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.whisper-server</string>
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
    <string>{os.path.join(voicemode_dir, 'whisper-server.stdout.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, 'whisper-server.stderr.log')}</string>
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
            
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
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
                "message": f"Successfully installed whisper.cpp with {gpu_type} support and whisper-server on port 2022"
            }
        
        # Install systemd service on Linux
        elif system == "Linux":
            logger.info("Installing systemd user service for whisper-server...")
            systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(systemd_user_dir, exist_ok=True)
            
            service_name = "whisper-server.service"
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
StandardOutput=append:{os.path.join(voicemode_dir, 'whisper-server.log')}
StandardError=append:{os.path.join(voicemode_dir, 'whisper-server.error.log')}
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
            
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
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
                "message": f"Successfully installed whisper.cpp with {gpu_type} support. {systemd_message}"
            }
        
        else:
            return {
                "success": True,
                "install_path": install_dir,
                "model_path": model_path,
                "gpu_enabled": use_gpu,
                "gpu_type": gpu_type,
                "performance_info": {
                    "system": system,
                    "gpu_acceleration": gpu_type,
                    "model": model,
                    "binary_path": main_path if 'main_path' in locals() else os.path.join(install_dir, "main")
                },
                "message": f"Successfully installed whisper.cpp with {gpu_type} support"
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


@mcp.tool()
async def install_kokoro_fastapi(
    install_dir: Optional[str] = None,
    models_dir: Optional[str] = None,
    port: int = 8880,
    auto_start: bool = True,
    install_models: bool = True,
    force_reinstall: bool = False
) -> Dict[str, Any]:
    """
    Install and setup remsky/kokoro-fastapi TTS service using the simple 3-step approach.
    
    1. Clones the repository to ~/.voicemode/kokoro-fastapi
    2. Uses the appropriate start script (start-gpu_mac.sh on macOS)
    3. Installs a launchagent on macOS for automatic startup
    
    Args:
        install_dir: Directory to install kokoro-fastapi (default: ~/.voicemode/kokoro-fastapi)
        models_dir: Directory for Kokoro models (default: ~/.voicemode/kokoro-models) - not currently used
        port: Port to configure for the service (default: 8880)
        auto_start: Start the service after installation (ignored on macOS, uses launchd instead)
        install_models: Download Kokoro models (not used - handled by start script)
        force_reinstall: Force reinstallation even if already installed
    
    Returns:
        Installation status with service configuration details
    """
    try:
        # Set default directories under ~/.voicemode
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "kokoro-fastapi")
        else:
            install_dir = os.path.expanduser(install_dir)
            
        if models_dir is None:
            models_dir = os.path.join(voicemode_dir, "kokoro-models")
        else:
            models_dir = os.path.expanduser(models_dir)
        
        # Check if already installed
        if os.path.exists(install_dir) and not force_reinstall:
            if os.path.exists(os.path.join(install_dir, "main.py")):
                return {
                    "success": True,
                    "install_path": install_dir,
                    "models_path": models_dir,
                    "already_installed": True,
                    "message": "kokoro-fastapi already installed. Use force_reinstall=True to reinstall."
                }
        
        # Check Python version
        if sys.version_info < (3, 10):
            return {
                "success": False,
                "error": f"Python 3.10+ required. Current version: {sys.version}"
            }
        
        # Check for git
        if not shutil.which("git"):
            return {
                "success": False,
                "error": "Git is required. Please install git and try again."
            }
        
        # Install UV if not present
        if not shutil.which("uv"):
            logger.info("Installing UV package manager...")
            subprocess.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True,
                check=True
            )
            # Add UV to PATH for this session
            os.environ["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{os.environ['PATH']}"
        
        # Remove existing installation if force_reinstall
        if force_reinstall and os.path.exists(install_dir):
            logger.info(f"Removing existing installation at {install_dir}")
            shutil.rmtree(install_dir)
        
        # Clone repository if not exists
        if not os.path.exists(install_dir):
            logger.info("Cloning kokoro-fastapi repository...")
            subprocess.run([
                "git", "clone", "https://github.com/remsky/kokoro-fastapi.git", install_dir
            ], check=True)
        else:
            logger.info("Using existing kokoro-fastapi directory...")
        
        # Determine system and select appropriate start script
        system = platform.system()
        if system == "Darwin":
            start_script_name = "start-gpu_mac.sh"
        elif system == "Linux":
            # Check if GPU available
            if shutil.which("nvidia-smi"):
                start_script_name = "start-gpu.sh"
            else:
                start_script_name = "start-cpu.sh"
        else:
            start_script_name = "start-cpu.ps1"  # Windows
        
        start_script_path = os.path.join(install_dir, start_script_name)
        
        # Check if the start script exists
        if not os.path.exists(start_script_path):
            return {
                "success": False,
                "error": f"Start script not found: {start_script_path}",
                "message": "The repository seems incomplete. Try force_reinstall=True"
            }
        
        # If a custom port is requested, we need to modify the start script
        if port != 8880:
            logger.info(f"Creating custom start script for port {port}")
            with open(start_script_path, 'r') as f:
                script_content = f.read()
            
            # Replace the port in the script
            modified_script = script_content.replace("--port 8880", f"--port {port}")
            
            # Create a custom start script
            custom_script_name = f"start-custom-{port}.sh"
            custom_script_path = os.path.join(install_dir, custom_script_name)
            with open(custom_script_path, 'w') as f:
                f.write(modified_script)
            os.chmod(custom_script_path, 0o755)
            start_script_path = custom_script_path
            
        result = {
            "success": True,
            "install_path": install_dir,
            "service_url": f"http://127.0.0.1:{port}",
            "start_command": f"cd {install_dir} && ./{os.path.basename(start_script_path)}",
            "start_script": start_script_path,
            "message": f"Kokoro-fastapi installed. Run: cd {install_dir} && ./{os.path.basename(start_script_path)}"
        }
        
        # Install launchagent on macOS
        if system == "Darwin":
            logger.info("Installing launchagent for automatic startup...")
            launchagents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launchagents_dir, exist_ok=True)
            
            plist_name = f"com.voicemode.kokoro-{port}.plist"
            plist_path = os.path.join(launchagents_dir, plist_name)
            
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.kokoro-{port}</string>
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
    <string>{os.path.join(voicemode_dir, f'kokoro-{port}.log')}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(voicemode_dir, f'kokoro-{port}.error.log')}</string>
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
            result["launchagent"] = plist_path
            result["message"] += f"\nLaunchAgent installed: {plist_name}"
        
        # Install systemd service on Linux
        elif system == "Linux":
            logger.info("Installing systemd user service for kokoro-fastapi...")
            systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(systemd_user_dir, exist_ok=True)
            
            service_name = f"kokoro-fastapi-{port}.service"
            service_path = os.path.join(systemd_user_dir, service_name)
            
            service_content = f"""[Unit]
Description=Kokoro FastAPI TTS Service on port {port}
After=network.target

[Service]
Type=simple
ExecStart={start_script_path}
Restart=on-failure
RestartSec=10
WorkingDirectory={install_dir}
StandardOutput=append:{os.path.join(voicemode_dir, f'kokoro-fastapi-{port}.log')}
StandardError=append:{os.path.join(voicemode_dir, f'kokoro-fastapi-{port}.error.log')}
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/home/m/.local/bin"

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
                
                result["systemd_service"] = service_path
                result["systemd_enabled"] = True
                result["message"] += f"\nSystemd service installed and started: {service_name}"
                result["service_status"] = "managed_by_systemd"
            except subprocess.CalledProcessError as e:
                result["systemd_service"] = service_path
                result["systemd_enabled"] = False
                result["message"] += f"\nSystemd service created but not started: {e}"
                logger.warning(f"Systemd service error: {e}")
        
        # Start service if requested (skip if launchagent or systemd was installed)
        if auto_start and system not in ["Darwin", "Linux"]:
            logger.info("Starting kokoro-fastapi service...")
            # Start in background
            process = subprocess.Popen(
                ["bash", start_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait a moment for service to start
            await asyncio.sleep(3)
            
            # Check if service is running
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{port}/health") as response:
                        if response.status == 200:
                            result["service_status"] = "running"
                            result["service_pid"] = process.pid
                        else:
                            result["service_status"] = "failed"
                            result["error"] = "Health check failed"
            except:
                result["service_status"] = "failed"
                result["error"] = "Could not connect to service"
        elif system == "Darwin" and "launchagent" in result:
            result["service_status"] = "managed_by_launchd"
        elif system == "Linux" and "systemd_enabled" in result and result["systemd_enabled"]:
            # Service status already set to "managed_by_systemd" in the systemd section
            pass
        else:
            result["service_status"] = "not_started"
        
        return result
    
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Command failed: {e.cmd}",
            "stderr": e.stderr.decode() if e.stderr else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }