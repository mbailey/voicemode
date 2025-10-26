# Voice MCP Makefile

.PHONY: help install dev-install clean \
	build build-package build-installer build-dev \
	test test-package test-all test-unit test-integration test-parallel test-markers \
	coverage coverage-html coverage-xml \
	publish publish-package publish-installer \
	publish-test publish-package-test publish-installer-test \
	release release-package release-installer \
	docs-serve docs-build docs-check docs-deploy \
	clean-dist clean-package clean-installer \
	test-installer-ubuntu test-installer-fedora test-installer-all test-installer-ci \
	test-installer-pypi test-installer-pypi-ubuntu test-installer-pypi-fedora \
	test-installer-pypi-all \
	vm-ubuntu vm-fedora vm-macos vm-ubuntu-quick vm-fedora-quick vm-macos-quick vm-clean vm-list

# Default target
help:
	@echo "Voice MCP Build Targets:"
	@echo ""
	@echo "Development:"
	@echo "  install       - Install package in normal mode"
	@echo "  dev-install   - Install package in editable mode with dev dependencies"
	@echo "  clean         - Remove all build artifacts and caches"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run unit tests with pytest"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-integration - Run integration tests"
	@echo "  test-all      - Run all tests (including slow/manual)"
	@echo "  test-parallel - Run tests in parallel"
	@echo "  test-markers  - Show available test markers"
	@echo ""
	@echo "Coverage:"
	@echo "  coverage      - Run tests with coverage report"
	@echo "  coverage-html - Generate and open HTML coverage report"
	@echo "  coverage-xml  - Generate XML coverage report (for CI)"
	@echo ""
	@echo "Building:"
	@echo "  build         - Build both packages"
	@echo "  build-package - Build voice-mode package only"
	@echo "  build-installer - Build voice-mode-install package only"
	@echo "  build-dev     - Build development package with auto-versioning"
	@echo "  test-package  - Test package installation"
	@echo ""
	@echo "Publishing to PyPI:"
	@echo "  publish       - Publish both packages to PyPI"
	@echo "  publish-package - Publish voice-mode package to PyPI"
	@echo "  publish-installer - Publish voice-mode-install to PyPI"
	@echo ""
	@echo "Publishing to TestPyPI:"
	@echo "  publish-test  - Publish both packages to TestPyPI"
	@echo "  publish-package-test - Publish voice-mode to TestPyPI"
	@echo "  publish-installer-test - Publish voice-mode-install to TestPyPI"
	@echo ""
	@echo "Release Management:"
	@echo "  release       - Create unified release for both packages"
	@echo "  release-package - Release voice-mode package only"
	@echo "  release-installer - Release voice-mode-install package only"
	@echo ""
	@echo "Installer Testing (Local Build):"
	@echo "  test-installer-ubuntu   - Test on fresh Ubuntu clone"
	@echo "  test-installer-fedora   - Test on fresh Fedora clone"
	@echo "  test-installer-all      - Test on fresh clones of all platforms"
	@echo "  test-installer-ci       - Test installer using Docker"
	@echo ""
	@echo "Installer Testing (From PyPI):"
	@echo "  test-installer-pypi        - Test latest from PyPI (all platforms)"
	@echo "  test-installer-pypi-ubuntu - Test latest from PyPI on Ubuntu"
	@echo "  test-installer-pypi-fedora - Test latest from PyPI on Fedora"
	@echo "  test-installer-pypi-all    - Test latest from PyPI (fresh clones)"
	@echo ""
	@echo "Documentation:"
	@echo "  docs-serve    - Serve documentation locally (http://localhost:8000)"
	@echo "  docs-build    - Build documentation site"
	@echo "  docs-check    - Check documentation for errors (strict mode)"
	@echo "  docs-deploy   - Deploy to ReadTheDocs (requires auth)"
	@echo ""
	@echo "Manual VM Testing:"
	@echo "  vm-ubuntu     - Start fresh Ubuntu VM and show SSH command"
	@echo "  vm-fedora     - Start fresh Fedora VM and show SSH command"
	@echo "  vm-macos      - Start fresh macOS VM and show SSH command"
	@echo "  vm-ubuntu-quick  - Start persistent Ubuntu VM (faster)"
	@echo "  vm-fedora-quick  - Start persistent Fedora VM (faster)"
	@echo "  vm-macos-quick   - Start persistent macOS VM (faster)"
	@echo "  vm-clean      - Clean up persistent VMs"
	@echo "  vm-list       - List all Tart VMs"

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
	@echo "Building voice-mode package..."
	@uv build
	@echo "✅ Package built: dist/"
	@ls -lh dist/

