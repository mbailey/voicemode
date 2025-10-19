# Development Setup

*Note: These docs need review.*

This guide covers setting up VoiceMode for development, including building from source, configuring your IDE, and contributing to the project.

## Prerequisites

- Python 3.10 or higher
- Git
- UV package manager (recommended) or pip
- Node.js 18+ (for frontend development)

## Setting Up UV

UV is a fast Python package manager written in Rust. It's the recommended tool for VoiceMode development:

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

## Quick Start (Recommended)

The Makefile provides convenient targets for all common development tasks:

```bash
# Clone the repository
git clone https://github.com/mbailey/voicemode
cd voicemode

# Install with development dependencies (creates venv automatically)
make dev-install

# Run tests to verify setup
make test
```

That's it! The Makefile handles virtual environment creation, dependency installation, and test setup automatically.

## Manual Setup (Alternative Method)

If you prefer to set things up manually or need more control:

```bash
# Clone the repository
git clone https://github.com/mbailey/voicemode
cd voicemode

# Create and activate virtual environment
uv tool install -e .[dev,test]

```

## Development Workflow

### Running from Source

### Building the Package

```bash
# Build the package
uv build

# This creates:
# dist/voice_mode-X.Y.Z-py3-none-any.whl
# dist/voice_mode-X.Y.Z.tar.gz

# Test the built package
uvx --from dist/voice_mode-*.whl voice-mode
```

### Running Tests

#### Using Makefile (Recommended)

The Makefile provides comprehensive test targets (see `make help`):

```bash
# Run unit tests with pytest
make test

# Run tests with coverage report
make coverage

# Run all tests (including slow/manual)
make test-all
```

#### Manual Testing (Alternative)

If you prefer running tests directly:

```bash
# Using uv run (no activation needed)
uv run pytest

# using python
source .venv/bin/activate
pytest

# Run with coverage
pytest --cov=voice_mode

# Run specific test file
pytest tests/test_converse.py

# Run with verbose output
pytest -v
```

### Using Local Services

For development without API keys:

```bash
# Or manually
voicemode whisper install
voicemode kokoro install

# Or manually
voicemode whisper start
voicemode kokoro start
```

## Project Structure

```ini
voicemode/
├── voice_mode/           # Main package
│   ├── __init__.py
│   ├── server.py         # MCP server
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration
│   ├── tools/           # MCP tools
│   │   ├── converse.py
│   │   └── services/    # Service installers
│   ├── providers.py     # Service providers
│   ├── frontend/        # Next.js frontend
│   └── templates/       # Service templates
├── tests/               # Test suite
├── docs/               # Documentation
├── scripts/            # Development scripts
├── Makefile           # Development tasks
└── pyproject.toml     # Project configuration
```

## Common Development Tasks

### Adding a New Tool

1. Create tool file in `voice_mode/tools/`
2. Implement tool class with MCP decorators
3. Add tests in `tests/tools/`
4. Update documentation

### Modifying Configuration

1. Update `voice_mode/config.py`
2. Add environment variable to docs
3. Update tests for new config
4. Add to example `.env` files

### Updating Dependencies

```bash
# Add a new dependency
uv add requests

# Add development dependency
uv add --dev pytest-mock

# Update all dependencies
uv sync
```

## Debugging

### Enable Debug Mode

```bash
export VOICEMODE_DEBUG=true
export VOICEMODE_LOG_LEVEL=debug
```

### Debug Output Locations

- Logs: `~/.voicemode/logs/`
- Audio files: `~/.voicemode/debug/`
- Event logs: `~/.voicemode/events.log`

### Common Debug Commands

```bash
# Check service status
voicemode whisper status
voicemode kokoro status
```

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run with markers
pytest -m "not integration"
```

### Integration Tests

```bash
# Run integration tests
pytest tests/integration/

# Run specific service tests
pytest tests/integration/test_whisper.py
```

### Manual Testing

```bash
# Test voice conversation with debug output
voice-mode converse --debug

# Test specific tool
voice-mode test-tool converse

# Test with different providers
VOICEMODE_TTS_BASE_URLS=http://localhost:8880/v1 voice-mode converse
```

### Testing Service Installations

Update your local '.voicemode.env' file to overide the default path `~/.voicemode`

```bash
echo "VOICEMODE_BASE_DIR=/tmp/.voicemode" >> .voicemode.env
```

Use temporary directories when testing installers to prevent affecting your production setup in `~/.voicemode/services/`:

```bash

# Test Whisper installation
voicemode whisper install --force --install-dir /tmp/.voicemode/services/whisper/ --model large-v3-turbo

# Test Kokoro installation
voicemode kokoro install --force --install-dir /tmp/.voicemode/services/kokoro/ 

# Test LiveKit installation
voicemode livekit install --force --install-dir /tmp/.voicemode/services/livekit/ --port 7881
```

## Contributing

For guidelines on contributing to the project, including code style, commit conventions, and the pull request process, please see the [Contributing Guide](/CONTRIBUTING.md).

## Makefile Commands Reference

The Makefile is the primary tool for development tasks. Run `make help` for a comprehensive list of available targets.  Here is a sample of commonly used targets:

### Essential Development Commands

```bash
make help          # Show all available targets
make dev-install   # Install package with development dependencies
make test          # Run unit tests
make clean         # Remove build artifacts and caches
```

### Testing & Coverage

```bash
make test          # Run unit tests with pytest
make coverage      # Run tests with coverage report
make coverage-html # Generate and open HTML coverage report
make test-unit     # Run unit tests only
make test-integration # Run integration tests
make test-all      # Run all tests (including slow/manual)
make test-parallel # Run tests in parallel
```

### Building & Publishing

```bash
make build-package # Build Python package for PyPI
make build-dev     # Build development package with auto-versioning
make test-package  # Test package installation
```

### Documentation

```bash
make docs    # Build documentation
make docs-serve    # Serve documentation locally (http://localhost:8000)
make docs-build    # Build documentation site
make docs-check    # Check documentation for errors (strict mode)
```

## Troubleshooting Development Issues

### Common Issues

#### "pytest: command not found"

This happens when the virtual environment isn't activated. Solutions:

- Use `make test` which handles everything automatically
- Use `uv run pytest` instead (no activation needed)
- Activate the venv: `source .venv/bin/activate`

#### pyenv/VIRTUAL_ENV conflicts

If you see warnings about VIRTUAL_ENV not matching the project environment:

- This is usually harmless - uv will use the project's `.venv`
- To avoid the warning, deactivate any other Python environments first

#### Verifying Installation

To check if everything is installed correctly:

```bash
# Check if pytest is installed
uv run pytest --version

# Check if voice_mode is installed in editable mode
uv pip list | grep voice-mode

# Run a simple test
uv run pytest tests/test_server_syntax.py -v
```

### Import Errors

```bash
uv pip install -e .
```

### Service Connection Issues

```bash
# Check if ports are in use
lsof -i :8880  # Kokoro
lsof -i :2022  # Whisper
lsof -i :7880  # LiveKit

# Kill stuck processes
pkill -f kokoro
pkill -f whisper
```

## Additional Resources

- [VoiceMode Architecture](../concepts/architecture.md)
- [API Reference](../reference/api.md)
- [Service Development](../concepts/service-model.md)
- [Testing Guide](../guides/testing.md)
