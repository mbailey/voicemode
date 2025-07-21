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
    model: str = "base.en",
    use_gpu: Optional[bool] = None,
    force_reinstall: bool = False
) -> Dict[str, Any]:
    """
    Install whisper.cpp with automatic system detection and configuration.
    
    Supports macOS (with Metal) and Linux (with CUDA if available).
    
    Args:
        install_dir: Directory to install whisper.cpp (default: ~/whisper.cpp)
        model: Whisper model to download (tiny, base, small, medium, large-v3, etc.)
        use_gpu: Enable GPU support if available (default: auto-detect)
        force_reinstall: Force reinstallation even if already installed
    
    Returns:
        Installation status with paths and configuration details
    """
    try:
        # Set default install directory
        if install_dir is None:
            install_dir = os.path.expanduser("~/whisper.cpp")
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
    Install and setup remsky/kokoro-fastapi TTS service.
    
    Automatically configures the service and downloads required models.
    
    Args:
        install_dir: Directory to install kokoro-fastapi (default: ~/kokoro-fastapi)
        models_dir: Directory for Kokoro models (default: ~/Models/kokoro)
        port: Port to configure for the service (default: 8880)
        auto_start: Start the service after installation
        install_models: Download Kokoro models
        force_reinstall: Force reinstallation even if already installed
    
    Returns:
        Installation status with service configuration details
    """
    try:
        # Set default directories
        if install_dir is None:
            install_dir = os.path.expanduser("~/kokoro-fastapi")
        else:
            install_dir = os.path.expanduser(install_dir)
            
        if models_dir is None:
            models_dir = os.path.expanduser("~/Models/kokoro")
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
        
        # Save current directory
        original_dir = os.getcwd()
        
        try:
            os.chdir(install_dir)
            
            # Create virtual environment if not exists
            venv_path = os.path.join(install_dir, ".venv")
            if not os.path.exists(venv_path):
                logger.info("Creating virtual environment...")
                subprocess.run(["uv", "venv"], check=True)
            else:
                logger.info("Using existing virtual environment...")
            
            # Determine venv Python path
            venv_python = os.path.join(install_dir, ".venv", "bin", "python")
            if not os.path.exists(venv_python):
                # Windows path
                venv_python = os.path.join(install_dir, ".venv", "Scripts", "python.exe")
            
            # Install dependencies
            logger.info("Installing dependencies...")
            subprocess.run(["uv", "pip", "install", "-r", "requirements.txt"], check=True)
            
            # Download models if requested
            if install_models:
                logger.info("Downloading Kokoro models...")
                os.makedirs(models_dir, exist_ok=True)
            
                # Model files to download
                model_files = [
                    "kokoro-v0_19.onnx",
                    "kokoro-v0_19.onnx.json",
                    "voices.json"
                ]
                
                async with aiohttp.ClientSession() as session:
                    for model_file in model_files:
                        url = f"https://huggingface.co/remsky/kokoro-onnx/resolve/main/{model_file}"
                        output_path = os.path.join(models_dir, model_file)
                        
                        if os.path.exists(output_path) and not force_reinstall:
                            logger.info(f"Model already exists: {model_file}")
                            continue
                        
                        logger.info(f"Downloading {model_file}...")
                        async with session.get(url) as response:
                            response.raise_for_status()
                            with open(output_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(8192):
                                    f.write(chunk)
            
            # Create configuration
            config = {
                "host": "127.0.0.1",
                "port": port,
                "models_dir": models_dir,
                "log_level": "info"
            }
            
            config_path = os.path.join(install_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            
            # Create start script
            start_script = f"""#!/bin/bash
cd {install_dir}
source .venv/bin/activate
MODELS_DIR={models_dir} uvicorn main:app --host 127.0.0.1 --port {port}
"""
            
            start_script_path = os.path.join(install_dir, "start.sh")
            with open(start_script_path, "w") as f:
                f.write(start_script)
            os.chmod(start_script_path, 0o755)
            
            # Get available voices
            available_voices = []
            voices_file = os.path.join(models_dir, "voices.json")
            if os.path.exists(voices_file):
                with open(voices_file, "r") as f:
                    voices_data = json.load(f)
                    available_voices = list(voices_data.keys())
            
            result = {
                "success": True,
                "install_path": install_dir,
                "models_path": models_dir,
                "service_url": f"http://127.0.0.1:{port}",
                "start_command": f"bash {start_script_path}",
                "available_voices": available_voices,
                "config_path": config_path
            }
            
            # Start service if requested
            if auto_start:
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
            else:
                result["service_status"] = "not_started"
            
            result["message"] = f"Successfully installed kokoro-fastapi at {install_dir}"
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
        finally:
            # Always restore original directory
            if 'original_dir' in locals():
                os.chdir(original_dir)
    
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