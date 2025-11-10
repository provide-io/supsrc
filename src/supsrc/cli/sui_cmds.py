#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

import asyncio
import importlib
import logging
import signal
import sys
from pathlib import Path
from typing import Protocol, cast

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import load_config
from supsrc.utils.directories import SupsrcDirectories


class SupsrcTuiAppProtocol(Protocol):
    def __init__(self, *, config_path: Path, cli_shutdown_event: asyncio.Event) -> None: ...

    def run(self) -> None: ...


try:
    _tui_module = importlib.import_module("supsrc.tui.app")
except ImportError:
    SupsrcTuiApp: type[SupsrcTuiAppProtocol] | None = None
    TEXTUAL_AVAILABLE = False
else:
    SupsrcTuiApp = cast(type[SupsrcTuiAppProtocol], _tui_module.SupsrcTuiApp)
    TEXTUAL_AVAILABLE = True

log: StructLogger = get_logger(__name__)

_shutdown_requested = asyncio.Event()


async def _handle_signal_async(sig: int):
    signame = signal.Signals(sig).name
    base_log = get_logger(__name__)
    base_log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if not _shutdown_requested.is_set():
        base_log.info("Setting shutdown requested event.")
        _shutdown_requested.set()
    else:
        base_log.warning("Shutdown already requested, signal ignored.")


@click.command(name="sui")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=str),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def sui_cli(ctx: click.Context, config_path: Path | str, **kwargs):
    """Supsrc User Interface - Interactive dashboard for monitoring repositories."""
    import os

    # CRITICAL: Suppress stderr immediately to prevent any initialization logs
    _original_stderr = sys.stderr
    with open(os.devnull, "w") as dev_null:
        sys.stderr = dev_null

        try:
            config_path = Path(config_path)
            # Determine log file path
            log_file_path = Path("/tmp/supsrc_tui_debug.log")
            try:
                supsrc_config = load_config(config_path)
                for _repo_id, repo_config in supsrc_config.repositories.items():
                    if repo_config.enabled and repo_config._path_valid:
                        log_file_path = (
                            SupsrcDirectories.get_log_dir(repo_config.path) / "supsrc_tui_debug.log"
                        )
                        break
            except Exception:
                pass

            # Check for TUI dependencies
            if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None:
                sys.stderr = _original_stderr
                log.error("TUI dependencies not installed for 'sui' command.")
                click.echo(
                    "Error: The 'sui' command requires the 'textual' library, provided by the 'tui' extra.",
                    err=True,
                )
                click.echo(
                    "Hint: pip install 'supsrc[tui]' or uv pip install 'supsrc[tui]'", err=True
                )
                ctx.exit(1)
                return

            # Set up file logging (logs still suppressed from stderr)
            from attrs import evolve
            from provide.foundation import LoggingConfig, TelemetryConfig, get_hub

            try:
                base_config = TelemetryConfig.from_env()
                telemetry_config = evolve(
                    base_config,
                    service_name="supsrc",
                    logging=LoggingConfig(
                        console_formatter="json",
                        default_level="TRACE",
                        das_emoji_prefix_enabled=True,
                        logger_name_emoji_prefix_enabled=True,
                        log_file=log_file_path,
                    ),
                )
                hub = get_hub()
                hub.initialize_foundation(telemetry_config)

                # Register eventset
                try:
                    from provide.foundation.eventsets.registry import register_event_set

                    from supsrc.telemetry import SUPSRC_EVENT_SET

                    register_event_set(SUPSRC_EVENT_SET)
                except Exception:
                    pass

                # Suppress all logging to prevent TUI flicker during initialization
                # Set root logger to CRITICAL to suppress everything except critical errors
                root_logger = logging.getLogger()
                root_logger.setLevel(logging.CRITICAL)

                # Also set all known loggers to CRITICAL
                for name in list(logging.root.manager.loggerDict.keys()):
                    logging.getLogger(name).setLevel(logging.CRITICAL)

                # Remove console handlers to prevent any output
                for logger_obj in [root_logger] + [
                    logging.getLogger(name) for name in logging.root.manager.loggerDict
                ]:
                    for handler in [
                        h
                        for h in logger_obj.handlers
                        if isinstance(h, logging.StreamHandler)
                        and not isinstance(h, logging.FileHandler)
                    ]:
                        logger_obj.removeHandler(handler)

            except Exception:
                pass

            log.info("Initializing interactive dashboard...", config_path=str(config_path))
            # Run the TUI app (stderr still suppressed)
            app = SupsrcTuiApp(config_path=config_path, cli_shutdown_event=_shutdown_requested)
            app.run()

        except KeyboardInterrupt:
            sys.stderr = _original_stderr
            click.echo("\nAborted by user.", err=True)
            ctx.exit(1)
        except Exception as e:
            sys.stderr = _original_stderr
            click.echo(f"\nAn error occurred: {e}", err=True)
            ctx.exit(1)
        finally:
            sys.stderr = _original_stderr


# 🔼⚙️🔚
