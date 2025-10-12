# Voice MCP Makefile

.PHONY: help build-package build-dev test test-package publish-test publish release install dev-install clean build-voice-mode publish-voice-mode sync-tomls claude cursor docs docs-serve docs-build docs-check docs-deploy coverage coverage-html coverage-xml test-unit test-integration test-all test-parallel test-markers build-installer test-installer-ubuntu test-installer-fedora test-installer-all test-installer-ci test-installer-ubuntu-fast test-installer-fedora-fast test-installer-all-fast publish-installer-test publish-installer publish-voicemode-test

# Default target
help:
	@echo "Voice MCP Build Targets:"
	@echo ""
	@echo "Development targets:"
	@echo "  install       - Install package in normal mode"
	@echo "  dev-install   - Install package in editable mode with dev dependencies"
	@echo "  test          - Run unit tests with pytest"
	@echo "  clean         - Remove build artifacts and caches"
	@echo ""
	@echo "Testing & Coverage:"
	@echo "  test          - Run unit tests with pytest"
	@echo "  coverage      - Run tests with coverage report"
	@echo "  coverage-html - Generate and open HTML coverage report"
	@echo "  coverage-xml  - Generate XML coverage report (for CI)"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-integration - Run integration tests"
	@echo "  test-all      - Run all tests (including slow/manual)"
	@echo "  test-parallel - Run tests in parallel"
	@echo "  test-markers  - Show available test markers"
	@echo "  CLAUDE.md     - Generate CLAUDE.md with consolidated startup context"
	@echo ""
	@echo "Installer Testing & Publishing:"
	@echo "  build-installer                 - Build voicemode-install package"
	@echo "  test-installer-ubuntu           - Test on fresh Ubuntu clone (default)"
	@echo "  test-installer-fedora           - Test on fresh Fedora clone (default)"
	@echo "  test-installer-all              - Test on fresh clones of all platforms (default)"
	@echo "  test-installer-ubuntu-fast      - Test on existing Ubuntu VM (no clone)"
	@echo "  test-installer-fedora-fast      - Test on existing Fedora VM (no clone)"
	@echo "  test-installer-all-fast         - Test on existing VMs (no clone)"
	@echo "  test-installer-ci               - Test installer using Docker (CI mode)"
	@echo "  publish-installer-test          - Publish voicemode-install to TestPyPI"
	@echo "  publish-installer               - Publish voicemode-install to PyPI"
	@echo "  publish-voicemode-test          - Publish voice-mode to TestPyPI"
	@echo ""
	@echo "Python package targets:"
	@echo "  build-package - Build Python package for PyPI"
	@echo "  build-dev     - Build development package with auto-versioning"
	@echo "  test-package  - Test package installation"
	@echo "  publish-test  - Publish to TestPyPI"
	@echo "  publish       - Publish to PyPI"
	@echo ""
	@echo "Release targets:"
	@echo "  release       - Create a new release (tags, pushes, triggers GitHub workflow)"
	@echo ""
	@echo "Alternative package (voice-mode):"
	@echo "  build-voice-mode  - Build voice-mode package"
	@echo "  publish-voice-mode - Publish voice-mode to PyPI"
	@echo "  sync-tomls        - Sync pyproject.toml changes to pyproject-voice-mode.toml"
	@echo ""
	@echo "Documentation targets:"
	@echo "  docs-serve    - Serve documentation locally (http://localhost:8000)"
	@echo "  docs-build    - Build documentation site"
	@echo "  docs-check    - Check documentation for errors (strict mode)"
	@echo "  docs-deploy   - Deploy to ReadTheDocs (requires auth)"
	@echo ""
	@echo "  help          - Show this help message"

# Install package
install:
	@echo "Installing voice-mode..."
	uv pip install -e .
	@echo "Installation complete!"

# Install package with development dependencies
dev-install:
	@echo "Installing voice-mode with development dependencies..."
	uv pip install -e ".[dev,test]"
	@echo "Development installation complete!"

# Build Python package
build-package:
	@echo "Building Python package..."
	python -m build
	@echo "Package built successfully in dist/"

# Build development package with auto-versioning
build-dev:
	@echo "Building development package..."
	@# Save current version
	@cp voice_mode/__version__.py voice_mode/__version__.py.bak
	@# Get current version and append .dev suffix with timestamp
	@CURRENT_VERSION=$$(python -c "exec(open('voice_mode/__version__.py').read()); print(__version__)") && \
	DEV_VERSION="$$CURRENT_VERSION.dev$$(date +%Y%m%d%H%M%S)" && \
	echo "__version__ = \"$$DEV_VERSION\"" > voice_mode/__version__.py && \
	echo "Building version $$DEV_VERSION..." && \
	uv build || (mv voice_mode/__version__.py.bak voice_mode/__version__.py; exit 1)
	@# Restore original version
	@mv voice_mode/__version__.py.bak voice_mode/__version__.py
	@echo "Development package built successfully in dist/"

