# src/supsrc/cli/utils.py

import logging

import click
import structlog

# No need for custom setup - Foundation handles everything via Hub

log = structlog.get_logger("cli.utils")

LOG_LEVEL_CHOICES = click.Choice(list(logging._nameToLevel.keys()), case_sensitive=False)


def logging_options(f):
    """Decorator to add logging options to any command."""
    f = click.option(
        "-l",
        "--log-level",
        type=LOG_LEVEL_CHOICES,
        default=None,
        envvar="SUPSRC_LOG_LEVEL",
        help="Set the logging level (overrides config file).",
    )(f)
    f = click.option(
        "--log-file",
        type=click.Path(dir_okay=False, writable=True, resolve_path=True),
        default=None,
        envvar="SUPSRC_LOG_FILE",
        help="Path to write logs to a file (JSON format).",
    )(f)
    f = click.option(
        "--json-logs",
        is_flag=True,
        default=None,
        envvar="SUPSRC_JSON_LOGS",
        help="Output console logs as JSON.",
    )(f)
    return f


# Removed unused setup_logging_from_context function - Foundation handles logging setup


# ⚙️🛠️
