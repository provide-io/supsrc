#
# supsrc/cli/main.py
# -*- coding: utf-8 -*-
"""
Main CLI entry point for supsrc using Click.
Handles global options like logging level.
"""

import logging
import sys

import click
import structlog

# Import setup_logging from its location
# Use relative imports assuming standard package structure
try:
    from ..telemetry.logger import setup_logging
    from .. import __version__
except ImportError:
    # Allow running directly for development? Less ideal.
    print("ERROR: Cannot perform relative imports. Ensure supsrc is installed correctly.", file=sys.stderr)
    # Attempt absolute import as fallback (might work if PYTHONPATH is set)
    try:
        from supsrc.telemetry.logger import setup_logging
        from supsrc import __version__
    except ImportError:
        __version__ = "unknown"
        def setup_logging(*args, **kwargs):
            print("ERROR: Logging setup failed.", file=sys.stderr)

# Import command groups
from .config_cmds import config_cli

log = structlog.get_logger("cli.main")

# Define choices based on standard logging levels
LOG_LEVEL_CHOICES = click.Choice(
    list(logging._nameToLevel.keys()), case_sensitive=False
)

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(__version__, '-V', '--version', package_name='supsrc')
@click.option(
    '-l', '--log-level',
    type=LOG_LEVEL_CHOICES,
    default='INFO',
    show_default=True,
    envvar='SUPSRC_LOG_LEVEL', # Allow setting via env var
    help='Set the logging level.',
)
@click.option(
    '--log-file',
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default=None,
    envvar='SUPSRC_LOG_FILE',
    help='Path to write logs to a file (JSON format).',
)
@click.option(
    '--json-logs',
    is_flag=True,
    default=False,
    envvar='SUPSRC_JSON_LOGS',
    help='Output console logs as JSON.',
)
@click.pass_context # Pass context to store/retrieve shared options
def cli(ctx: click.Context, log_level: str, log_file: str | None, json_logs: bool):
    """
    Supsrc: Automated Git commit/push utility.

    Monitors repositories and performs Git actions based on rules.
    """
    # Ensure context object exists
    ctx.ensure_object(dict)
    # Store options in context for subcommands to access
    ctx.obj['LOG_LEVEL'] = log_level
    ctx.obj['LOG_FILE'] = log_file
    ctx.obj['JSON_LOGS'] = json_logs

    # --- Setup Logging EARLY ---
    # Get numeric level AFTER validation by Click
    log_level_numeric = logging.getLevelName(log_level.upper())
    setup_logging(
        level=log_level_numeric,
        json_logs=json_logs,
        log_file=log_file
    )
    log.debug("CLI context initialized", args=sys.argv, options=ctx.obj)


# Add command groups to the main CLI group
cli.add_command(config_cli)
# Add other command groups here later (e.g., watch_cli)


if __name__ == '__main__':
    # This allows running the CLI via 'python -m supsrc.cli.main'
    # or directly if needed, but entry point script is preferred.
    cli()

# 🔼⚙️
