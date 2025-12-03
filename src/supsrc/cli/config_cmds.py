#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from pathlib import Path

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import load_config
from supsrc.exceptions import ConfigurationError

try:
    from rich.pretty import pretty_repr

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

log: StructLogger = get_logger(__name__)


@click.group(name="config")
def config_cli():
    """Commands for inspecting and validating configuration."""
    pass


@config_cli.command(name="show")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def show_config(ctx: click.Context, config_path: Path, **kwargs):
    """Load, validate, and display the configuration."""
    # Foundation's CLI framework handles logging setup via decorators
    log.info("Executing 'config show' command", config_path=str(config_path))

    try:
        config = load_config(config_path)
        log.debug("Configuration loaded successfully by 'show' command.")

        if RICH_AVAILABLE:
            output_str = pretty_repr(config, expand_all=True)
            click.echo(output_str)
        else:
            import io

            with io.StringIO() as buffer:
                output_str = buffer.getvalue()
            click.echo(output_str)

        disabled_count = sum(1 for repo in config.repositories.values() if not repo._path_valid)
        if disabled_count > 0:
            log.warning(
                f"{disabled_count} repository path(s) were invalid and auto-disabled.",
                count=disabled_count,
            )
        else:
            log.info("All repository paths validated successfully.")

    except ConfigurationError as e:
        log.error("Failed to load or validate configuration", error=str(e), exc_info=True)
        click.echo(f"Error: Configuration problem in '{config_path}':\n{e}", err=True)
        ctx.exit(1)
    except Exception as e:
        log.critical(
            "An unexpected error occurred during 'config show'",
            error=str(e),
            exc_info=True,
        )
        click.echo(f"Error: An unexpected issue occurred: {e}", err=True)
        ctx.exit(2)


# 🔼⚙️🔚
