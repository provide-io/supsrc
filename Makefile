# Makefile for supsrc development

.PHONY: help setup test lint typecheck coverage clean build all test-unit test-integration test-workflow run-watch run-tui docs-setup docs-build docs-serve docs-clean

# Default target
help:
	@echo "Available targets:"
	@echo "  setup       - Create virtual environment and install dependencies"
	@echo "  test        - Run full test suite"
	@echo "  lint        - Run ruff format and check with fixes"
	@echo "  typecheck   - Run type checking"
	@echo "  coverage    - Run tests with coverage report"
	@echo "  clean       - Remove virtual environment and cache files"
	@echo "  build       - Build the package"
	@echo "  all         - Run lint, typecheck, and tests"
	@echo ""
	@echo "Test-specific targets:"
	@echo "  test-unit        - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-workflow    - Test the new workflow package"
	@echo "  test-feed        - Test the feed_table package"
	@echo ""
	@echo "Running targets:"
	@echo "  run-watch   - Run supsrc in watch mode"
	@echo "  run-tui     - Run supsrc with TUI"

# Create virtual environment and install dependencies
setup:
	@echo "Creating virtual environment..."
	uv venv
	@echo "Installing dependencies..."
	uv sync --all-extras
	@echo "Setup complete! Activate with: source .venv/bin/activate"

# Run full test suite
test:
	@echo "Running test suite..."
	source .venv/bin/activate && python -m pytest

# Run unit tests only
test-unit:
	@echo "Running unit tests..."
	source .venv/bin/activate && python -m pytest tests/unit/

# Run integration tests only
test-integration:
	@echo "Running integration tests..."
	source .venv/bin/activate && python -m pytest tests/integration/

# Test the new workflow package specifically
test-workflow:
	@echo "Running workflow package tests..."
	source .venv/bin/activate && python -m pytest tests/unit/workflow/ -v

# Test the feed_table package specifically
test-feed:
	@echo "Running feed_table package tests..."
	source .venv/bin/activate && python -m pytest -k "feed_table" -v

# Run ruff format and check with fixes
lint:
	@echo "Running ruff format..."
	source .venv/bin/activate && ruff format src/ tests/
	@echo "Running ruff check with fixes..."
	source .venv/bin/activate && ruff check src/ tests/ --fix --unsafe-fixes

# Run type checking
typecheck:
	@echo "Running type checking..."
	source .venv/bin/activate && mypy src/

# Run tests with coverage report
coverage:
	@echo "Running tests with coverage..."
	source .venv/bin/activate && python -m pytest --cov=src/supsrc --cov-report=html --cov-report=term

# Remove virtual environment and cache files
clean:
	@echo "Cleaning up..."
	rm -rf .venv/
	rm -rf .mypy_cache/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Build the package
build:
	@echo "Building package..."
	source .venv/bin/activate && uv build

# Run all quality checks
all: lint typecheck test
	@echo "All checks completed!"

# Run supsrc in watch mode
run-watch:
	@echo "Starting supsrc in watch mode..."
	source .venv/bin/activate && supsrc watch

# Run supsrc with TUI
run-tui:
	@echo "Starting supsrc with TUI..."
	source .venv/bin/activate && supsrc sui
# Documentation targets
docs-setup:
	@python -c "from provide.foundry.config import extract_base_mkdocs; from pathlib import Path; extract_base_mkdocs(Path('.'))"

docs-build: docs-setup
	@mkdocs build

docs-serve: docs-setup
	@mkdocs serve

docs-clean:
	@rm -rf site .provide
