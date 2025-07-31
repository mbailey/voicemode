# Contributing to voice-mode

Thank you for your interest in contributing to voice-mode! This guide will help you get started with development.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [Astral UV](https://github.com/astral-sh/uv) - Package manager (install with `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Git
- A working microphone and speakers (for testing)
- System dependencies (see README.md for OS-specific instructions)

### Getting Started

1. **Clone the repository**
   ```bash
   git clone https://github.com/mbailey/voicemode.git
   cd voicemode
   ```

2. **Create a virtual environment**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in development mode**
   ```bash
   uv pip install -e .
   uv pip install -e .[dev,test]
   ```

4. **Set up environment variables**
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

### Testing with MCP

1. Update `.mcp.json` to point to your development version
2. Run `mcp` to test the connection
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
5. Push and create a pull request

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
- **Run linting**: `make lint` (if configured)

## Questions?

Feel free to open an issue if you have questions or need help getting started!
