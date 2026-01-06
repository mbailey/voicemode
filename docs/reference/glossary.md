# Glossary

This glossary defines key terms and concepts used throughout the Voice Mode project. It serves as a reference for both human developers and AI assistants to ensure consistent terminology.

## Why This Glossary Exists

- **Consistency**: Ensures everyone uses the same terms with the same meanings
- **Clarity**: Reduces confusion, especially around MCP-specific terminology
- **Onboarding**: Helps new contributors quickly understand domain-specific language
- **AI Assistance**: Provides LLMs with precise definitions to improve their understanding

## How to Use This Glossary

- **For Humans**: Reference this when you encounter unfamiliar terms or want to ensure you're using the right terminology
- **For LLMs**: This file should be read at the start of each session to understand project-specific terminology
- **In Documentation**: Link to glossary entries when introducing potentially unfamiliar terms

---

**Base Directory**: The root directory for all Voice Mode data, defaults to `~/.voicemode`.

**Conversation**: A group of related exchanges that form a complete interaction, typically with less than 5 minutes between exchanges.

**Endpoint**: A specific URL where a provider's API is accessible (e.g., `http://127.0.0.1:8880/v1`).

**Exchange**: A single call-and-response interaction in voice mode. One user utterance and one assistant response.

**Event Log**: Structured log of voice interaction events used for debugging and performance analysis.

**MCP Client**: The LLM or AI assistant that connects to MCP servers. The client uses the tools and resources provided by servers.

**MCP Host**: The application that manages MCP connections between clients and servers. Examples: Claude Desktop, VS Code, Cursor. These are the AI coding assistants that users install Voice Mode into.

**MCP (Model Context Protocol)**: The protocol that enables LLMs to interact with external tools and resources through a standardized interface.

**MP3**: Widely supported compressed audio format, good balance of size and compatibility.

**Opus**: Compressed audio format optimized for voice, good compression but can have quality issues with streaming.

**PCM**: Uncompressed audio format, best for real-time streaming with lowest latency.

**Prompt**: Pre-written instructions that help guide AI assistants in using MCP tools effectively.

**Provider**: A service that provides TTS (text-to-speech) or STT (speech-to-text) capabilities. Examples: OpenAI, Kokoro, Whisper.

**MCP Server**: A program that provides tools and resources via MCP. Voice Mode is an MCP server that provides voice interaction capabilities.

**Resource**: Data or content exposed by an MCP server that clients can read.

**STT (Speech-to-Text)**: Converting spoken audio into written text.

**Streaming**: Playing audio as it arrives rather than waiting for the complete file, reducing latency.

**Tool**: A function exposed by an MCP server that clients can invoke. Voice Mode exposes tools like `converse`, `listen_for_speech`, etc.

**Transcription**: Text version of spoken audio, saved separately from audio files when enabled.

**Transport**: The method used for voice communication - either "local" (direct microphone) or "livekit" (room-based).

**TTFA (Time to First Audio)**: The time between requesting TTS and when audio playback begins.

**TTS (Text-to-Speech)**: Converting written text into spoken audio.

**VoiceMode**: The project name and package that brings natural voice conversations to AI assistants through the Model Context Protocol (MCP). Written as one word with capital M in documentation, lowercase in code/paths.

**VoiceMode Home Directory**: The user's application data directory at `~/.voicemode/` that stores all VoiceMode data including audio recordings, logs, configuration, installed services, and downloaded models. Also referred to by the environment variable VOICEMODE_BASE_DIR.