# Run unit tests
test:
	@echo "Running unit tests..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@echo "Running tests..."
	@uv run pytest tests/ -v --tb=short
	@echo "Tests completed!"

# Test package installation
test-package: build-package
	@echo "Testing package installation..."
	cd /tmp && \
	python -m venv test-env && \
	. test-env/bin/activate && \
	pip install $(CURDIR)/dist/voice_mode-*.whl && \
	voice-mode --help && \
	deactivate && \
	rm -rf test-env
	@echo "Package test successful!"

# Publish to TestPyPI
publish-test: build-package
	@echo "Publishing to TestPyPI..."
	@echo "Make sure you have configured ~/.pypirc with testpypi credentials"
	python -m twine upload --repository testpypi dist/*
	@echo "Published to TestPyPI. Install with:"
	@echo "  pip install --index-url https://test.pypi.org/simple/ voice-mode"

# Publish to PyPI
publish: build-package
	@echo "Publishing to PyPI..."
	@echo "Make sure you have configured ~/.pypirc with pypi credentials"
	python -m twine upload dist/*
	@echo "Published to PyPI. Install with:"
	@echo "  pip install voice-mode"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf dist/ build/ *.egg-info .pytest_cache __pycache__
	rm -rf htmlcov/ .coverage coverage.xml .coverage.*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete!"

# Release - Create a new release and tag
release:
	@echo "Creating a new release..."
	@echo ""
	@echo "Current version: $$(grep -E '^__version__ = ' voice_mode/__version__.py | cut -d'"' -f2)"
	@echo ""
	@read -p "Enter new version (e.g., 0.1.3): " version; \
	if [ -z "$$version" ]; then \
		echo "Error: Version cannot be empty"; \
		exit 1; \
	fi; \
	echo "Updating version to $$version..."; \
	sed -i.bak 's/^__version__ = .*/__version__ = "'$$version'"/' voice_mode/__version__.py && \
	rm voice_mode/__version__.py.bak; \
	echo "Updating server.json version..."; \
	sed -i.bak 's/"version": "[^"]*"/"version": "'$$version'"/' server.json && \
	rm server.json.bak; \
	echo "Updating CHANGELOG.md..."; \
	date=$$(date +%Y-%m-%d); \
	sed -i.bak "s/## \[Unreleased\]/## [Unreleased]\n\n## [$$version] - $$date/" CHANGELOG.md && \
	rm CHANGELOG.md.bak; \
	git add voice_mode/__version__.py server.json CHANGELOG.md && \
	git commit -m "chore: bump version to $$version" && \
	git tag -a "v$$version" -m "Release v$$version" && \
	echo "" && \
	echo "✅ Version bumped and tagged!" && \
	echo "" && \
	echo "Pushing to GitHub..." && \
	git push origin && \
	git push origin "v$$version" && \
	echo "" && \
	echo "🚀 Release pipeline triggered!" && \
	echo "" && \
	echo "GitHub Actions will now:" && \
	echo "1. Create a GitHub release with changelog" && \
	echo "2. Publish to PyPI" && \
	echo "" && \
	echo "Monitor progress at: https://github.com/mbailey/voice-mode/actions"

# Build voice-mode package
build-voice-mode:
	@echo "Building voice-mode package..."
	@# Temporarily swap pyproject files
	@mv pyproject.toml pyproject-voice-mode.toml.tmp
	@cp pyproject-voice-mode.toml pyproject.toml
	@# Build the package
	python -m build
	@# Restore original pyproject.toml
	@mv pyproject-voice-mode.toml.tmp pyproject.toml
	@echo "voice-mode package built successfully in dist/"

# Publish voice-mode to PyPI
publish-voice-mode: build-voice-mode
	@echo "Publishing voice-mode to PyPI..."
	@echo "Make sure you have configured ~/.pypirc with pypi credentials"
	@# Find the latest voice-mode wheel and sdist
	@latest_wheel=$$(ls -t dist/voice_mode-*.whl 2>/dev/null | head -1); \
	latest_sdist=$$(ls -t dist/voice_mode-*.tar.gz 2>/dev/null | head -1); \
	if [ -z "$$latest_wheel" ] || [ -z "$$latest_sdist" ]; then \
		echo "Error: voice-mode distribution files not found. Run 'make build-voice-mode' first."; \
		exit 1; \
	fi; \
	python -m twine upload "$$latest_wheel" "$$latest_sdist"
	@echo "Published to PyPI. Install with:"
	@echo "  pip install voice-mode"

