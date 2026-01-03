# 🔼⚙️ Supsrc

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-package_manager-FF6B35.svg)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/provide-io/supsrc/actions/workflows/ci.yml/badge.svg)](https://github.com/provide-io/supsrc/actions)

**Automated Git commit/push utility based on filesystem events and rules**

Never forget to commit again! supsrc watches your repositories for changes and automatically stages, commits, and pushes them according to rules you define. Perfect for frequent checkpointing, synchronizing work-in-progress, or ensuring volatile experiments are saved.

## ✨ Key Features

*   **📂 Directory Monitoring:** Watches specified repository directories recursively for file changes using `watchdog`.
*   **📜 Rule-Based Triggers:**
    *   **Inactivity:** Trigger actions after a configurable period of no file changes (e.g., `30s`, `5m`).
    *   **Save Count:** Trigger actions after a specific number of file save events.
    *   **Manual:** Disable automatic triggers (useful for testing or specific setups).
*   **⚙️ Git Engine:**
    *   Interacts with Git repositories using `pygit2`.
    *   Automatically stages modified, added, and deleted files (respecting `.gitignore`).
    *   Performs commits with customizable message templates (including timestamps, save counts, and change summaries).
    *   Optionally pushes changes to a configured remote and branch.
    *   Handles SSH Agent authentication and basic HTTPS (user/token via env vars).
*   **📝 TOML Configuration:** Easy-to-understand configuration file (`supsrc.conf`).
*   **🕶️ `.gitignore` Respect:** Automatically ignores files specified in the repository's `.gitignore`.
*   **📊 Structured Logging:** Detailed logging using `structlog` for observability (JSON or colored console output).
*   **🖥️ Optional TUI:** An interactive Terminal User Interface (built with `textual`) for monitoring repository status and logs in real-time.
*   **📟 Tail Mode:** A headless, non-interactive mode for monitoring repositories without terminal control issues (useful for scripts and automation).

## Quick Start
1. Install: `uv tool install supsrc`
2. Read the [Getting Started guide](https://github.com/provide-io/supsrc/blob/main/docs/getting-started/installation.md).
3. Try the examples in [examples/README.md](https://github.com/provide-io/supsrc/blob/main/examples/README.md).

## Documentation
- [Documentation index](https://github.com/provide-io/supsrc/blob/main/docs/index.md)
- [API docs](https://github.com/provide-io/supsrc/tree/main/docs/api)
- [Examples](https://github.com/provide-io/supsrc/blob/main/examples/README.md)

## Development

### Quick Start

```bash
# Set up environment
uv sync

# Run common tasks
we test           # Run tests
we lint           # Check code
we format         # Format code
we tasks          # See all available commands
```

See [CLAUDE.md](https://github.com/provide-io/supsrc/blob/main/CLAUDE.md) for detailed development instructions and architecture information.

## 🤝 Contributing

Contributions are welcome! Please feel free to open an issue to report bugs, suggest features, or ask questions. Pull requests are greatly appreciated.

## 📜 License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](https://github.com/provide-io/supsrc/blob/main/LICENSE) file for details. <!-- Ensure LICENSE file exists -->

## 🤔 Why `supsrc`?

*   **Automated Checkpoints:** Working on something complex or experimental? `supsrc` can automatically commit your changes after a period of inactivity or after a certain number of saves, creating a safety net without interrupting your flow.
*   **Effortless Syncing:** Keep a work-in-progress branch automatically pushed to a remote for backup or collaboration, without manual `git add/commit/push` steps.
*   **Simple Configuration:** Define your repositories and rules in a clear TOML file.
*   **Focused:** Designed specifically for the "watch and sync" workflow, aiming to be simpler than custom scripting or more complex backup solutions for this specific task.

## 🚀 Installation

### Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install supsrc
uv tool install supsrc

# Install with TUI support
uv tool install 'supsrc[tui]'

# Install with LLM support (Gemini and Ollama)
uv tool install 'supsrc[llm]'

# Install with all optional features
uv tool install 'supsrc[tui,llm]'
```

### Using pip

Ensure you have Python 3.11 or later installed:

```bash
uv tool install supsrc

# With TUI support
uv tool install 'supsrc[tui]'

# With LLM support
uv tool install 'supsrc[llm]'
```

## 💡 Usage

1.  **Create a Configuration File:** By default, `supsrc` looks for `supsrc.conf` in the current directory. See the [Configuration](#-configuration) section below for details.

2.  **Run the Watcher:**

    ```bash
    # Run with interactive dashboard (TUI mode)
    supsrc sui

    # Run in headless mode (non-interactive)
    supsrc watch

    # Specify a different config file
    supsrc sui -c /path/to/your/config.toml
    supsrc watch -c /path/to/your/config.toml

    # Increase log verbosity
    supsrc watch --log-level DEBUG
    ```

3.  **Check Configuration:** Validate and display the loaded configuration (including environment variable overrides):

    ```bash
    supsrc config show
    supsrc config show -c path/to/config.toml
    ```

4.  **Stop the Watcher:** Press `Ctrl+C` to stop the watcher gracefully.

## ⚙️ Configuration

supsrc uses a TOML configuration file (`supsrc.conf`) to define repositories, rules, and Git settings. Configuration supports:

- **Multiple repository monitoring** with individual settings
- **Rule-based triggers** (inactivity, save count, manual)
- **Git engine** with auto-push, custom commit messages, and authentication
- **Optional LLM integration** for commit message generation and code review
- **Environment variable overrides** for flexible deployment

See the [Configuration Guide](https://github.com/provide-io/supsrc/blob/main/docs/configuration.md) for complete documentation on:
- Configuration file structure and examples
- Rule types and behavior
- Git authentication (SSH Agent, HTTPS)
- LLM providers (Gemini, Ollama)
- Environment variables
- TUI setup


## 🙏 Acknowledgements

`supsrc` builds upon several fantastic open-source libraries, including:

*   [`pygit2`](https://www.pygit2.org/) for Git interactions.
*   [`watchdog`](https://github.com/gorakhargosh/watchdog) for filesystem monitoring.
*   [`structlog`](https://www.structlog.org/) for structured logging.
*   [`attrs`](https://www.attrs.org/) & [`cattrs`](https://catt.rs/) for data classes and configuration structuring.
*   [`click`](https://click.palletsprojects.com/) for the command-line interface.
*   [`textual`](https://github.com/Textualize/textual) for the optional TUI.
*   [`pathspec`](https://github.com/cpburnz/python-path-specification) for `.gitignore` handling.

Copyright (c) provide.io LLC.
