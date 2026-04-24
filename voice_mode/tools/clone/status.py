"""Status check tool for clone TTS service (Qwen3-TTS via mlx-audio)."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict

from voice_mode.config import CLONE_PORT

logger = logging.getLogger("voicemode")


async def clone_status() -> Dict[str, Any]:
    """Check the status of the clone TTS service (Qwen3-TTS via mlx-audio).

    Checks if the service is running and the endpoint is healthy by hitting
    the /v1/models endpoint on the configured port (default: 8890).

    Returns:
        Dictionary with service status, health, and endpoint details.
    """
    port = CLONE_PORT
    url = f"http://127.0.0.1:{port}"
    health_url = f"{url}/v1/models"

    result: Dict[str, Any] = {
        "service": "clone",
        "port": port,
        "url": url,
    }

    try:
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                result["status"] = "running"
                result["healthy"] = True
                result["models"] = data
                result["message"] = f"Clone TTS service is running on port {port}"
            else:
                result["status"] = "unhealthy"
                result["healthy"] = False
                result["http_status"] = resp.status
                result["message"] = f"Clone TTS service responded with HTTP {resp.status}"
    except urllib.error.URLError:
        result["status"] = "not_running"
        result["healthy"] = False
        result["message"] = (
            f"Clone TTS service is not running on port {port}. "
            "Run 'voicemode clone install' to set it up."
        )
    except Exception as e:
        result["status"] = "error"
        result["healthy"] = False
        result["error"] = str(e)
        result["message"] = f"Error checking clone TTS service: {e}"

    return result
