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
uv sync
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
uv run supsrc watch              # Headless mode (non-interactive)
uv run supsrc sui               # With Terminal UI (interactive dashboard)

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
   - `repository_manager.py` - Repository initialization and lifecycle management
   - `monitoring_coordinator.py` - Filesystem monitoring coordination
   - `tui_interface.py` - Optional Terminal UI integration

3. **Engine Layer** (`src/supsrc/engines/`) - Pluggable repository engines
   - Protocol-based design allowing different VCS backends
   - `git/` subdirectory contains modular Git engine implementation
   - Components: `client.py`, `operations.py`, `staging.py`, `status.py`

4. **Configuration Layer** (`src/supsrc/config/`) - Strongly-typed configuration
   - `models.py` - Attrs-based data models for configuration
   - `loader.py` - TOML configuration loading and validation with cattrs

5. **Event System Layer** (`src/supsrc/events/`) - Event processing and buffering
   - `buffer/` - Modular event buffering system with atomic operation detection
     - `core.py` - EventBuffer orchestration (off/simple/smart modes)
     - `grouping.py` - Simple file-based grouping strategy
     - `streaming.py` - Foundation OperationDetector integration
     - `converters.py` - Event type transformations
   - `collector.py` - Event collection and subscription system
   - `processor.py` - Event processing orchestrator with rule evaluation
   - `monitor.py` - File change event definitions

6. **Monitoring Layer** (`src/supsrc/monitor/`) - Filesystem event monitoring
   - `service.py` - Watchdog-based file monitoring service
   - `events.py` - Event type definitions
   - `handler.py` - Event handling and routing logic

### Key Design Patterns

- **Protocol-Based Interfaces**: Uses Python protocols for pluggable engines and rules, enabling extensibility
- **Async/Await Architecture**: Built on asyncio for concurrent file monitoring and Git operations
- **Event-Driven System**: Filesystem changes trigger rule evaluation through an event queue
- **Modular Event Buffering**: Pluggable buffering strategies (off/simple/smart) with Foundation integration
- **Streaming Operation Detection**: Real-time atomic save pattern detection via Foundation's OperationDetector
- **Structured Configuration**: TOML configs with strong typing via attrs/cattrs
- **Structured Logging**: JSON-structured logging via Foundation's logger for observability

### Core Flow
```
File Changes → Watchdog → Event Queue → Event Buffer → Event Processor
                              ↓            (optional)         ↓
                         Config Reload   Atomic Detection   Rule Engine
                                             ↓                 ↓
                                        TUI Event Feed    Git Actions
                                             ↑                 ↓
                                    State Management ← Commits/Pushes
```

**Event Flow Details:**
1. Filesystem changes detected by Watchdog
2. Events queued for processing
3. Optional buffering with atomic operation detection (smart mode)
4. Rule evaluation (inactivity/save count triggers)
5. Git operations (stage → commit → push)
6. State updates propagated to TUI

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

## Code Organization Guidelines

### When to Split Files

Split a file into modules when it contains **multiple independent concerns** that can work separately:

**Indicators for splitting:**
- File has 400+ lines with distinct, unrelated responsibilities
- Multiple concerns that don't need to coordinate with each other
- Pure functions or utilities that could be imported independently
- Different grouping strategies or algorithms that don't share state

**Example: `events/buffer_legacy.py` (546 lines) → Split into:**
- `buffer/core.py` - Main EventBuffer orchestration
- `buffer/grouping.py` - Simple file-based grouping strategy
- `buffer/streaming.py` - Foundation OperationDetector integration
- `buffer/converters.py` - Pure conversion functions
- `buffer/__init__.py` - Public API re-exports

**Benefits of this split:**
- Each module has single, focused responsibility
- Easier testing (test grouping logic independently from streaming detection)
- Clear dependency graph
- Smaller files (12-226 lines each)

### When NOT to Split Files

Keep files together when they implement the **orchestrator pattern** with interdependent concerns:

**Indicators for keeping together:**
- Single class coordinating multiple related async operations
- Methods that must work together in coordinated flow
- Shared state management across lifecycle
- Timer management, debouncing, and scheduling
- Main coordination logic for subsystem

**Examples of appropriate large files:**
- `runtime/orchestrator.py` (441 lines) - Main watch coordinator
- `events/processor.py` (443 lines) - Event processing orchestrator
- `engines/git/base.py` (482 lines) - Git engine coordinator
- `runtime/repository_manager.py` (432 lines) - Repository lifecycle manager

**Why these stay together:**
- All methods coordinate through shared async state
- Lifecycle management requires centralized control
- Breaking apart would create circular dependencies
- Size is appropriate for orchestrator complexity

### Module Organization Best Practices

When refactoring, follow these patterns:

1. **Create package directories** for related modules:
   ```
   events/buffer/
   ├── __init__.py      # Public API re-exports only
   ├── core.py          # Main orchestration class
   ├── grouping.py      # Independent algorithms
   ├── streaming.py     # Foundation integration
   └── converters.py    # Pure conversion functions
   ```

2. **Public API in `__init__.py`**:
   ```python
   from module.core import MainClass
   from module.events import EventType
   __all__ = ["MainClass", "EventType"]
   ```

3. **Update all imports** after refactoring:
   - Search for old imports: `from old_module import X`
   - Update to new location: `from new_package import X`
   - Use absolute imports always, never relative

4. **Test requirements**:
   - All existing tests must pass without modification to test logic
   - May need to update import statements in tests
   - Add tests for new modules if exposing new APIs
   - Verify integration tests still work end-to-end

5. **Async patterns** when splitting:
   - Keep async coordination in orchestrator classes
   - Extract pure, synchronous logic to separate modules
   - Use callbacks for streaming detection (Foundation pattern)
   - Post-operation delays for debouncing (20ms typical)

### Event Buffering Architecture

The event buffering system demonstrates modular organization:

**Components:**
- `EventBuffer` (core.py) - Routes events to appropriate handlers based on mode
- `group_events_simple()` (grouping.py) - Groups events by file path
- `StreamingOperationHandler` (streaming.py) - Integrates Foundation's OperationDetector
- Converter functions (converters.py) - Transform between event types

**Modes:**
- `off` - Pass-through, no buffering
- `simple` - Basic file-path grouping
- `smart` - Streaming atomic operation detection via Foundation

**Atomic Save Detection:**
- Uses `provide.foundation.file.operations.OperationDetector`
- Detects patterns: create temp → write → move (atomic rewrite)
- Configurable temp file patterns (`.tmp`, `~`, `.swp`, hidden files)
- Streaming detection with 20ms post-operation delay for FS settling
- Time-window based detection (default: 100ms)

**Testing Patterns:**
- Complete event sequences required (create → modify → move)
- Wait times must account for: window + post-delay + margin
- Always call `flush_all()` before assertions in tests
- Verify both individual events and grouped operations

## Important Notes

- Requires Python 3.11+ for modern Python features
- Uses `uv` as the primary package manager for fast dependency resolution
- Local dependency on `wrknv` package at `../wrknv`
- Configuration files use TOML format (`supsrc.conf`)
- Environment variables can override configuration (prefix: `SUPSRC_`)
- TUI is optional and requires separate installation (`supsrc[tui]`)
- "import annotations" is okay so I can use the unquoted types.
- After writing each Python file, run the code quality tools:
  - If `we` commands available: `we format`, `we lint`, `we typecheck`
  - Otherwise: `ruff format`, `ruff check --fix`, `mypy`
- never use structlog/logging directly unless I approve it. always use provide-foundation logger using the public API.
- never use relative imports. only absolute imports always.