# Generate CLAUDE.md from template
CLAUDE.md: CLAUDE.md.in GLOSSARY.md docs/tasks/README.md docs/tasks/key-insights.md docs/tasks/implementation-notes.md docs/configuration/environment.md
	@echo "Generating CLAUDE.md from template..."
	@# Start with the template
	@cp CLAUDE.md.in CLAUDE.md.tmp
	@# Replace timestamp
	@sed -i.bak "s/@TIMESTAMP@/$$(date -u +%Y-%m-%dT%H:%M:%SZ)/g" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak
	@# Process @include directives
	@while grep -q "@include " CLAUDE.md.tmp; do \
		file=$$(grep -m1 "@include " CLAUDE.md.tmp | sed 's/.*@include //'); \
		if [ -f "$$file" ]; then \
			sed -i.bak "/@include $$file/r $$file" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak; \
			sed -i.bak "/@include $$file/d" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak; \
		else \
			echo "Warning: Could not find $$file"; \
			sed -i.bak "s|@include $$file|[File not found: $$file]|" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak; \
		fi; \
	done
	@# Process @include-section directives (file, pattern, lines)
	@while grep -q "@include-section " CLAUDE.md.tmp; do \
		line=$$(grep -m1 "@include-section " CLAUDE.md.tmp); \
		file=$$(echo "$$line" | awk '{print $$2}'); \
		pattern=$$(echo "$$line" | awk '{print $$3}' | tr -d '"'); \
		lines=$$(echo "$$line" | awk '{print $$4}'); \
		if [ -f "$$file" ]; then \
			grep -A $$lines "$$pattern" "$$file" > include.tmp || true; \
			sed -i.bak "/@include-section $$file/r include.tmp" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak; \
			rm -f include.tmp; \
		fi; \
		sed -i.bak "/@include-section $$file/d" CLAUDE.md.tmp && rm CLAUDE.md.tmp.bak; \
	done
	@mv CLAUDE.md.tmp CLAUDE.md
	@echo "✅ CLAUDE.md generated successfully!"

# Prepare everything and start Claude
claude: CLAUDE.md
	@echo "Preparing to start Claude Code..."
	@echo ""
	@# Check if Claude is installed
	@if ! command -v claude >/dev/null 2>&1; then \
		echo "❌ Claude Code is not installed!"; \
		echo ""; \
		echo "Install with:"; \
		echo "  npm install -g @anthropic-ai/claude-code"; \
		exit 1; \
	fi
	@echo "✅ Claude Code is installed"
	@echo ""
	@# Check environment
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "⚠️  Warning: OPENAI_API_KEY is not set"; \
		echo "  Voice Mode requires this for TTS/STT"; \
		echo ""; \
	fi
	@# Start Claude
	@echo "Starting Claude Code..."
	@echo ""
	@claude converse

# Documentation targets
docs-serve:
	@echo "Starting documentation server at http://localhost:8000..."
	@echo ""
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
	@echo "Press Ctrl+C to stop the server"
	@.venv/bin/mkdocs serve

docs-build:
	@echo "Building documentation site..."
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
	@.venv/bin/mkdocs build
	@echo "Documentation built to site/ directory"

docs-check:
	@echo "Checking documentation for errors..."
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
	@echo ""
	@echo "Running strict documentation check..."
	@.venv/bin/mkdocs build --strict

docs-deploy:
	@echo "Deploying documentation to ReadTheDocs..."
	@echo "Note: This requires ReadTheDocs authentication"
	@# ReadTheDocs typically auto-builds from GitHub
	@echo "Push to main branch to trigger ReadTheDocs build"
	@echo "Or configure manual deployment in ReadTheDocs dashboard"

# Run tests with coverage report
coverage:
	@echo "Running tests with coverage..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@echo "Running tests with coverage..."
	@uv run pytest tests --cov --cov-report=html --cov-report=term
	@echo ""
	@echo "✅ Coverage report generated!"
	@echo "   Terminal report shown above"
	@echo "   HTML report: htmlcov/index.html"
	@echo ""
	@echo "Opening HTML coverage report..."
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html manually"

# Generate HTML coverage report
coverage-html: coverage
	@echo "Opening coverage report in browser..."
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html manually"

# Generate XML coverage report for CI
coverage-xml:
	@echo "Generating XML coverage report..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@uv run pytest tests --cov --cov-report=xml
	@echo "XML coverage report generated: coverage.xml"

# Run unit tests only
test-unit:
	@echo "Running unit tests..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@uv run pytest tests -v -m "unit or not integration"

