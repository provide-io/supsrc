# src/supsrc/cli/main.py

"""
Main CLI entry point for supsrc using Click.
Handles global options like logging level.
"""

from importlib.metadata import PackageNotFoundError, version

import click
import structlog

from supsrc.cli.config_cmds import config_cli
from supsrc.cli.tail_cmds import tail_cli
from supsrc.cli.watch_cmds import watch_cli
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger
# Replace custom CLI utils with Foundation's CLI framework
from provide.foundation.cli import logging_options, setup_cli_logging, error_handler

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
    log_file: str | None,
    json_logs: bool | None,
):
    """
    Supsrc: Automated Git commit/push utility.

    Monitors repositories and performs Git actions based on rules.
    Configuration precedence: CLI options > Environment Variables > Config File > Defaults.
    """
    ctx.ensure_object(dict)

    # Use Foundation's CLI logging setup
    setup_cli_logging(
        level=log_level or "WARNING",
        format="json" if json_logs else "console",
        file_path=log_file
    )
    
    # Store context for subcommands
    ctx.obj["LOG_LEVEL"] = log_level
    ctx.obj["LOG_FILE"] = log_file
    ctx.obj["JSON_LOGS"] = json_logs if json_logs is not None else False
    log.debug(
        "Main CLI group initialized",
        log_level=log_level,
        log_file=log_file,
        json_logs=json_logs,
    )


cli.add_command(config_cli)
cli.add_command(tail_cli)
cli.add_command(watch_cli)

if __name__ == "__main__":
    cli()

# 🖥️⚙️
