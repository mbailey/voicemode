# Contributing to voice-mode

Thank you for your interest in contributing to voice-mode! This guide will help you get started with making your first contribution.

## Contribution Workflow

Based on the project's development patterns, here's the typical workflow for contributions:

1. **Fork and Clone**

   - Fork the repository to your GitHub account
   - Clone your fork locally
   - Add the upstream repository as a remote

2. **Set Up Development Environment**

   - Follow the [Development Setup Guide](docs/tutorials/development-setup.md) for installation
   - Ensure all tests pass before making changes

3. **Create a Feature Branch**

   - Use descriptive branch names (e.g., `feature/add-new-voice`, `fix/audio-playback-issue`)
   - Branch from the main branch

4. **Make Your Changes**

   - Follow the existing code style and patterns
   - Add tests for new functionality
   - Update documentation if needed

5. **Test Your Changes**

   - Run the full test suite with `make test` or `uv run pytest`
   - Test manually with different configurations
   - Ensure no regressions in existing functionality

6. **Commit Your Changes**

   - Use conventional commit messages (see Commit Messages section below)
   - Keep commits focused and atomic
   - Write clear, descriptive commit messages

7. **Submit a Pull Request**

   - Push your branch to your fork
   - Open a PR against the main repository
   - Provide a clear description of changes and motivation
   - Link any related issues

## Development Setup

For detailed setup instructions, please see the [Development Setup Guide](docs/tutorials/development-setup.md).

### Quick Start

1. Clone the repository
2. Create and activate a virtual environment with `uv venv`
3. Install with `uv pip install -e .[dev,test]`
4. Run tests with `uv run pytest` or `make test`

For troubleshooting and detailed instructions, refer to the [Development Setup Guide](docs/tutorials/development-setup.md).

## Running Tests

```bash
# Quick start - run all tests
uv run pytest
```

For detailed testing options (coverage, specific files, parallel execution), see the [Testing section in the Development Setup Guide](docs/tutorials/development-setup.md#running-tests).

## Code Style

- We use standard Python formatting conventions
- Keep imports organized (stdlib, third-party, local)
- Add type hints where appropriate
- Document functions with docstrings

## Testing Locally

For local testing instructions including MCP integration and audio testing, see the [Manual Testing section](docs/tutorials/development-setup.md#manual-testing).

## Code Style

We use standard Python formatting conventions with Black and Ruff:

```bash
# Format code
black voice_mode tests

# Run linter
ruff check voice_mode tests

# Fix linting issues
ruff check --fix voice_mode tests
```

- Keep imports organized (stdlib, third-party, local)
- Add type hints where appropriate
- Document functions with docstrings
- Follow existing patterns in the codebase

## Pre-commit Hooks

For automated code quality checks:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Commit Messages

Follow conventional commits format for clear project history:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions or changes
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

Examples:

- `feat: add support for custom voice models`
- `fix: resolve audio playback issue on macOS`
- `docs: update installation instructions`

## Pull Request Process

1. **Fork the repository** on GitHub OR create a branch
2. **Create your feature branch** from main
3. **Make changes with tests** - ensure new features have test coverage
4. **Run the full test suite** to verify nothing is broken
5. **Submit your pull request** with:
   - Clear title and description
   - Link to any related issues
   - Description of testing performed
   - Any breaking changes noted

## Debugging

For debugging instructions and troubleshooting, see the [Debugging section in the Development Setup Guide](docs/tutorials/development-setup.md#debugging).

## Common Development Tasks

For common tasks like building packages, updating dependencies, and running tests, see the [Common Development Tasks section](docs/tutorials/development-setup.md#common-development-tasks).

## Questions?

Feel free to open an issue if you have questions or need help getting started!
