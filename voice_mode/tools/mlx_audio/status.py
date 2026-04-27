"""Status check tool for the mlx-audio service."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict

from voice_mode.config import MLX_AUDIO_PORT

logger = logging.getLogger("voicemode")


async def mlx_audio_status() -> Dict[str, Any]:
    """Check the status of the mlx-audio service.

    Hits ``/v1/models`` on the configured port (default 8890) to verify
    the OpenAI-compatible endpoint is responding.

    Returns:
        Dict with service status, health, and endpoint details.
    """
    port = MLX_AUDIO_PORT
    url = f"http://127.0.0.1:{port}"
    health_url = f"{url}/v1/models"

    result: Dict[str, Any] = {
        "service": "mlx_audio",
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
                result["message"] = f"mlx-audio service is running on port {port}"
            else:
                result["status"] = "unhealthy"
                result["healthy"] = False
                result["http_status"] = resp.status
                result["message"] = (
                    f"mlx-audio service responded with HTTP {resp.status}"
                )
    except urllib.error.URLError:
        result["status"] = "not_running"
        result["healthy"] = False
        result["message"] = (
            f"mlx-audio service is not running on port {port}. "
            "Run 'voicemode service install mlx-audio' to set it up."
        )
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["healthy"] = False
        result["error"] = str(exc)
        result["message"] = f"Error checking mlx-audio service: {exc}"

    return result
