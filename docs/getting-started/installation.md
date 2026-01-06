# Installation

Get started with SupSrc, an automated Git workflow and commit management tool that monitors filesystem events and performs Git operations based on configurable rules.

## Prerequisites

--8<-- ".provide/foundry/docs/_partials/python-requirements.md"

--8<-- ".provide/foundry/docs/_partials/uv-installation.md"

--8<-- ".provide/foundry/docs/_partials/python-version-setup.md"

## Installation Methods

### As a Command-Line Tool

If you want to use supsrc to monitor and automate your Git workflows:

**Using uv (Recommended):**
```bash
# Install supsrc globally with uv
uvx supsrc --help

# Or install in a dedicated virtual environment
uv tool install supsrc

# With Terminal UI support
uv tool install "supsrc[tui]"
```

### As a Library Dependency

If you're integrating supsrc's functionality into your project:

**Using uv:**
```bash
uv add supsrc
```

**In your `pyproject.toml`:**
```toml
[project]
dependencies = [
    "supsrc>=0.1.0",
]
```

### For Development

Clone the repository and set up the development environment:

```bash
# Clone the repository
git clone https://github.com/provide-io/supsrc.git
cd supsrc

# Set up development environment
uv sync

# Or install with all development dependencies
uv sync --all-groups

# Verify installation
uv run supsrc --version
```

This creates a `.venv/` virtual environment with all dependencies installed.

--8<-- ".provide/foundry/docs/_partials/virtual-env-setup.md"

--8<-- ".provide/foundry/docs/_partials/platform-specific-macos.md"

## Optional Features

### Terminal UI (Recommended)

SupSrc includes an optional interactive Terminal UI (TUI) for real-time monitoring and control:

```bash
# Install with TUI support
uv tool install supsrc[tui]

# Run with TUI
supsrc sui
```

**TUI Features:**
- Real-time event monitoring dashboard
- Repository status display
- Interactive controls for pause/resume
- Event feed and activity logs
- Configuration display

**Without TUI:**
```bash
# Headless monitoring mode (no TUI dependencies)
uv tool install supsrc
supsrc watch
```

### Foundation Integration

SupSrc is built on Foundation infrastructure for structured logging and operation detection:

```python
from provide.foundation import logger
from provide.foundation.file.operations import OperationDetector
from supsrc.config import models
from supsrc.runtime import orchestrator
```

**Operation Detection:**
- Atomic save pattern detection (temp file → move)
- Streaming event processing
- Debouncing and buffering

## Verifying Installation

### Basic Verification

--8<-- ".provide/foundry/docs/_partials/verification-commands.md"

!!! note "Package and Command Names"
    Replace `{{PACKAGE_NAME}}` with `supsrc` and `{{COMMAND_NAME}}` with `supsrc` in the verification commands above.

### SupSrc-Specific Verification

**1. Test Core Imports:**
```python
import supsrc
from supsrc.cli import main
from supsrc.config.models import SupSrcConfig
from supsrc.runtime.orchestrator import Orchestrator

print(f"SupSrc version: {supsrc.__version__}")
print("Installation successful!")
```

**2. Test Configuration Loading:**
```python
from supsrc.config.loader import load_config
from pathlib import Path

# Create minimal test config
config_content = """
[general]
log_level = "INFO"

[[repositories]]
path = "/path/to/repo"
rule_type = "inactivity"
trigger_seconds = 300
"""

config_path = Path("test_config.toml")
config_path.write_text(config_content)

config = load_config(config_path)
print(f"Loaded {len(config.repositories)} repository configuration(s)")
config_path.unlink()  # Clean up
```

**3. Test CLI Commands:**
```bash
# Display help
supsrc --help

# Show config command
supsrc config show

# Test watch command (with non-existent config to verify parsing)
supsrc watch --help
```

**4. Run Tests:**
```bash
# Run all tests (152 test cases)
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Run specific test categories
uv run pytest -m "not slow"
uv run pytest tests/unit/
```

## Configuration Setup

### Creating a Configuration File

SupSrc uses TOML configuration files (`supsrc.conf` by default):

```bash
# Create example configuration
cat > supsrc.conf << 'EOF'
[general]
log_level = "INFO"
buffer_mode = "smart"  # off, simple, or smart

[[repositories]]
path = "/path/to/your/repo"
rule_type = "inactivity"
trigger_seconds = 300
commit_message_template = "Auto-commit: {timestamp}"
auto_push = false

[[repositories]]
path = "/path/to/another/repo"
rule_type = "save_count"
trigger_count = 10
commit_message_template = "Checkpoint: {file_count} files"
auto_push = true
push_remote = "origin"
push_branch = "main"
EOF
```

