# src/supsrc/cli/watch_cmds.py

import asyncio
import signal
from pathlib import Path

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import load_config
from supsrc.utils.directories import SupsrcDirectories

try:
    from supsrc.tui.app import SupsrcTuiApp

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    SupsrcTuiApp = None

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
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def sui_cli(ctx: click.Context, config_path: Path, **kwargs):
    """Supsrc User Interface - Interactive dashboard for monitoring repositories."""
    # Step 1: Check for TUI dependencies before configuring logging.
    if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None:
        # Set up basic console logging to ensure the error is visible.
        # Foundation's CLI framework handles logging setup via decorators
        log.error("TUI dependencies not installed for 'sui' command.")
        click.echo(
            "Error: The 'sui' command requires the 'textual' library, provided by the 'tui' extra.",
            err=True,
        )
        click.echo("Hint: pip install 'supsrc[tui]' or uv pip install 'supsrc[tui]'", err=True)
        ctx.exit(1)
        return

    # Step 2: Dependencies are available. Now run the TUI application.
    # Enable debug file logging for troubleshooting
    import logging

    from provide.foundation import LoggingConfig, TelemetryConfig, get_hub
    from provide.foundation.streams.core import set_log_stream_for_testing

    from supsrc.utils.streams import NoOpStream

    log.info("Initializing interactive dashboard...")

    # Determine log file path using .supsrc structure if possible
    log_file_path = Path("/tmp/supsrc_tui_debug.log")  # fallback
    try:
        config = load_config(config_path)
        # Find first enabled repository for log directory
        for _repo_id, repo_config in config.repositories.items():
            if repo_config.enabled and repo_config._path_valid:
                log_file_path = (
                    SupsrcDirectories.get_log_dir(repo_config.path) / "supsrc_tui_debug.log"
                )
                break
    except Exception as e:
        log.warning("Failed to determine TUI log directory, using temp", error=str(e))

    log.info("🐛 Debug logging available", log_file=str(log_file_path))

    # Suppress all console output from Foundation by setting NoOpStream
    # This must be done BEFORE Foundation initialization
    set_log_stream_for_testing(NoOpStream())

    # Set up file logging for debugging using Foundation public API
    try:
        # Start with from_env() to preserve OpenObserve/OTLP auto-configuration,
        # then override service_name and logging settings
        from attrs import evolve

        base_config = TelemetryConfig.from_env()
        config = evolve(
            base_config,
            service_name="supsrc",  # Override service name for OTLP/telemetry
            logging=LoggingConfig(
                console_formatter="json",
                default_level="TRACE",
                das_emoji_prefix_enabled=True,
                logger_name_emoji_prefix_enabled=True,
                log_file=log_file_path,  # Enable file logging
            ),
        )

        # Use new Foundation API
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

        # CRITICAL: Remove all console handlers to prevent app logs from appearing in TUI
        # Must be done AFTER Foundation initialization
        root_logger = logging.getLogger()
        all_loggers = [root_logger] + [
            logging.getLogger(name) for name in logging.root.manager.loggerDict
        ]

        for logger in all_loggers:
            console_handlers = [
                h
                for h in logger.handlers
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            ]
            for handler in console_handlers:
                logger.removeHandler(handler)

        # Also disable propagation for structlog loggers to prevent console output
        for name in logging.root.manager.loggerDict:
            if any(pattern in name for pattern in ["provide.foundation", "supsrc"]):
                logger = logging.getLogger(name)
                logger.propagate = False

        log.debug("Debug file logging configured")
    except Exception as e:
        log.warning("Failed to setup debug file logging", error=str(e))

    try:
        app = SupsrcTuiApp(config_path=config_path, cli_shutdown_event=_shutdown_requested)
        app.run()
        log.info("Interactive dashboard finished.")
    except KeyboardInterrupt:
        log.warning("Shutdown requested via KeyboardInterrupt during TUI run.")
        click.echo("\nAborted!")
        ctx.exit(1)
    except Exception as e:
        log.critical("The TUI application crashed unexpectedly.", error=str(e), exc_info=True)
        click.echo(f"\nAn unexpected error occurred in the TUI: {e}", err=True)
        ctx.exit(1)


# 🔼⚙️
