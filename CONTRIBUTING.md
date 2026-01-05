# Contributing to supsrc

Thank you for your interest in contributing to supsrc! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- `uv` package manager
- Git 2.0+
- SSH agent or Git credentials (for testing Git operations)

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/provide-io/supsrc.git
   cd supsrc
   ```

2. Set up the development environment:
   ```bash
   uv sync
   ```

This will create a virtual environment and install all development dependencies.

## Development Workflow

### Running Tests

```bash
# Run all tests (152 test cases)
uv run pytest

# Run tests with coverage (target: 85% minimum)
uv run pytest --cov

# Run specific test categories
uv run pytest -m "not slow"        # Skip slow tests
uv run pytest -m integration       # Only integration tests
uv run pytest tests/unit/          # Only unit tests

# Run a single test file
uv run pytest tests/unit/test_orchestrator.py

# Run a specific test
uv run pytest tests/unit/test_orchestrator.py::test_specific_function

# Or using wrknv
we run test
```

### Running the Application

```bash
# Start monitoring repositories (headless mode)
uv run supsrc watch

# Start with Terminal UI (interactive dashboard)
uv run supsrc sui

# Configuration commands
uv run supsrc config show                    # Display current configuration
uv run supsrc watch -c path/to/config.toml  # Use specific config file

# Or using wrknv
we run watch
we run sui
```

### Code Quality

Before submitting a pull request, ensure your code passes all quality checks:

```bash
# Linting and formatting
uv run ruff check .      # Check for linting issues
uv run ruff format .     # Auto-format code

# Type checking
uv run pyre check        # Run Pyre type checker

# Or using wrknv
we run format
we run lint
we run typecheck
```

### Code Style

- Follow PEP 8 guidelines (enforced by `ruff`)
- Use modern Python 3.11+ type hints (e.g., `list[str]` not `List[str]`)
- Use absolute imports, never relative imports
- Add comprehensive type hints to all functions and methods
- Write docstrings for public APIs
- Use `from __future__ import annotations` for unquoted types

### Logging

**CRITICAL**: Always use `provide.foundation.logger` for logging:

```python
from provide.foundation import logger

logger.debug("File change detected", path=file_path, event=event_type)
logger.info("Commit created", repo=repo_name, commit_hash=commit_id)
logger.error("Push failed", repo=repo_name, error=str(e))
```

**Never use**: `print()` statements or raw `structlog`/`logging` directly

## Architecture Overview

### Layered Architecture

The codebase follows a clean layered architecture:

1. **CLI Layer** (`src/supsrc/cli/`)
   - Command-line interface and entry points
   - Commands: `watch`, `sui` (TUI), `config`

2. **Runtime Layer** (`src/supsrc/runtime/`)
   - `orchestrator.py` - Main coordination logic
   - `action_handler.py` - Executes Git actions
   - `event_processor.py` - Processes filesystem events
   - `repository_manager.py` - Repository lifecycle management
   - `monitoring_coordinator.py` - Filesystem monitoring coordination

3. **Engine Layer** (`src/supsrc/engines/`)
   - Protocol-based design for pluggable VCS backends
   - `git/` - Modular Git engine implementation

4. **Configuration Layer** (`src/supsrc/config/`)
   - `models.py` - Attrs-based configuration data models
   - `loader.py` - TOML configuration loading and validation

5. **Event System Layer** (`src/supsrc/events/`)
   - `buffer/` - Modular event buffering system
   - `collector.py` - Event collection and subscription
   - `processor.py` - Event processing orchestrator

6. **Monitoring Layer** (`src/supsrc/monitor/`)
   - `service.py` - Watchdog-based file monitoring
   - `events.py` - Event type definitions
   - `handler.py` - Event handling and routing

### Key Design Patterns

- **Protocol-Based Interfaces**: Pluggable engines and rules
- **Async/Await Architecture**: Built on asyncio
- **Event-Driven System**: Filesystem changes trigger rule evaluation
- **Modular Event Buffering**: Pluggable strategies (off/simple/smart)
- **Structured Configuration**: TOML configs with attrs/cattrs
- **Structured Logging**: JSON-structured logging via Foundation

## Project Structure

```
supsrc/
├── src/supsrc/
│   ├── cli/                    # Command-line interface
│   │   ├── main.py            # Entry point
│   │   ├── watch_cmds.py      # Watch and sui commands
│   │   ├── config_cmds.py     # Config commands
│   │   └── tail_cmds.py       # Tail mode commands
│   ├── runtime/                # Core application orchestration
│   │   ├── orchestrator.py    # Main coordination logic
│   │   ├── action_handler.py  # Git action execution
│   │   ├── event_processor.py # Event processing
│   │   └── ...
│   ├── engines/                # Pluggable VCS engines
│   │   └── git/               # Git engine implementation
│   ├── config/                 # Configuration system
│   │   ├── models.py          # Data models
│   │   └── loader.py          # TOML loading
│   ├── events/                 # Event processing
│   │   ├── buffer/            # Event buffering
│   │   ├── collector.py       # Event collection
│   │   └── processor.py       # Event processing
│   └── monitor/                # Filesystem monitoring
│       ├── service.py         # Monitoring service
│       ├── events.py          # Event definitions
│       └── handler.py         # Event handling
├── tests/                      # Test suite
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── conftest.py            # Pytest fixtures
├── docs/                       # Documentation
│   ├── index.md               # Documentation index
│   ├── configuration.md       # Configuration guide
│   ├── getting-started/       # Installation guides
│   └── api/                   # API documentation
└── examples/                   # Example configurations
```

## Adding New Features

### Adding a New Rule Type

1. Define the rule protocol in `src/supsrc/engines/protocol.py`
2. Implement the rule class in `src/supsrc/engines/git/rules.py`
3. Add configuration support in `src/supsrc/config/models.py`
4. Update the rule factory in `src/supsrc/runtime/orchestrator.py`
5. Add tests in `tests/unit/test_rules.py`
6. Update configuration documentation

### Adding a New Git Operation

1. Implement the operation in `src/supsrc/engines/git/operations.py`
2. Update the Git engine protocol if needed
3. Add tests in `tests/integration/test_git_operations.py`
4. Update the action handler if needed
5. Document the operation

### Modifying the Event System

1. Update event types in `src/supsrc/monitor/events.py`
2. Modify event processing in `src/supsrc/events/processor.py`
3. Update event buffering if needed in `src/supsrc/events/buffer/`
4. Add comprehensive tests for event flow
5. Update documentation

## Testing Guidelines

### Writing Tests

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions and Git operations
- **Async Testing**: Use pytest-asyncio for testing async code
- **Mocking**: Use pytest-mock for isolating components
- **Time-Based Testing**: Use freezegun for testing time-based rules

### Test Structure

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_feature_name():
    """Test description explaining what this test validates."""
    # Arrange
    config = create_test_config()
    orchestrator = Orchestrator(config)

    # Act
    result = await orchestrator.process_event(event)

    # Assert
    assert result.success
```

