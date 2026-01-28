# Contributing to VoiceMode

Thank you for your interest in contributing to VoiceMode. This guide will help you get started with development.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [Astral UV](https://github.com/astral-sh/uv) - Package manager (install with `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Git
- A working microphone and speakers (for testing)
- System dependencies (see README.md for OS-specific instructions)

### Getting Started

1. **Fork and clone the repository**

   External contributors need to fork the repository first (you can't push directly to the main repo):

   - Click **Fork** at https://github.com/mbailey/voicemode
   - Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/voicemode.git
   cd voicemode
   ```

2. **Install in development mode**

   ```bash
   uv tool install -e .
   ```

3. **Set up environment variables**

   ```bash
   # Set your API key
   export OPENAI_API_KEY=your-key-here
   
   # Voice Mode will auto-generate ~/.voicemode/voicemode.env on first run
   # You can edit this file to customize configuration
   ```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=voice_mode

# Run specific test file
pytest tests/test_server_syntax.py
```

## Code Style

- We use standard Python formatting conventions
- Keep imports organized (stdlib, third-party, local)
- Add type hints where appropriate
- Document functions with docstrings

## Testing Locally

The easiest way to test your changes:

```bash
uv run voicemode converse
```

This starts a voice conversation directly, without needing Claude Code or MCP.

### Testing with MCP

The repo's `.mcp.json` uses `uv run voicemode`, which automatically runs your local development version when Claude Code is started in the repo directory. No configuration changes needed.

1. Start Claude Code from the voicemode repo directory
2. Your code changes are immediately available via the MCP tools
3. Use the voice tools to verify functionality

### Testing Audio

```bash
# Test TTS and audio playback
python -c "from voice_mode.core import text_to_speech; import asyncio; asyncio.run(text_to_speech(...))"
```

## Making Changes

1. Create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes
3. Run tests to ensure nothing is broken
4. Commit with descriptive messages
5. Push to your fork and create a pull request
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a PR from your fork to `mbailey/voicemode`

## Debugging

Enable debug mode for detailed logging:
```bash
export VOICEMODE_DEBUG=true
```

Debug recordings are saved to `~/.voicemode/audio/`

## Common Development Tasks

- **Update dependencies**: Edit `pyproject.toml` and run `uv pip install -e .`
- **Build package**: `make build-package`
- **Run tests**: `make test`

## Questions?

Feel free to open an issue if you have questions or need help getting started!
