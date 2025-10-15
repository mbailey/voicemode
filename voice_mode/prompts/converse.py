"""Conversation prompts for voice interactions."""

from voice_mode.server import mcp


@mcp.prompt()
def converse(context: str = "") -> str:
    """Have an ongoing two-way voice conversation with the user.

    Args:
        context: Optional context or topic to guide the conversation
    """
    instructions = [
        "Using tools from voice-mode, have an ongoing two-way conversation",
        "End the chat when the user indicates they want to end it",
        "Keep your utterances brief unless a longer response is requested or necessary",
    ]

    # Add context as additional instruction if provided
    if context and context.strip():
        instructions.insert(0, f"Context for this conversation: {context}")

    return "\n".join(f"- {instruction}" for instruction in instructions)