### Test Fixtures

Use the shared fixtures in `tests/conftest.py`:

```python
def test_with_fixture(tmp_repo, sample_config):
    """Use pytest fixtures for common test setup."""
    # tmp_repo provides a temporary Git repository
    # sample_config provides a test configuration
    pass
```

## Documentation

### Docstring Format

Use Google-style docstrings:

```python
async def process_event(self, event: FileEvent) -> ProcessResult:
    """Process a filesystem event through the rule engine.

    Args:
        event: The filesystem event to process

    Returns:
        ProcessResult containing success status and actions taken

    Raises:
        ProcessingError: If event processing fails

    Example:
        >>> event = FileModifiedEvent(path="/repo/file.py")
        >>> result = await processor.process_event(event)
        >>> print(f"Processed: {result.success}")
    """
```

### Updating Documentation

When adding new features or changing APIs:

1. Update relevant docstrings in the code
2. Update `README.md` for user-facing changes
3. Update `docs/configuration.md` for configuration changes
4. Update `docs/index.md` for major features
5. Add examples in `examples/` directory

## Configuration

### Configuration File Format

supsrc uses TOML configuration files. Example structure:

```toml
# Global settings
log_level = "INFO"

# Repository definitions
[[repositories]]
name = "my-project"
path = "/path/to/repo"

[repositories.trigger]
type = "inactivity"
delay = "30s"

[repositories.git]
auto_push = true
remote = "origin"
branch = "auto-commits"
```

See `docs/configuration.md` for complete documentation.

## Submitting Changes

### Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name main
   ```

2. Make your changes following the guidelines

3. Ensure all tests pass and code quality checks pass:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format .
   uv run pyre check
   ```

4. Commit your changes:
   ```bash
   git commit -m "Add feature: description of what was added"
   ```

5. Push to the branch:
   ```bash
   git push origin feature/your-feature-name
   ```

6. Open a Pull Request

7. Ensure your PR:
   - Has a clear title and description
   - References any related issues
   - Includes tests for new functionality
   - Maintains or improves code coverage (85% target)
   - Updates documentation as needed
   - Passes all CI checks

### Commit Message Guidelines

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and pull requests when relevant

Examples:
- `Add support for LLM-generated commit messages`
- `Fix event buffering for atomic file operations`
- `Update configuration documentation with new rule types`

## Code Review Process

All submissions require review. The maintainers will:

- Review code for quality, style, and correctness
- Ensure tests are comprehensive and passing
- Verify documentation is updated and accurate
- Check for breaking changes
- Verify async patterns are correct
- Ensure code coverage meets target (85%)

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues and documentation first
- Refer to the documentation in the `docs/` directory

## Dependencies

The project depends on several key libraries:

- `pygit2` - Git interactions
- `watchdog` - Filesystem monitoring
- `attrs` & `cattrs` - Configuration structuring
- `click` - Command-line interface
- `textual` - Optional TUI
- `pathspec` - .gitignore handling
- `provide-foundation` - Logging and utilities

## License

By contributing to supsrc, you agree that your contributions will be licensed under the Apache-2.0 License.
