"""
Voice notification for Claude Code tool calls.

When a voice session is active, this command synthesizes a short spoken
notification (e.g. "rodando bash", "lendo arquivo") using the local TTS
service, so the user gets audio feedback for tool activity.

CLI usage (for use in Claude Code hooks):
    voicemode notify pre <tool_name>
    voicemode notify post <tool_name>

Session state:
    A voice session is considered active when the file
    ~/.voicemode/voice_session exists and was modified within the last
    VOICEMODE_NOTIFY_SESSION_TTL seconds (default: 300).

Configuration:
    VOICEMODE_TOOL_NOTIFY=true|false       (default: false)
    VOICEMODE_NOTIFY_VOICE=pf_dora         (TTS voice for notifications)
    VOICEMODE_NOTIFY_SESSION_TTL=300       (seconds before session expires)
    VOICEMODE_NOTIFY_LANGUAGE=pt           (language for spoken messages: pt or en)
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import click

logger = logging.getLogger("voicemode")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TOOL_NOTIFY_ENABLED = os.environ.get("VOICEMODE_TOOL_NOTIFY", "false").lower() in ("true", "1", "yes")
NOTIFY_VOICE = os.environ.get("VOICEMODE_NOTIFY_VOICE", "pf_dora")
NOTIFY_SESSION_TTL = int(os.environ.get("VOICEMODE_NOTIFY_SESSION_TTL", "300"))
NOTIFY_LANGUAGE = os.environ.get("VOICEMODE_NOTIFY_LANGUAGE", "pt").lower()
SESSION_FILE = Path.home() / ".voicemode" / "voice_session"

# ---------------------------------------------------------------------------
# Tool name → short spoken message
# ---------------------------------------------------------------------------

_TOOL_MESSAGES_PT = {
    # pre (starting)
    "pre_Bash": "rodando bash",
    "pre_Read": "lendo arquivo",
    "pre_Write": "escrevendo arquivo",
    "pre_Edit": "editando arquivo",
    "pre_Glob": "buscando arquivos",
    "pre_Grep": "buscando conteúdo",
    "pre_Agent": "chamando agente",
    "pre_Task": "criando tarefa",
    "pre_WebFetch": "acessando URL",
    "pre_WebSearch": "buscando na web",
    "pre_TodoWrite": "atualizando tarefas",
    "pre_Notebook": "editando notebook",
    # post (done) — kept silent by default to avoid noise
    "post_Bash": "bash concluído",
    "post_Agent": "agente concluído",
}

_TOOL_MESSAGES_EN = {
    "pre_Bash": "running bash",
    "pre_Read": "reading file",
    "pre_Write": "writing file",
    "pre_Edit": "editing file",
    "pre_Glob": "searching files",
    "pre_Grep": "searching content",
    "pre_Agent": "calling agent",
    "pre_Task": "creating task",
    "pre_WebFetch": "fetching URL",
    "pre_WebSearch": "searching web",
    "pre_TodoWrite": "updating tasks",
    "pre_Notebook": "editing notebook",
    "post_Bash": "bash done",
    "post_Agent": "agent done",
}


def _get_message(phase: str, tool_name: str) -> Optional[str]:
    """Return the spoken message for a tool event, or None to skip."""
    messages = _TOOL_MESSAGES_PT if NOTIFY_LANGUAGE == "pt" else _TOOL_MESSAGES_EN
    key = f"{phase}_{tool_name}"
    # Exact match first
    if key in messages:
        return messages[key]
    # Phase-only fallback (only for "pre")
    if phase == "pre":
        if NOTIFY_LANGUAGE == "pt":
            return f"rodando {tool_name.lower()}"
        return f"running {tool_name.lower()}"
    # post: silent for unknown tools
    return None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def is_voice_session_active() -> bool:
    """Return True if a voice session has been active recently."""
    if not SESSION_FILE.exists():
        return False
    age = time.time() - SESSION_FILE.stat().st_mtime
    return age <= NOTIFY_SESSION_TTL


def touch_voice_session(conversation_id: Optional[str] = None) -> None:
    """Mark that a voice session is currently active."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "ts": time.time(),
        "conversation_id": conversation_id,
    }
    SESSION_FILE.write_text(json.dumps(data))


def clear_voice_session() -> None:
    """Remove the voice session marker."""
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TTS synthesis (fire-and-forget, low latency)
# ---------------------------------------------------------------------------

async def _speak_notification(text: str) -> None:
    """Synthesize and play a short notification via local Kokoro TTS."""
    try:
        from voice_mode.simple_failover import simple_tts_failover
        await simple_tts_failover(
            text=text,
            voice=NOTIFY_VOICE,
            model="tts-1",
        )
    except Exception as exc:
        logger.debug(f"voice_notify: TTS failed: {exc}")


def speak_sync(text: str) -> None:
    """Synchronous wrapper around _speak_notification."""
    try:
        asyncio.run(_speak_notification(text))
    except Exception as exc:
        logger.debug(f"voice_notify: speak_sync failed: {exc}")


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------

@click.group("notify")
def notify():
    """Voice notifications for Claude Code tool events."""
    pass


@notify.command("pre")
@click.argument("tool_name")
@click.option("--force", is_flag=True, help="Speak even if VOICEMODE_TOOL_NOTIFY is not set")
def notify_pre(tool_name: str, force: bool) -> None:
    """Speak a notification before a tool runs (PreToolUse hook)."""
    if not force and not TOOL_NOTIFY_ENABLED:
        return
    if not is_voice_session_active():
        return
    message = _get_message("pre", tool_name)
    if message:
        speak_sync(message)


@notify.command("post")
@click.argument("tool_name")
@click.option("--force", is_flag=True, help="Speak even if VOICEMODE_TOOL_NOTIFY is not set")
def notify_post(tool_name: str, force: bool) -> None:
    """Speak a notification after a tool finishes (PostToolUse hook)."""
    if not force and not TOOL_NOTIFY_ENABLED:
        return
    if not is_voice_session_active():
        return
    message = _get_message("post", tool_name)
    if message:
        speak_sync(message)
