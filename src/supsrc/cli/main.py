# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Main CLI entry point for supsrc using Click.
Properly dogfoods provide-foundation's CLI framework."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import logging
from pathlib import Path

import click
from provide.foundation import LoggingConfig, TelemetryConfig, get_hub
from provide.foundation.cli.decorators import error_handler, logging_options
from provide.foundation.context import CLIContext
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.cli.circuit_breaker_cmds import circuit_breaker_cli
from supsrc.cli.config_cmds import config_cli
from supsrc.cli.sui_cmds import sui_cli
from supsrc.cli.watch_cmds import watch_cli

try:
    __version__ = version("supsrc")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

log: StructLogger = get_logger(__name__)


def _initialize_logging(cli_context: CLIContext) -> None:
    """Initialize Foundation logging from CLIContext.

    This function properly sets up provide-foundation's logging system
    based on the CLI context configuration.

    Args:
        cli_context: CLIContext with log_level, log_format, and log_file settings
    """
    try:
        # Map log level string to logging constant
        # Handle TRACE specially since it's a Foundation custom level
        if cli_context.log_level == "TRACE":
            from provide.foundation.logger.trace import TRACE_LEVEL_NUM

            level = TRACE_LEVEL_NUM
            level_name = "TRACE"
        else:
            level = getattr(logging, cli_context.log_level, logging.WARNING)
            level_name = logging.getLevelName(level)

        # Setup Foundation using public API
        # Start with from_env() to preserve OpenObserve/OTLP auto-configuration,
        # then override service_name and logging settings
        from attrs import evolve

        base_config = TelemetryConfig.from_env()
        config = evolve(
            base_config,
            service_name="supsrc",  # Override service name for OTLP/telemetry
            logging=LoggingConfig(
                console_formatter=cli_context.log_format,
                default_level=level_name,
                das_emoji_prefix_enabled=True,
                logger_name_emoji_prefix_enabled=True,
            ),
        )

        # Initialize Foundation
        # Note: Foundation automatically detects explicit config and overrides auto-init
        hub = get_hub()
        hub.initialize_foundation(config)

        # Register custom supsrc eventset for log enrichment
        try:
            from provide.foundation.eventsets.registry import register_event_set

            from supsrc.telemetry import SUPSRC_EVENT_SET

            register_event_set(SUPSRC_EVENT_SET)
            log.debug("Registered supsrc eventset for observability enrichment")
        except Exception as e:
            log.warning("Failed to register supsrc eventset", error=str(e))

        # Add file handler if needed
        if cli_context.log_file:
            file_handler = logging.FileHandler(str(cli_context.log_file), encoding="utf-8")
            file_handler.setLevel(level)

            # Use JSON formatter for file logs
            if cli_context.log_format == "json":
                import json

                class JSONFileFormatter(logging.Formatter):
                    def format(self, record):
                        log_data = {
                            "timestamp": self.formatTime(record),
                            "level": record.levelname,
                            "logger": record.name,
                            "message": record.getMessage(),
                        }
                        if record.exc_info:
                            log_data["exception"] = self.formatException(record.exc_info)
                        return json.dumps(log_data)

                file_handler.setFormatter(JSONFileFormatter())

            logging.getLogger().addHandler(file_handler)

    except Exception as e:
        # Fallback to basic logging if Foundation setup fails
        logging.basicConfig(
            level=logging.WARNING,
            format="%(levelname)s: %(message)s",
            force=True,
        )
        log.warning("Failed to initialize Foundation logging, using fallback", error=str(e))


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
    # Create or get CLIContext
    if ctx.obj is None:
        ctx.obj = {}

    # Create Foundation CLI context with provided options
    cli_context = CLIContext(
        log_level=log_level or "WARNING",
        log_format=log_format,
        log_file=log_file,
    )

    # Initialize logging using the context
    _initialize_logging(cli_context)

    # Store context for subcommands
    ctx.obj["CLI_CONTEXT"] = cli_context
    ctx.obj["LOG_LEVEL"] = log_level
    ctx.obj["LOG_FILE"] = log_file
    ctx.obj["LOG_FORMAT"] = log_format

    log.debug(
        "Main CLI group initialized",
        log_level=cli_context.log_level,
        log_file=str(log_file) if log_file else None,
        log_format=log_format,
    )


cli.add_command(circuit_breaker_cli)
cli.add_command(config_cli)
cli.add_command(sui_cli)
cli.add_command(watch_cli)

if __name__ == "__main__":
    cli()

# 🔼⚙️🔚