**Configuration Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `log_level` | Logging verbosity (DEBUG, INFO, WARNING) | INFO |
| `buffer_mode` | Event buffering (off, simple, smart) | smart |
| `rule_type` | Trigger type (inactivity, save_count, manual) | inactivity |
| `trigger_seconds` | Inactivity timeout (seconds) | 300 |
| `trigger_count` | Save count threshold | 10 |
| `auto_push` | Automatically push commits | false |

### Environment Variables

Override configuration via environment variables with `SUPSRC_` prefix:

```bash
# Set log level
export SUPSRC_LOG_LEVEL=DEBUG

# Override buffer mode
export SUPSRC_BUFFER_MODE=simple

# Run with environment overrides
supsrc watch
```

## Development Workflow

--8<-- ".provide/foundry/docs/_partials/testing-setup.md"

**Additional Testing Options:**
```bash
# Skip slow tests
uv run pytest -m "not slow"

# Run integration tests only
uv run pytest -m integration

# Run specific test file
uv run pytest tests/unit/test_orchestrator.py -v
```

**Important Testing Note:**

SupSrc uses Foundation's OperationDetector for atomic save detection. Tests require:
- Complete event sequences (create → modify → move)
- Proper wait times for detection windows
- Always call `flush_all()` before assertions

```python
# Example test pattern
async def test_atomic_detection():
    # Setup event buffer
    buffer = EventBuffer(mode="smart")

    # Send complete sequence
    buffer.add_event(create_event)
    buffer.add_event(modify_event)
    buffer.add_event(move_event)

    # Wait for detection (window + post-delay + margin)
    await asyncio.sleep(0.15)

    # Flush and verify
    groups = buffer.flush_all()
    assert len(groups) == 1
```

--8<-- ".provide/foundry/docs/_partials/code-quality-setup.md"

**Additional Type Checking:**
```bash
# Run Pyre (primary type checker for this project)
pyre check
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

## Running SupSrc

### Basic Usage

```bash
# Start monitoring with TUI
supsrc sui

# Headless monitoring
supsrc watch

# Use specific config file
supsrc watch -c /path/to/config.toml

# Show current configuration
supsrc config show
```

### Monitoring Multiple Repositories

```bash
# Configure multiple repos in supsrc.conf
[[repositories]]
path = "~/projects/repo1"
rule_type = "inactivity"
trigger_seconds = 300

[[repositories]]
path = "~/projects/repo2"
rule_type = "save_count"
trigger_count = 5
auto_push = true

# Start monitoring all configured repos
supsrc watch
```

## Troubleshooting

--8<-- ".provide/foundry/docs/_partials/troubleshooting-common.md"

### SupSrc-Specific Issues

#### TUI Not Available

If you installed without TUI support:

```bash
# Install TUI dependencies
uv tool install supsrc[tui]

# Or use headless mode
supsrc watch  # Instead of 'supsrc sui'
```

#### Git Operations Failing

Check Git configuration and permissions:

```bash
# Verify Git is accessible
git --version

# Check repository status
cd /path/to/repo
git status

# Verify authentication for push
git remote -v
ssh -T git@github.com  # For SSH
```

#### Event Detection Not Working

Verify filesystem monitoring:

```bash
# Check file changes are being detected
export SUPSRC_LOG_LEVEL=DEBUG
supsrc watch

# Make some file changes and watch logs
# Should see event detection messages
```

#### Configuration Errors

Validate configuration file:

```bash
# Check config syntax
supsrc config show

# Use explicit config path
supsrc watch --config /full/path/to/supsrc.conf
```

#### High CPU Usage

Adjust buffer mode or event processing:

```toml
[general]
buffer_mode = "simple"  # Less CPU than "smart"

[[repositories]]
# Increase trigger time to reduce frequency
trigger_seconds = 600  # 10 minutes instead of 5
```

### Getting Help

If you encounter issues:

1. **Check logs** - Run with `SUPSRC_LOG_LEVEL=DEBUG`
2. **Verify Python version** - Ensure you're using Python 3.11+
3. **Check configuration** - Validate TOML syntax with `supsrc config show`
4. **Report issues** - [GitHub Issues](https://github.com/provide-io/supsrc/issues)

## Next Steps

### Quick Start

1. **[Installation Guide](installation.md)** - Set up your first monitored repository
2. **[Configuration Guide](../configuration.md)** - Learn about all configuration options
3. **[Rule Types](../configuration.md#rules-explained)** - Understand inactivity, save count, and manual rules

### Advanced Topics

- **[API Reference](../api/index.md)** - CLI and configuration reference
- **[Development Guide](../../CONTRIBUTING.md)** - Contributing to SupSrc

Ready to automate your Git workflow? Start with the [installation guide](installation.md)!