# Build development package with auto-versioning
build-dev:
	@echo "Building development package..."
	@# Save current version
	@cp voice_mode/__version__.py voice_mode/__version__.py.bak
	@# Get current version and append .dev suffix with timestamp
	@CURRENT_VERSION=$$(uv run python -c "exec(open('voice_mode/__version__.py').read()); print(__version__)") && \
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

# Test package installation (FIXED: Now uses UV)
test-package: build-package
	@echo "Testing package installation..."
	@cd /tmp && \
	uv venv test-env && \
	. test-env/bin/activate && \
	uv pip install $(CURDIR)/dist/voice_mode-*.whl && \
	voice-mode --help && \
	deactivate && \
	rm -rf test-env
	@echo "Package test successful!"

# Publish to TestPyPI - unified target for both packages
publish-test: clean-dist build
	@echo "Publishing both packages to TestPyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo "Get a token from https://test.pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-test-token\""; \
		exit 1; \
	fi
	@uv publish --index-url https://test.pypi.org/legacy/
	@cd installer && uv publish --index-url https://test.pypi.org/legacy/
	@echo "✅ Both packages published to TestPyPI!"

# Publish voice-mode package to TestPyPI
publish-package-test:
	@echo "Cleaning voice-mode dist..."
	@rm -rf dist/*.whl dist/*.tar.gz
	@$(MAKE) build-package
	@echo "Publishing voice-mode to TestPyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo "Get a token from https://test.pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-test-token\""; \
		exit 1; \
	fi
	@uv publish --index-url https://test.pypi.org/legacy/
	@echo "✅ Published to TestPyPI!"

# Publish to PyPI - unified target for both packages
publish: clean-dist build
	@echo "Publishing both packages to PyPI..."
	@echo ""
	@echo "⚠️  WARNING: This will publish BOTH packages to PRODUCTION PyPI!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" != "yes" ]; then \
		echo "Aborted."; \
		exit 1; \
	fi
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo "Get a token from https://pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-token\""; \
		exit 1; \
	fi
	@echo ""
	@echo "Publishing voice-mode..."
	@uv publish
	@echo "✅ voice-mode published!"
	@echo ""
	@echo "Publishing voice-mode-install..."
	@cd installer && uv publish
	@echo "✅ voice-mode-install published!"

# Publish voice-mode package only
publish-package:
	@echo "Cleaning voice-mode dist..."
	@rm -rf dist/*.whl dist/*.tar.gz
	@$(MAKE) build-package
	@echo "Publishing voice-mode to PyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		exit 1; \
	fi
	@uv publish
	@echo "✅ voice-mode published!"

# Publish voice-mode-install package only
publish-installer:
	@echo "Cleaning installer dist..."
	@rm -rf installer/dist/*.whl installer/dist/*.tar.gz
	@$(MAKE) build-installer
	@echo "Publishing voice-mode-install to PyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		exit 1; \
	fi
	@cd installer && uv publish
	@echo "✅ voice-mode-install published!"

# Clean build artifacts - Three-tier approach for flexibility
clean:
	@echo "Cleaning all build artifacts..."
	@$(MAKE) clean-package
	@$(MAKE) clean-installer
	@echo "✅ All build artifacts cleaned!"

clean-package:
	@echo "Cleaning voice-mode build artifacts..."
	@rm -rf dist/ build/ *.egg-info .pytest_cache __pycache__
	@rm -rf htmlcov/ .coverage coverage.xml .coverage.*
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

clean-installer:
	@echo "Cleaning voice-mode-install build artifacts..."
	@rm -rf installer/dist/*.whl installer/dist/*.tar.gz

# Clean only distribution artifacts (for publish safety)
clean-dist:
	@echo "Cleaning distribution artifacts..."
	@rm -rf dist/*.whl dist/*.tar.gz
	@rm -rf installer/dist/*.whl installer/dist/*.tar.gz
	@echo "✅ Distribution artifacts cleaned!"

# Release targets - Create a new release and tag
release:
	@echo "Creating unified release for voice-mode and voice-mode-install..."
	@echo ""
	@echo "Current version: $$(uv run python scripts/release.py --current)"
	@echo ""
	@read -p "Enter new version (e.g., 5.1.5): " version; \
	if [ -z "$$version" ]; then \
		echo "Error: Version cannot be empty"; \
		exit 1; \
	fi; \
	uv run python scripts/release.py $$version

release-package:
	@echo "Creating release for voice-mode package only..."
	@echo ""
	@echo "Current version: $$(uv run python scripts/release.py --current)"
	@echo ""
	@read -p "Enter new version (e.g., 5.1.5): " version; \
	if [ -z "$$version" ]; then \
		echo "Error: Version cannot be empty"; \
		exit 1; \
	fi; \
	uv run python scripts/release.py $$version --package package

release-installer:
	@echo "Creating release for voice-mode-install package only..."
	@echo ""
	@echo "Current version: $$(uv run python scripts/release.py --current)"
	@echo ""
	@read -p "Enter new version (e.g., 5.1.5): " version; \
	if [ -z "$$version" ]; then \
		echo "Error: Version cannot be empty"; \
		exit 1; \
	fi; \
	uv run python scripts/release.py $$version --package installer

# Documentation targets (FIXED: Now uses uv run python)
docs-serve:
	@echo "Starting documentation server at http://localhost:8000..."
	@echo ""
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@uv run python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
	@echo "Press Ctrl+C to stop the server"
	@.venv/bin/mkdocs serve

docs-build:
	@echo "Building documentation site..."
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@uv run python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
	@.venv/bin/mkdocs build
	@echo "Documentation built to site/ directory"

docs-check:
	@echo "Checking documentation for errors..."
	@# Install docs dependencies using uv
	@echo "Installing documentation dependencies..."
	@uv pip install -e ".[docs]"
	@# Process README for docs
	@uv run python scripts/process-readme-for-docs.py README.md docs/README_PROCESSED.md
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

# Build voice-mode-install package (always clean first to prevent old artifacts)
build-installer: clean-installer
	@echo "Syncing dependencies.yaml to installer..."
	@bash scripts/sync-dependencies.sh
	@echo "Building voice-mode-install package..."
	@cd installer && uv build
	@echo "✅ Package built: installer/dist/"
	@ls -lh installer/dist/

# Unified build target for both packages
build: build-package build-installer
	@echo "✅ Both packages built successfully!"

# Run installer locally to preview logo and output
run-installer:
	@echo "Running voice-mode-install from source..."
	@cd installer && uv run voice-mode-install --dry-run --non-interactive 2>&1 | head -30 || true

# Test installer on fresh Ubuntu clone (default)
test-installer-ubuntu: build-installer
	@echo "Testing installer on fresh Ubuntu clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voice_mode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	uv run python scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart --clone-fresh

# Test installer on fresh Fedora clone (default)
test-installer-fedora: build-installer
	@echo "Testing installer on fresh Fedora clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voice_mode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	uv run python scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart --clone-fresh

# Test installer on fresh clones of all platforms (default)
test-installer-all: build-installer
	@echo "Testing installer on fresh clones of all platforms..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voice_mode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	echo ""; \
	echo "=== Testing Ubuntu (fresh clone) ==="; \
	uv run python scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend tart --clone-fresh || true; \
	echo ""; \
	echo "=== Testing Fedora (fresh clone) ==="; \
	uv run python scripts/test_installer.py fedora --wheel "$$WHEEL" --backend tart --clone-fresh || true

# Test installer using Docker (CI mode)
test-installer-ci: build-installer
	@echo "Testing installer with Docker..."
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "❌ Docker is not installed!"; \
		exit 1; \
	fi
	@WHEEL=$$(ls -t installer/dist/voice_mode_install-*.whl | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "❌ Wheel file not found. Run 'make build-installer' first."; \
		exit 1; \
	fi; \
	echo "Using wheel: $$WHEEL"; \
	echo ""; \
	echo "=== Testing Ubuntu (Docker) ==="; \
	uv run python scripts/test_installer.py ubuntu --wheel "$$WHEEL" --backend docker || true; \
	echo ""; \
	echo "=== Testing Fedora (Docker) ==="; \
	uv run python scripts/test_installer.py fedora --wheel "$$WHEEL" --backend docker || true

# Publish voice-mode-install to TestPyPI
publish-installer-test:
	@echo "Cleaning installer dist..."
	@rm -rf installer/dist/*.whl installer/dist/*.tar.gz
	@$(MAKE) build-installer
	@echo "Publishing voice-mode-install to TestPyPI..."
	@if [ -z "$$UV_PUBLISH_TOKEN" ]; then \
		echo "❌ UV_PUBLISH_TOKEN not set!"; \
		echo "Get a token from https://test.pypi.org/manage/account/token/"; \
		echo "Then set: export UV_PUBLISH_TOKEN=\"pypi-your-test-token\""; \
		exit 1; \
	fi
	@cd installer && uv publish --index-url https://test.pypi.org/legacy/
	@echo "✅ Published to TestPyPI!"

# Manual VM Testing - Start fresh VMs and show SSH command
vm-ubuntu:
	@echo "Starting fresh Ubuntu VM..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@echo "Cleaning up any existing manual-ubuntu VM..."
	@tart delete manual-ubuntu 2>/dev/null || true
	@echo "Creating fresh Ubuntu VM..."
	@tart clone ghcr.io/cirruslabs/ubuntu:latest manual-ubuntu && \
	tart run --no-graphics manual-ubuntu >/dev/null 2>&1 & \
	echo "Waiting for VM to start..." && \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-ubuntu)" && \
	echo "" && \
	echo "   Username: admin" && \
	echo "   Password: admin" && \
	echo "" && \
	echo "To stop the VM: tart stop manual-ubuntu" && \
	echo "To delete the VM: tart delete manual-ubuntu"

vm-fedora:
	@echo "Starting fresh Fedora VM..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@echo "Cleaning up any existing manual-fedora VM..."
	@tart delete manual-fedora 2>/dev/null || true
	@echo "Creating fresh Fedora VM..."
	@tart clone ghcr.io/cirruslabs/fedora:latest manual-fedora && \
	tart run --no-graphics manual-fedora >/dev/null 2>&1 & \
	echo "Waiting for VM to start..." && \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-fedora)" && \
	echo "" && \
	echo "   Username: admin" && \
	echo "   Password: admin" && \
	echo "" && \
	echo "To stop the VM: tart stop manual-fedora" && \
	echo "To delete the VM: tart delete manual-fedora"

vm-macos:
	@echo "Starting fresh macOS VM..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@echo "Cleaning up any existing manual-macos VM..."
	@tart delete manual-macos 2>/dev/null || true
	@echo "Creating fresh macOS VM..."
	@tart clone ghcr.io/cirruslabs/macos-tahoe-base:latest manual-macos && \
	tart run --no-graphics manual-macos >/dev/null 2>&1 & \
	echo "Waiting for VM to start..." && \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-macos)" && \
	echo "" && \
	echo "   Username: admin" && \
	echo "   Password: admin" && \
	echo "" && \
	echo "To stop the VM: tart stop manual-macos" && \
	echo "To delete the VM: tart delete manual-macos"

# Quick VM shell access (reuses existing VMs for faster startup)
vm-ubuntu-quick:
	@echo "Starting Ubuntu VM (quick mode - reuses existing VM)..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		exit 1; \
	fi
	@if ! tart list | grep -q "manual-ubuntu"; then \
		echo "Creating VM: manual-ubuntu"; \
		tart clone ghcr.io/cirruslabs/ubuntu:latest manual-ubuntu; \
	else \
		echo "Using existing manual-ubuntu VM"; \
	fi
	@tart run --no-graphics manual-ubuntu >/dev/null 2>&1 & \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-ubuntu)" && \
	echo "" && \
	echo "   Username: admin, Password: admin"

vm-fedora-quick:
	@echo "Starting Fedora VM (quick mode - reuses existing VM)..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		exit 1; \
	fi
	@if ! tart list | grep -q "manual-fedora"; then \
		echo "Creating VM: manual-fedora"; \
		tart clone ghcr.io/cirruslabs/fedora:latest manual-fedora; \
	else \
		echo "Using existing manual-fedora VM"; \
	fi
	@tart run --no-graphics manual-fedora >/dev/null 2>&1 & \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-fedora)" && \
	echo "" && \
	echo "   Username: admin, Password: admin"

vm-macos-quick:
	@echo "Starting macOS VM (quick mode - reuses existing VM)..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		exit 1; \
	fi
	@if ! tart list | grep -q "manual-macos"; then \
		echo "Creating VM: manual-macos"; \
		tart clone ghcr.io/cirruslabs/macos-tahoe-base:latest manual-macos; \
	else \
		echo "Using existing manual-macos VM"; \
	fi
	@tart run --no-graphics manual-macos >/dev/null 2>&1 & \
	sleep 5 && \
	echo "" && \
	echo "✅ VM started! To connect:" && \
	echo "" && \
	echo "   ssh admin@$$(tart ip manual-macos)" && \
	echo "" && \
	echo "   Username: admin, Password: admin"

# Clean up manual VMs
vm-clean:
	@echo "Cleaning up manual VMs..."
	@tart delete manual-ubuntu 2>/dev/null || echo "  manual-ubuntu not found"
	@tart delete manual-fedora 2>/dev/null || echo "  manual-fedora not found"
	@tart delete manual-macos 2>/dev/null || echo "  manual-macos not found"
	@echo "✅ Manual VMs cleaned up"

# List all Tart VMs
vm-list:
	@echo "Available Tart VMs:"
	@tart list

# Test installer from PyPI - default target tests all platforms
test-installer-pypi: test-installer-pypi-all

# Test installer from PyPI on Ubuntu (fresh clone)
test-installer-pypi-ubuntu:
	@echo "Testing latest voice-mode-install from PyPI on fresh Ubuntu clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@uv run python scripts/test_installer.py ubuntu --pypi --backend tart --clone-fresh

# Test installer from PyPI on Fedora (fresh clone)
test-installer-pypi-fedora:
	@echo "Testing latest voice-mode-install from PyPI on fresh Fedora clone..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@uv run python scripts/test_installer.py fedora --pypi --backend tart --clone-fresh

# Test installer from PyPI on all platforms (fresh clones)
test-installer-pypi-all:
	@echo "Testing latest voice-mode-install from PyPI on fresh clones of all platforms..."
	@if ! command -v tart >/dev/null 2>&1; then \
		echo "❌ Tart is not installed!"; \
		echo "Install from: https://github.com/cirruslabs/tart"; \
		exit 1; \
	fi
	@echo ""
	@echo "=== Testing Ubuntu (fresh clone) ==="; \
	uv run python scripts/test_installer.py ubuntu --pypi --backend tart --clone-fresh || true; \
	echo ""; \
	echo "=== Testing Fedora (fresh clone) ==="; \
	uv run python scripts/test_installer.py fedora --pypi --backend tart --clone-fresh || true