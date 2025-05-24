#
# supsrc/cli/main.py
#
"""
Main CLI entry point for supsrc using Click.
Handles global options like logging level.
"""

import logging
import sys
from importlib.metadata import PackageNotFoundError, version

import click
import structlog

from supsrc.cli.config_cmds import config_cli
from supsrc.cli.watch_cmds import watch_cli
from supsrc.telemetry import StructLogger
from supsrc.telemetry.logger import setup_logging

try:
    __version__ = version("supsrc")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

# Logger for this specific module
log: StructLogger = structlog.get_logger("cli.main")

# Define choices based on standard logging levels
LOG_LEVEL_CHOICES = click.Choice(
    list(logging._nameToLevel.keys()), case_sensitive=False
)

# Shared logging options that can be used across commands
def logging_options(f):
    """Decorator to add logging options to any command."""
    f = click.option(
        "-l", "--log-level",
        type=LOG_LEVEL_CHOICES,
        default=None,  # None means inherit from parent
        help="Set the logging level (overrides config file and env var).",
    )(f)
    f = click.option(
        "--log-file",
        type=click.Path(dir_okay=False, writable=True, resolve_path=True),
        default=None,
        help="Path to write logs to a file (JSON format). Suppresses console output.",
    )(f)
    f = click.option(
        "--json-logs",
        is_flag=True,
        default=None,  # None means inherit from parent
        help="Output console logs as JSON.",
    )(f)
    return f

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", package_name="supsrc")
@logging_options
@click.pass_context
def cli(ctx: click.Context, log_level: str | None, log_file: str | None, json_logs: bool | None):
    """
    Supsrc: Automated Git commit/push utility.

    Monitors repositories and performs Git actions based on rules.
    Configuration precedence: CLI options > Environment Variables > Config File > Defaults.
    """
    # Ensure context object exists
    ctx.ensure_object(dict)

    # Store options in context for subcommands to access
    # These values reflect Click's precedence (CLI > Env Var > Default)
    ctx.obj["LOG_LEVEL"] = log_level or "INFO"
    ctx.obj["LOG_FILE"] = log_file
    ctx.obj["JSON_LOGS"] = json_logs if json_logs is not None else False

def setup_logging_from_context(ctx: click.Context, local_log_level: str | None = None,
                               local_log_file: str | None = None,
                               local_json_logs: bool | None = None) -> None:
    """Setup logging using context and local overrides."""
    # Merge global and local options (local takes precedence)
    log_level = local_log_level or ctx.obj.get("LOG_LEVEL", "INFO")
    log_file = local_log_file or ctx.obj.get("LOG_FILE")
    json_logs = local_json_logs if local_json_logs is not None else ctx.obj.get("JSON_LOGS", False)

    # Get numeric level
    log_level_numeric = logging.getLevelName(log_level.upper())

    # Setup logging with file-only mode if log_file is specified
    setup_logging(
        level=log_level_numeric,
        json_logs=json_logs,
        log_file=log_file,
        file_only=log_file is not None  # New parameter
    )

    log.debug("CLI logging initialized",
              level=log_level,
              file=log_file or "console",
              json=json_logs)

# Add command groups to the main CLI group
cli.add_command(config_cli)
cli.add_command(watch_cli)

if __name__ == "__main__":
    cli()

# 🖥️⚙️
