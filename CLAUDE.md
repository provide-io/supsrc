# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`supsrc` is an automated Git commit/push utility that monitors filesystem events and performs Git operations based on configurable rules. It provides effortless checkpointing and synchronization for developers, automatically committing changes after periods of inactivity or specific save counts.

## Development Commands

### Build and Development Setup
```bash
# Install dependencies using uv (fast Python package manager)
uv venv
source .venv/bin/activate
uv pip install -e ".[tui]"  # Install in dev mode with TUI support

# Setup development environment (comprehensive setup)
source env.sh
```

### Testing
```bash
# Run all tests (152 test cases)
uv run pytest

# Run tests with coverage (target: 85% minimum)
uv run pytest --cov

# Run specific test categories
uv run pytest -m "not slow"        # Skip slow tests
uv run pytest -m integration        # Only integration tests
uv run pytest tests/unit/           # Only unit tests

# Run a single test file
uv run pytest tests/unit/test_orchestrator.py

# Run a specific test
uv run pytest tests/unit/test_orchestrator.py::test_specific_function
```

### Code Quality
```bash
# Linting and formatting (using ruff)
uv run ruff check .      # Check for linting issues
uv run ruff format .     # Auto-format code

# Type checking
uv run pyre check        # Run Pyre type checker
```

### Running the Application
```bash
# Start monitoring repositories
uv run supsrc watch              # Standard console mode
uv run supsrc watch --tui        # With Terminal UI
uv run supsrc tail               # Headless mode (no terminal control)

# Configuration commands
uv run supsrc config show        # Display current configuration
uv run supsrc watch -c path/to/config.toml  # Use specific config file
```

## Architecture Overview

### Layered Architecture

The codebase follows a clean layered architecture with clear separation of concerns:

1. **CLI Layer** (`src/supsrc/cli/`) - Command-line interface and entry points
   - Entry point: `main.py:cli()` function
   - Commands: `watch_cmds.py`, `tail_cmds.py`, `config_cmds.py`

2. **Runtime Layer** (`src/supsrc/runtime/`) - Core application orchestration
   - `orchestrator.py` - Main coordination logic for file monitoring and Git operations
   - `action_handler.py` - Executes Git actions (stage, commit, push)
   - `event_processor.py` - Processes filesystem events through rule engine
   - `tui_interface.py` - Optional Terminal UI integration

3. **Engine Layer** (`src/supsrc/engines/`) - Pluggable repository engines
   - Protocol-based design allowing different VCS backends
   - `git/` subdirectory contains modular Git engine implementation
   - Components: `client.py`, `operations.py`, `staging.py`, `status.py`

4. **Configuration Layer** (`src/supsrc/config/`) - Strongly-typed configuration
   - `models.py` - Attrs-based data models for configuration
   - `loader.py` - TOML configuration loading and validation with cattrs

5. **Monitoring Layer** (`src/supsrc/monitor/`) - Filesystem event monitoring
   - `service.py` - Watchdog-based file monitoring service
   - `events.py` - Event type definitions
   - `handler.py` - Event handling and routing logic

### Key Design Patterns

- **Protocol-Based Interfaces**: Uses Python protocols for pluggable engines and rules, enabling extensibility
- **Async/Await Architecture**: Built on asyncio for concurrent file monitoring and Git operations
- **Event-Driven System**: Filesystem changes trigger rule evaluation through an event queue
- **Structured Configuration**: TOML configs with strong typing via attrs/cattrs
- **Structured Logging**: JSON-structured logging via structlog for observability

### Core Flow
```
File Changes → Watchdog → Event Queue → Rule Engine → Git Engine → Actions
                                    ↓
                              TUI Interface ← State Management
```

### Rule System Architecture

Rules determine when to trigger Git operations:
- **Inactivity Rules**: Trigger after configurable periods of no file changes
- **Save Count Rules**: Trigger after specified number of save events
- **Manual Rules**: Disable automatic triggers for external control

### Git Engine Features

- Smart staging respecting `.gitignore` patterns via pathspec
- Template-based commit messages with placeholders
- Multi-authentication support (SSH agent, HTTPS tokens)
- Optional automatic pushing to configured remotes
- Thread pool executors for non-blocking Git operations in UI mode

## Testing Strategy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions and Git operations
- **Test Fixtures**: Shared fixtures in `tests/conftest.py`
- **Async Testing**: Uses pytest-asyncio for testing async code
- **Mocking**: pytest-mock for isolating components
- **Property Testing**: Hypothesis for edge case discovery
- **Time Mocking**: freezegun for testing time-based rules

## Important Notes

- Requires Python 3.11+ for modern Python features
- Uses `uv` as the primary package manager for fast dependency resolution
- Local dependency on `wrknv` package at `../wrknv`
- Configuration files use TOML format (`supsrc.conf`)
- Environment variables can override configuration (prefix: `SUPSRC_`)
- TUI is optional and requires separate installation (`supsrc[tui]`)
- "import annotations" is okay so I can use the unquoted types.
- After writing each Python file, run the code quality tools - ruff check --fix --unsafe-fixes, ty check, mypy, ruff format, then run each of the tools again. this way CQ is performed during the dev process.