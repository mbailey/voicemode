"""Installation tool for Parakeet ASR service."""

import os
import sys
import platform
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from voice_mode.server import mcp
from voice_mode.tools.parakeet.models import (
    get_parakeet_install_dir,
    is_parakeet_installed,
    PARAKEET_PORT,
    DEFAULT_PARAKEET_MODEL,
)

logger = logging.getLogger("voicemode")

# Server code template
SERVER_PY_CONTENT = '''"""
Parakeet ASR Server - VoiceMode compatible whisper.cpp API wrapper

Provides /inference endpoint with whisper-compatible JSON response format.
Runs on port 2023 alongside whisper.cpp (port 2022) for A/B testing.
"""

import asyncio
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model reference for lazy loading
_model = None
_model_lock = asyncio.Lock()
_model_name = "mlx-community/parakeet-tdt-0.6b-v3"

# File upload limits
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/wave", "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/ogg", "audio/flac",
    "audio/aac", "audio/m4a", "audio/x-m4a",
    "audio/webm",
    "application/octet-stream",  # Allow when MIME detection fails
}


async def get_model():
    """Lazy load the parakeet model on first request with thread-safety."""
    global _model
    async with _model_lock:
        if _model is None:
            from parakeet_mlx import from_pretrained
            _model = from_pretrained(_model_name)
        return _model


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield
    # Cleanup on shutdown if needed
    global _model
    _model = None


app = FastAPI(
    title="Parakeet ASR Server",
    description="VoiceMode-compatible ASR server using NVIDIA Parakeet via MLX",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Simple info page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Parakeet ASR Server</title>
        <style>
            body { font-family: system-ui, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
            pre { background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>Parakeet ASR Server</h1>
        <p>VoiceMode-compatible speech-to-text server using NVIDIA Parakeet via MLX.</p>

        <h2>Endpoints</h2>
        <ul>
            <li><code>GET /</code> - This page</li>
            <li><code>GET /health</code> - Health check</li>
            <li><code>POST /inference</code> - Transcribe audio</li>
        </ul>

        <h2>Usage</h2>
        <pre>curl -X POST http://localhost:2023/inference \\
  -F "file=@audio.wav"</pre>

        <h2>Model</h2>
        <p>Using: <code>mlx-community/parakeet-tdt-0.6b-v3</code></p>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/inference")
async def inference(
    file: UploadFile = File(...),
    temperature: Optional[float] = Form(default=0.0),
    response_format: Optional[str] = Form(default="json"),
):
    """
    Transcribe audio file using Parakeet ASR.

    Compatible with whisper.cpp server API format.

    Args:
        file: Audio file (WAV, MP3, etc.)
        temperature: Decoding temperature (ignored, for API compatibility)
        response_format: Response format - "json" or "verbose_json"

    Returns:
        JSON with transcription result in whisper-compatible format
    """
    temp_path = None
    try:
        # Validate MIME type
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Expected audio file, got: {content_type}"
            )

        # Read and validate file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # Save uploaded file to temp location
        suffix = Path(file.filename).suffix if file.filename else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        # Get model (lazy load on first request)
        model = await get_model()

        # Transcribe
        start_time = time.time()
        result = model.transcribe(temp_path)
        duration = time.time() - start_time

        # Extract text and language
        text = result.text if hasattr(result, 'text') else str(result)
        language = getattr(result, 'language', None) or "en"

        # Build response based on format
        if response_format == "verbose_json":
            response = {
                "task": "transcribe",
                "language": language,
                "duration": duration,
                "text": text,
                "segments": [
                    {
                        "id": 0,
                        "text": text,
                        "start": 0.0,
                        "end": duration,
                    }
                ],
            }
        else:
            # Default json format (minimal)
            response = {
                "text": text,
                "language": language,
            }

        return JSONResponse(content=response)

    except HTTPException:
        # Re-raise HTTP exceptions as-is (validation errors)
        raise

    except Exception as e:
        # Log full error server-side, return generic message to client
        logger.error(f"Transcription failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Transcription failed")

    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {temp_path}: {e}")


# OpenAI-compatible endpoint alias (VoiceMode uses this path)
@app.post("/v1/audio/transcriptions")
@app.post("/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: Optional[str] = Form(default="parakeet-tdt-0.6b-v3"),
    language: Optional[str] = Form(default=None),
    response_format: Optional[str] = Form(default="json"),
):
    """OpenAI-compatible transcription endpoint."""
    return await inference(file=file, temperature=0.0, response_format=response_format)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=2023)
'''

REQUIREMENTS_CONTENT = """parakeet-mlx>=0.3.0
fastapi>=0.109.0
uvicorn>=0.27.0
python-multipart>=0.0.6
"""

RUN_SERVER_SH_CONTENT = """#!/bin/bash
# Run Parakeet ASR Server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source .venv/bin/activate

# Run server
exec python server.py
"""

STOP_SERVER_SH_CONTENT = """#!/bin/bash
# Stop Parakeet ASR Server

pkill -f "python.*server.py.*parakeet" 2>/dev/null || true
pkill -f "uvicorn.*:2023" 2>/dev/null || true

echo "Parakeet server stopped"
"""

