# Voice MCP Makefile

.PHONY: help build-package build-dev test test-package publish-test publish release install dev-install clean build-voice-mode publish-voice-mode sync-tomls claude cursor docs docs-serve docs-build docs-check docs-deploy

# Default target
help:
	@echo "Voice MCP Build Targets:"
	@echo ""
	@echo "Development targets:"
	@echo "  install       - Install package in normal mode"
	@echo "  dev-install   - Install package in editable mode with dev dependencies"
	@echo "  test          - Run unit tests with pytest"
	@echo "  clean         - Remove build artifacts and caches"
	@echo "  CLAUDE.md     - Generate CLAUDE.md with consolidated startup context"
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
	@echo "Web Dashboard targets:"
	@echo "  web-install   - Install web dashboard dependencies"
	@echo "  web-dev       - Start both backend and frontend in tmux"
	@echo "  web-backend   - Start only the FastAPI backend server (port 8080)"
	@echo "  web-frontend  - Start only the React frontend dev server (port 5175)"
	@echo "  web-stop      - Stop all web servers"
	@echo "  web-logs      - Show backend server logs"
	@echo "  web-test      - Test if the API is responding"
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
	echo "Updating CHANGELOG.md..."; \
	date=$$(date +%Y-%m-%d); \
	sed -i.bak "s/## \[Unreleased\]/## [Unreleased]\n\n## [$$version] - $$date/" CHANGELOG.md && \
	rm CHANGELOG.md.bak; \
	git add voice_mode/__version__.py CHANGELOG.md && \
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

# Web Dashboard targets
web-backend:
	@echo "Starting FastAPI backend server on port 8080..."
	@cd web/backend && uv run python test_backend.py

web-frontend:
	@echo "Starting React frontend dev server..."
	@cd web/frontend && npm run dev

web-install:
	@echo "Installing web dashboard dependencies..."
	@echo "Installing backend dependencies..."
	@uv pip install fastapi uvicorn
	@echo "Installing frontend dependencies..."
	@cd web/frontend && npm install
	@echo "✅ Web dashboard dependencies installed!"

web-dev:
	@echo "Starting both web servers in tmux..."
	@# Check if tmux session exists
	@if tmux has-session -t cora 2>/dev/null; then \
		# Create new window in existing session; \
		tmux new-window -t cora -n web-dev 2>/dev/null || tmux select-window -t cora:web-dev; \
	else \
		# Create new session if doesn't exist; \
		tmux new-session -d -s cora -n web-dev; \
	fi
	@# Split horizontally for backend and frontend
	@tmux split-window -h -t cora:web-dev 2>/dev/null || true
	@# Start backend in left pane
	@tmux send-keys -t cora:web-dev.0 "cd $(PWD)/web/backend && uv run python test_backend.py" Enter
	@# Start frontend in right pane  
	@tmux send-keys -t cora:web-dev.1 "cd $(PWD)/web/frontend && npm run dev" Enter
	@echo ""
	@echo "✅ Web servers starting in tmux window 'web-dev'"
	@echo ""
	@echo "  Backend:  http://localhost:8080/api/health"
	@echo "  Frontend: http://localhost:5175"
	@echo "  API Docs: http://localhost:8080/docs"
	@echo ""
	@echo "Use 'tmux attach -t cora' to view the servers"

web-stop:
	@echo "Stopping web servers..."
	@pkill -f "test_backend.py" 2>/dev/null || true
	@pkill -f "vite" 2>/dev/null || true
	@echo "✅ Web servers stopped"

web-logs:
	@echo "Showing web backend logs..."
	@tail -f web/backend/test.log 2>/dev/null || tail -f web/backend/backend.log 2>/dev/null || echo "No log files found"

web-test:
	@echo "Testing web API..."
	@curl -s http://localhost:8080/api/health | jq . || echo "Backend not running or jq not installed"
