"""Ask tool for Claude Code voice questions via watch.

This tool allows Claude Code to ask the user a question that gets spoken
on the Pixel Watch, wait for the user's voice response, and receive the
transcription back.

Flow:
1. Claude calls ask_voice("Should I proceed?")
2. Watch wakes, plays TTS, shows "Hold to respond" button
3. User holds button, speaks, releases
4. Response is transcribed and returned to Claude
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

from voice_mode.server import mcp
from voice_mode.config import HTTP_CLIENT_CONFIG

logger = logging.getLogger("voicemode")

# HTTP Bridge URL (on beelink)
HTTP_BRIDGE_URL = os.environ.get("VOICEMODE_HTTP_BRIDGE_URL", "https://192.168.10.10:8890")

# Path to mTLS certs
CERT_DIR = os.path.expanduser("~/.config/argus")


def get_ssl_context():
    """Create SSL context for mTLS with HTTP Bridge."""
    import ssl
    from pathlib import Path

    cert_dir = Path(CERT_DIR)
    client_cert = cert_dir / "client.crt"
    client_key = cert_dir / "client.key"
    ca_cert = cert_dir / "ca.crt"

    if not all(f.exists() for f in [client_cert, client_key, ca_cert]):
        logger.warning("mTLS certs not found, falling back to no verification")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        return ssl_ctx

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.load_cert_chain(client_cert, client_key)
    ssl_ctx.load_verify_locations(ca_cert)
    return ssl_ctx


@mcp.tool()
async def ask_voice(
    question: str,
    timeout_seconds: int = 1800,
    poll_interval_seconds: int = 5,
    voice: Optional[str] = None
) -> str:
    """Ask the user a question via voice on their Pixel Watch and wait for spoken response.

    This tool sends a question to the user's Pixel Watch, where it is spoken
    via TTS. The user can then hold a button to record their response, which
    is transcribed and returned.

    IMPORTANT: This tool blocks until the user responds or timeout is reached.
    The default timeout is 30 minutes - Claude waits patiently for the user
    to respond when they're ready. Don't use this for time-sensitive questions.

    Args:
        question: The question to ask the user (will be spoken via TTS)
        timeout_seconds: How long to wait for response (default: 1800 = 30 minutes)
        poll_interval_seconds: How often to check for response (default: 5 seconds)
        voice: TTS voice to use (default: af_sky)

    Returns:
        The user's transcribed response, or an error message if failed/timed out

    Examples:
        # Ask a simple yes/no question
        response = await ask_voice("Should I proceed with the deployment?")
        # Returns: "Yes, go ahead"

        # Ask for user preference
        response = await ask_voice("Do you want me to run the tests first, or deploy directly?")
        # Returns: "Run the tests first please"

        # Ask for clarification
        response = await ask_voice("Which database should I use - PostgreSQL or MySQL?")
        # Returns: "PostgreSQL"
    """
    logger.info(f"ask_voice: question='{question[:50]}...', timeout={timeout_seconds}s")

    ssl_context = get_ssl_context()

    async with httpx.AsyncClient(
        verify=ssl_context,
        timeout=httpx.Timeout(30.0, connect=10.0)
    ) as client:
        # Step 1: Create ask session
        try:
            payload = {
                "question": question,
                "timeout_seconds": timeout_seconds,
            }
            if voice:
                payload["voice"] = voice

            response = await client.post(
                f"{HTTP_BRIDGE_URL}/ask",
                json=payload
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"ask_voice: Failed to create session: {response.status_code} - {error_detail}")
                return f"Error: Failed to send question to watch (HTTP {response.status_code})"

            data = response.json()
            session_id = data.get("session_id")
            devices_notified = data.get("devices_notified", 0)

            if not session_id:
                return "Error: No session ID returned from server"

            logger.info(f"ask_voice: Session created: {session_id}, devices={devices_notified}")

            if devices_notified == 0:
                logger.warning("ask_voice: No devices received the notification")
                # Continue anyway - user might poll manually

        except httpx.RequestError as e:
            logger.error(f"ask_voice: Connection error creating session: {e}")
            return f"Error: Could not connect to voice bridge ({e})"

        # Step 2: Poll for completion
        elapsed = 0
        last_status = "pending"

        while elapsed < timeout_seconds:
            try:
                response = await client.get(
                    f"{HTTP_BRIDGE_URL}/ask/{session_id}/status"
                )

                if response.status_code == 404:
                    return "Error: Session not found (may have expired)"

                if response.status_code != 200:
                    logger.warning(f"ask_voice: Status check returned {response.status_code}")
                    await asyncio.sleep(poll_interval_seconds)
                    elapsed += poll_interval_seconds
                    continue

                status_data = response.json()
                status = status_data.get("status", "unknown")

                if status != last_status:
                    logger.info(f"ask_voice: Status changed: {last_status} -> {status}")
                    last_status = status

                if status == "completed":
                    response_text = status_data.get("response_text", "")
                    elapsed_ms = status_data.get("elapsed_ms", 0)
                    logger.info(f"ask_voice: Got response in {elapsed_ms}ms: '{response_text[:50]}...'")
                    return response_text

                if status == "timeout":
                    return "Error: Session timed out waiting for response"

                if status == "error":
                    error = status_data.get("error", "Unknown error")
                    return f"Error: {error}"

                # Still pending or listening - wait and poll again
                await asyncio.sleep(poll_interval_seconds)
                elapsed += poll_interval_seconds

            except httpx.RequestError as e:
                logger.warning(f"ask_voice: Poll error (will retry): {e}")
                await asyncio.sleep(poll_interval_seconds)
                elapsed += poll_interval_seconds

        # Timeout reached
        logger.warning(f"ask_voice: Timed out after {elapsed}s")
        return f"Error: Timed out after {timeout_seconds} seconds waiting for response"


@mcp.tool()
async def check_ask_session(session_id: str) -> str:
    """Check the status of an ask session.

    Use this to check on a previously started ask session without blocking.

    Args:
        session_id: The session ID to check

    Returns:
        Status information about the session
    """
    logger.info(f"check_ask_session: {session_id}")

    ssl_context = get_ssl_context()

    async with httpx.AsyncClient(
        verify=ssl_context,
        timeout=httpx.Timeout(10.0, connect=5.0)
    ) as client:
        try:
            response = await client.get(
                f"{HTTP_BRIDGE_URL}/ask/{session_id}/status"
            )

            if response.status_code == 404:
                return "Session not found (may have expired)"

            if response.status_code != 200:
                return f"Error checking status: HTTP {response.status_code}"

            data = response.json()
            status = data.get("status", "unknown")
            elapsed_ms = data.get("elapsed_ms", 0)
            elapsed_sec = elapsed_ms / 1000

            result_parts = [
                f"Status: {status}",
                f"Elapsed: {elapsed_sec:.1f}s",
                f"Question: {data.get('question', 'N/A')[:50]}..."
            ]

            if status == "completed":
                result_parts.append(f"Response: {data.get('response_text', 'N/A')}")

            if status == "error":
                result_parts.append(f"Error: {data.get('error', 'Unknown')}")

            return "\n".join(result_parts)

        except httpx.RequestError as e:
            logger.error(f"check_ask_session: Connection error: {e}")
            return f"Error: Could not connect to voice bridge ({e})"