LAUNCHD_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.parakeet</string>
    <key>ProgramArguments</key>
    <array>
        <string>{install_dir}/.venv/bin/python</string>
        <string>{install_dir}/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{install_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{voicemode_dir}/logs/parakeet/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{voicemode_dir}/logs/parakeet/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
"""


@mcp.tool()
async def parakeet_install(
    install_dir: Optional[str] = None,
    port: int = PARAKEET_PORT,
    force_reinstall: bool = False,
    auto_enable: Optional[bool] = None,
) -> Dict[str, Any]:
    """Install Parakeet ASR service.

    Parakeet is an NVIDIA ASR model that runs via MLX on Apple Silicon.
    It's faster than Whisper with better accuracy for many languages.

    Args:
        install_dir: Custom installation directory (default: ~/.voicemode/services/parakeet)
        port: Port for the server (default: 2023)
        force_reinstall: Force reinstall even if already installed
        auto_enable: Enable service at boot/login (default: True on macOS)

    Returns:
        Dict with installation result
    """
    result = {
        "success": False,
        "install_path": None,
        "already_installed": False,
        "enabled": False,
    }

    # Check platform - Parakeet MLX only works on Apple Silicon
    if platform.system() != "Darwin":
        result["error"] = "Parakeet MLX is only supported on macOS with Apple Silicon"
        return result

    # Check for Apple Silicon
    if platform.machine() != "arm64":
        result["error"] = "Parakeet MLX requires Apple Silicon (M1/M2/M3)"
        return result

    # Determine installation directory
    if install_dir:
        install_path = Path(install_dir).expanduser().resolve()
    else:
        install_path = get_parakeet_install_dir()

    result["install_path"] = str(install_path)

    # Check if already installed
    if is_parakeet_installed() and not force_reinstall:
        result["success"] = True
        result["already_installed"] = True
        return result

    voicemode_dir = Path.home() / ".voicemode"

    try:
        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)

        # Create log directory
        log_dir = voicemode_dir / "logs" / "parakeet"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Write server.py
        server_path = install_path / "server.py"
        server_path.write_text(SERVER_PY_CONTENT)
        server_path.chmod(0o755)
        logger.info(f"Created server.py at {server_path}")

        # Write requirements.txt
        requirements_path = install_path / "requirements.txt"
        requirements_path.write_text(REQUIREMENTS_CONTENT)
        logger.info(f"Created requirements.txt at {requirements_path}")

        # Write run-server.sh
        run_script = install_path / "run-server.sh"
        run_script.write_text(RUN_SERVER_SH_CONTENT)
        run_script.chmod(0o755)

        # Write stop-server.sh
        stop_script = install_path / "stop-server.sh"
        stop_script.write_text(STOP_SERVER_SH_CONTENT)
        stop_script.chmod(0o755)

        # Create virtual environment using uv if available, otherwise python3 -m venv
        venv_path = install_path / ".venv"
        if shutil.which("uv"):
            logger.info("Creating virtual environment with uv...")
            subprocess.run(
                ["uv", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Installing dependencies with uv pip...")
            subprocess.run(
                ["uv", "pip", "install", "--python", str(venv_path / "bin" / "python"), "-r", str(requirements_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            logger.info("Creating virtual environment with python3 -m venv...")
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            pip_path = venv_path / "bin" / "pip"
            logger.info("Installing dependencies with pip...")
            subprocess.run(
                [str(pip_path), "install", "-r", str(requirements_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        # Create launchd plist for macOS
        if platform.system() == "Darwin":
            plist_content = LAUNCHD_PLIST_TEMPLATE.format(
                install_dir=str(install_path),
                voicemode_dir=str(voicemode_dir),
            )
            plist_path = install_path / "com.voicemode.parakeet.plist"
            plist_path.write_text(plist_content)
            logger.info(f"Created launchd plist at {plist_path}")

            # Auto-enable if requested
            if auto_enable is None:
                auto_enable = True  # Default to enabled on macOS

            if auto_enable:
                # Copy to LaunchAgents
                launch_agents = Path.home() / "Library" / "LaunchAgents"
                launch_agents.mkdir(parents=True, exist_ok=True)
                target_plist = launch_agents / "com.voicemode.parakeet.plist"
                shutil.copy2(plist_path, target_plist)

                # Load the service
                subprocess.run(
                    ["launchctl", "load", str(target_plist)],
                    capture_output=True,
                    text=True,
                )
                result["enabled"] = True
                logger.info("Parakeet service enabled and started")

        result["success"] = True
        logger.info(f"Parakeet ASR service installed successfully at {install_path}")

    except subprocess.CalledProcessError as e:
        result["error"] = f"Installation failed: {e.stderr if e.stderr else str(e)}"
        logger.error(result["error"])
    except Exception as e:
        result["error"] = f"Installation failed: {str(e)}"
        logger.error(result["error"])

    return result


@mcp.tool()
async def parakeet_uninstall(
    remove_all_data: bool = False,
) -> Dict[str, Any]:
    """Uninstall Parakeet ASR service.

    Args:
        remove_all_data: Also remove logs and configuration

    Returns:
        Dict with uninstall result
    """
    result = {
        "success": False,
        "service_stopped": False,
        "service_disabled": False,
        "install_removed": False,
        "data_removed": False,
    }

    install_path = get_parakeet_install_dir()
    voicemode_dir = Path.home() / ".voicemode"

    try:
        # Stop service if running
        if platform.system() == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.parakeet.plist"
            if plist_path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    capture_output=True,
                    text=True,
                )
                plist_path.unlink()
                result["service_disabled"] = True
                result["service_stopped"] = True

        # Also kill any running process
        subprocess.run(
            ["pkill", "-f", "parakeet.*server.py"],
            capture_output=True,
        )

        # Remove installation directory
        if install_path.exists():
            shutil.rmtree(install_path)
            result["install_removed"] = True
            result["install_path"] = str(install_path)

        # Remove logs if requested
        if remove_all_data:
            log_dir = voicemode_dir / "logs" / "parakeet"
            if log_dir.exists():
                shutil.rmtree(log_dir)
                result["data_removed"] = True

        result["success"] = True

    except Exception as e:
        result["error"] = f"Uninstall failed: {str(e)}"
        logger.error(result["error"])

    return result