# Run integration tests only
test-integration:
	@echo "Running integration tests..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@uv run pytest tests -v -m "integration"

# Run all tests (including slow and manual)
test-all:
	@echo "Running all tests..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@echo "Installing test dependencies..."
	@uv pip install -e ".[test]" -q
	@uv run pytest tests -v

# Run tests in parallel (requires pytest-xdist)
test-parallel:
	@echo "Installing pytest-xdist..."
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	@uv pip install -e ".[test]" -q
	@uv pip install pytest-xdist -q
	@echo "Running tests in parallel..."
	@uv run pytest tests -n auto -v

# Show available test markers
test-markers:
	@echo "Available test markers:"
	@echo "  unit        - Fast, isolated unit tests"
	@echo "  integration - Tests that interact with services"
	@echo "  slow        - Tests that take > 1s"
	@echo "  manual      - Tests requiring human interaction"
	@echo ""
	@echo "Usage: uv run pytest -m 'marker_name'"
	@echo "Example: uv run pytest -m 'not slow'"

# Build voicemode-install package
build-installer:
	@echo "Building voicemode-install package..."
	@cd installer && uv build
	@echo "✅ Package built: installer/dist/"
	@ls -lh installer/dist/

# Test installer on fresh Ubuntu clone (default)
test-installer-ubuntu: build-installer
	@echo "Testing installer on fresh Ubuntu clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	python3 scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart --clone-fresh

# Test installer on fresh Fedora clone (default)
test-installer-fedora: build-installer
	@echo "Testing installer on fresh Fedora clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	python3 scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart --clone-fresh

# Test installer on fresh clones of all platforms (default)
test-installer-all: build-installer
	@echo "Testing installer on fresh clones of all platforms..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	echo ""; \
	echo "=== Testing Ubuntu (fresh clone) ==="; \
	python3 scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart --clone-fresh || true; \
	echo ""; \
	echo "=== Testing Fedora (fresh clone) ==="; \
	python3 scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart --clone-fresh || true

# Test installer using Docker (CI mode)
test-installer-ci: build-installer
	@echo "Testing installer with Docker..."
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "❌ Docker is not installed!"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	echo ""; \
	echo "=== Testing Ubuntu (Docker) ==="; \
	python3 scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend docker || true; \
	echo ""; \
	echo "=== Testing Fedora (Docker) ==="; \
	python3 scripts/test_installer.py fedora --wheel "$$WHEEL" --backend docker || true

# Test installer on existing Ubuntu VM (fast, no clone)
test-installer-ubuntu-fast: build-installer
	@echo "Testing installer on existing Ubuntu VM..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	python3 scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart

# Test installer on existing Fedora VM (fast, no clone)
test-installer-fedora-fast: build-installer
	@echo "Testing installer on existing Fedora VM..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	python3 scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart

# Test installer on existing VMs (fast, no clone)
test-installer-all-fast: build-installer
	@echo "Testing installer on existing VMs..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voicemode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	echo ""; \
	echo "=== Testing Ubuntu ==="; \
	python3 scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart || true; \
	echo ""; \
	echo "=== Testing Fedora ==="; \
	python3 scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart || true

# Publish voicemode-install to TestPyPI
publish-installer-test: build-installer
	@echo "Publishing voicemode-install to TestPyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo ""; \
		echo "Get a token from https://test.pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-token\""; \
		exit 1; \
	fi
	@cd installer && uv publish --index-url https://test.pypi.org/legacy/
	@echo ""
	@echo "✅ Published to TestPyPI!"
	@echo ""
	@echo "Test installation with:"
	@echo "  uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ voicemode-install --dry-run"

# Publish voicemode-install to PyPI
publish-installer: build-installer test-installer-all
	@echo "Publishing voicemode-install to PyPI..."
	@echo ""
	@echo "⚠️  WARNING: This will publish to PRODUCTION PyPI!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" != "yes" ]; then \
		echo "Aborted."; \
		exit 1; \
	fi
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo ""; \
		echo "Get a token from https://pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-token\""; \
		exit 1; \
	fi
	@cd installer && uv publish
	@echo ""
	@echo "✅ Published to PyPI!"
	@echo ""
	@echo "Install with:"
	@echo "  uvx voicemode-install"

# Publish voice-mode to TestPyPI
publish-voicemode-test: build-package
	@echo "Publishing voice-mode to TestPyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo ""; \
		echo "Get a token from https://test.pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-token\""; \
		exit 1; \
	fi
	@uv publish --index-url https://test.pypi.org/legacy/
	@echo ""
	@echo "✅ Published to TestPyPI!"
	@echo ""
	@echo "Test installation with:"
	@echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ voice-mode"
