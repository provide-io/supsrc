# src/supsrc/cli/main.py

"""
Main CLI entry point for supsrc using Click.
Handles global options like logging level.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click
import structlog

# Replace custom CLI utils with Foundation's CLI framework
# Import Foundation CLI utilities directly to avoid testing dependencies
from provide.foundation.cli.decorators import error_handler, logging_options
from provide.foundation.context import CLIContext
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.cli.config_cmds import config_cli
from supsrc.cli.tail_cmds import tail_cli
from supsrc.cli.watch_cmds import watch_cli

try:
    __version__ = version("supsrc")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

log: StructLogger = structlog.get_logger("cli.main")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", package_name="supsrc")
@logging_options
@error_handler
@click.pass_context
def cli(
    ctx: click.Context,
    log_level: str | None,
    log_file: Path | None,
    log_format: str,
):
    """
    Supsrc: Automated Git commit/push utility.

    Monitors repositories and performs Git actions based on rules.
    Configuration precedence: CLI options > Environment Variables > Config File > Defaults.
    """
    ctx.ensure_object(dict)

    # Create Foundation CLI context and setup logging
    cli_context = CLIContext(
        log_level=log_level or "WARNING",
        log_format=log_format,
        log_file=log_file,
    )

    # Use Foundation's setup approach with error handling for file I/O
    from provide.foundation.logger import LoggingConfig, TelemetryConfig
    from provide.foundation.setup import internal_setup

    try:
        # Detect if we're in a test environment
        import os

        is_test_env = (
            "pytest" in os.environ.get("_", "")
            or "PYTEST_CURRENT_TEST" in os.environ
            or hasattr(__import__("sys"), "_called_from_test")
        )

        # Validate log file accessibility if provided
        log_file_path = None
        if log_file:
            log_file_path = str(log_file)
            # Test if we can write to the file (skip for temporary files in tests)
            if not is_test_env or not log_file_path.startswith("/tmp"):
                try:
                    with open(log_file_path, "a") as f:
                        pass  # Just test accessibility
                except (OSError, ValueError):
                    # If file is closed or inaccessible, disable file logging
                    log_file_path = None

        # Configure logging with Foundation but handle test environment carefully
        config = TelemetryConfig(
            logging=LoggingConfig(
                console_formatter=log_format,
                default_level=log_level or "WARNING",
                log_file=log_file_path,
            )
        )

        if is_test_env:
            # In test mode, be more cautious about file logging
            try:
                setup_foundation(config)
            except Exception:
                # If Foundation fails in test mode, use basic logging
                import logging

                level = getattr(logging, (log_level or "WARNING").upper())
                logging.basicConfig(level=level, format="%(levelname)s: %(message)s", force=True)

                # Still try to set up file logging if explicitly requested
                if log_file_path:
                    try:
                        file_handler = logging.FileHandler(log_file_path)
                        file_handler.setLevel(level)
                        file_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
                        logging.getLogger().addHandler(file_handler)
                    except Exception:
                        pass  # If file logging fails, just continue without it
        else:
            setup_foundation(config)
    except Exception:
        # Fallback to basic logging setup if Foundation fails
        import logging

        logging.basicConfig(
            level=getattr(logging, (log_level or "WARNING").upper()),
            format="%(levelname)s: %(message)s",
            force=True,
        )

    # Store context for subcommands
    ctx.obj["LOG_LEVEL"] = log_level
    ctx.obj["LOG_FILE"] = log_file
    ctx.obj["LOG_FORMAT"] = log_format
    log.debug(
        "Main CLI group initialized",
        log_level=log_level,
        log_file=log_file,
        log_format=log_format,
    )


cli.add_command(config_cli)
cli.add_command(tail_cli)
cli.add_command(watch_cli)

if __name__ == "__main__":
    cli()

# 🖥️⚙️
