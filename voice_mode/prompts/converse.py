"""Conversation prompts for voice interactions."""

from voice_mode.server import mcp


@mcp.prompt()
def converse() -> str:
    """Have an ongoing two-way voice conversation with the user."""
    return """- You are in an ongoing two-way voice conversation with the user
- If this is a new conversation with no prior context, greet briefly and ask what they'd like to work on
- If continuing an existing conversation, acknowledge and continue from where you left off
- Use tools from voice-mode to converse
- End the chat when the user indicates they want to end it
- Keep your utterances brief unless a longer response is requested or necessary"""
