# src/supsrc/cli/watch_cmds.py

import asyncio
import signal
from pathlib import Path

import click
import structlog
from provide.foundation.cli.decorators import logging_options
from structlog.typing import FilteringBoundLogger as StructLogger

try:
    from supsrc.tui.app import SupsrcTuiApp

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    SupsrcTuiApp = None

log: StructLogger = structlog.get_logger("cli.watch")

_shutdown_requested = asyncio.Event()


async def _handle_signal_async(sig: int):
    signame = signal.Signals(sig).name
    base_log = structlog.get_logger("cli.watch.signal")
    base_log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if not _shutdown_requested.is_set():
        base_log.info("Setting shutdown requested event.")
        _shutdown_requested.set()
    else:
        base_log.warning("Shutdown already requested, signal ignored.")


@click.command(name="watch")
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
def watch_cli(ctx: click.Context, config_path: Path, **kwargs):
    """Interactive dashboard for monitoring repositories."""
    # Step 1: Check for TUI dependencies before configuring logging.
    if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None:
        # Set up basic console logging to ensure the error is visible.
        # Foundation's CLI framework handles logging setup via decorators
        log.error("TUI dependencies not installed for 'watch' command.")
        click.echo(
            "Error: The 'watch' command requires the 'textual' library, provided by the 'tui' extra.",
            err=True,
        )
        click.echo("Hint: pip install 'supsrc[tui]' or uv pip install 'supsrc[tui]'", err=True)
        ctx.exit(1)
        return

    # Step 2: Dependencies are available. Now run the TUI application.
    # Enable debug file logging for troubleshooting
    import logging

    from provide.foundation import LoggingConfig, TelemetryConfig, get_hub

    log.info("Initializing interactive dashboard...")
    log.info("🐛 Debug logging available at /tmp/supsrc_tui_debug.log")

    # Set up file logging for debugging using Foundation public API
    try:
        config = TelemetryConfig(
            logging=LoggingConfig(
                console_formatter="key_value",
                default_level="DEBUG",
                das_emoji_prefix_enabled=True,
                logger_name_emoji_prefix_enabled=True,
            )
        )

        # Use public Foundation API
        hub = get_hub()
        hub.initialize_foundation(config)

        # CRITICAL: Remove all console handlers to prevent app logs from appearing in TUI
        root_logger = logging.getLogger()
        console_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        for handler in console_handlers:
            root_logger.removeHandler(handler)

        # Add debug file handler
        file_handler = logging.FileHandler("/tmp/supsrc_tui_debug.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # Set file handler formatter to include more detail for debugging
        import structlog

        file_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(sort_keys=True)
        )
        file_handler.setFormatter(file_formatter)

        root_logger.addHandler(file_handler)

        # Set root logger level to capture everything
        root_logger.setLevel(logging.DEBUG)

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
