"""Minimal test backend to verify setup"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess
from typing import Dict, Any

app = FastAPI(title="Voice Mode Test API")

# Simple CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/voice/test")
async def test_voice(request: Dict[str, Any]):
    """Test voice synthesis with given text"""
    text = request.get("text", "Hello, this is a test")
    response_duration = request.get("response_duration")
    voice = request.get("voice")
    
    # Build the command
    cmd = ["uv", "run", "python", "-m", "voice_mode", "converse", "-m", text]
    
    # Add voice if specified
    if voice:
        cmd.extend(["--voice", voice])
    
    # If response_duration is specified, we want to listen for a response
    # So we DON'T use --no-wait, and we add --duration
    if response_duration is not None:
        cmd.extend(["--duration", str(response_duration)])
    else:
        # Only use --no-wait if we're NOT listening for a response
        cmd.append("--no-wait")
    
    # Adjust timeout based on whether we're waiting for a response
    timeout = 10 if response_duration is None else response_duration + 10
    
    # Run the voice mode converse command
    try:
        result = subprocess.run(
            cmd,
            cwd="/Users/admin/Code/github.com/mbailey/voicemode",
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "success": True,
            "text": text,
            "response_duration": response_duration,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)