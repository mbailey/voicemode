"""
Show and tell prompt for VoiceMode.

This prompt enables Claude to give guided audio-visual tours of the codebase,
controlling the user's Neovim editor while explaining the code structure.
"""

from voice_mode.mcp_instance import mcp

@mcp.prompt("show-and-tell")
async def show_and_tell():
    """Audio-visual tour of VoiceMode codebase with Neovim navigation"""
    return f"""# Show and Tell

Please provide an audio-visual tour of the VoiceMode codebase by:

1. **Before Starting**:
   - Ask if the user wants a tour and what aspect they're interested in
   - Run git ls-files so you know all the paths to files
   - Give a brief overview (1-2 sentences) of what you'll show and the goal

2. **During the Tour**:
   - Use Neovim MCP tools to control what the user sees
   - Ensure all messages to the user are spoken with voicemode MCP tools
   - Open neotree at the beginning if possible
   - Before each utterance, ensure the lines you'll be referring to are in view and selected or highlighted to direct the users eyes to them
   - Before moving to a new file or section:
     - provide the user with an opportunity to ask questions
     - tell them what you are about to open next
   - For each section:
     - Open the file to the correct location
     - Speak about that section's purpose and implementation
     - Show how it fits into the overall architecture
   
3. **Navigation Tips**:
   - Use `:e <filepath>` to open files
   - Use `:<line_number>` to jump to specific lines
   - Use `/pattern` to search for specific code
   - Consider using `:split` or `:vsplit` for comparing files

4. **Content Structure**:
   - Start with the entry point (server.py)
   - Follow the logical flow of a voice conversation
   - Show key modules: config, providers, core, streaming
   - Explain the MCP tool definitions
   - Demonstrate the audio processing pipeline

Important! Do not attempt to modify files or directories with the neovim tools. Use them for display purposes only.

Remember to keep explanations concise and focused on helping the user understand how the pieces fit together.
"""
