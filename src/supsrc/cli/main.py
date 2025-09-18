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

    # Use supsrc's own logging setup which properly handles Foundation
    from supsrc.telemetry.logger.base import setup_logging
    import logging

    try:
        # Convert log level string to integer
        level = getattr(logging, (log_level or "WARNING").upper(), logging.WARNING)

        # Determine if JSON logs should be used
        json_logs = log_format == "json"

        # Setup logging using supsrc's Foundation integration
        setup_logging(
            level=level,
            json_logs=json_logs,
            log_file=str(log_file) if log_file else None,
            headless_mode=True,
        )
    except Exception:
        # Fallback to basic logging setup if supsrc logging fails
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
