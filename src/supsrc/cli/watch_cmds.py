#
# src/supsrc/cli/watch_cmds.py
#

import asyncio
import signal
import sys
import logging # For logging.shutdown
import os # For potential future use
from pathlib import Path
from typing import Any

import click
import structlog
import attrs # For potential future use

# Use absolute imports
from supsrc.telemetry import StructLogger
from supsrc.runtime.orchestrator import WatchOrchestrator # Use the orchestrator

log: StructLogger = structlog.get_logger("cli.watch") # Logger for the CLI layer

# --- Global Shutdown Event ---
_shutdown_requested = asyncio.Event()

# --- Async Signal Handler ---
async def _handle_signal_async(sig: int):
    """Async wrapper for signal handling logic."""
    signame = signal.Signals(sig).name
    base_log = structlog.get_logger("cli.watch.signal")
    base_log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if _shutdown_requested.is_set():
        base_log.warning("Shutdown already requested, signal ignored.")
        return
    base_log.info("Setting shutdown requested event.")
    _shutdown_requested.set()

# --- Click Command Definition ---

@click.command(name="watch")
@click.option(
    '-c', '--config-path',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar='SUPSRC_CONF',
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@click.pass_context
def watch_cli(ctx: click.Context, config_path: Path):
    """
    Monitor configured repositories for changes and trigger actions (commit/push).
    """
    # Safe logging helper specific to the CLI layer's final shutdown
    def _cli_safe_log(level: str, msg: str, **kwargs):
        """Helper to suppress logging errors during final CLI shutdown."""
        try:
            getattr(log, level)(msg, **kwargs)
        except (BrokenPipeError, RuntimeError, ValueError) as e:
            pass

    _cli_safe_log("info", "Initializing 'watch' command")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    signals_to_handle = (signal.SIGINT, signal.SIGTERM)
    handlers_added = False

    _cli_safe_log("debug", f"Adding signal handlers to loop {id(loop)}")
    try:
        for sig in signals_to_handle:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_handle_signal_async(s))
            )
            _cli_safe_log("debug", f"Added signal handler for {signal.Signals(sig).name}")
        handlers_added = True
    except NotImplementedError:
         _cli_safe_log("warning", "Signal handlers could not be added (not supported on this platform/loop).")
    except Exception as e:
         _cli_safe_log("error", "Failed to add signal handlers", error=str(e), exc_info=True)

    # --- Create and Run Orchestrator ---
    orchestrator = WatchOrchestrator(config_path=config_path, shutdown_event=_shutdown_requested)
    main_task = None
    exit_code = 0

    try:
        _cli_safe_log("debug", "Creating main orchestrator task...")
        main_task = loop.create_task(orchestrator.run(), name="OrchestratorRun")
        _cli_safe_log("debug", f"Running event loop {id(loop)} until orchestrator task completes...")
        loop.run_until_complete(main_task)
        _cli_safe_log("debug", "Orchestrator task completed normally.")

    except KeyboardInterrupt:
         _cli_safe_log("warning", "KeyboardInterrupt caught directly in watch_cli. Signalling shutdown.")
         if not _shutdown_requested.is_set():
              _shutdown_requested.set()
         exit_code = 130

    except asyncio.CancelledError:
         _cli_safe_log("warning", "Main orchestrator task was cancelled unexpectedly.")
         if not _shutdown_requested.is_set(): _shutdown_requested.set()
         exit_code = 1

    except Exception as e:
         _cli_safe_log("critical", "Orchestrator run failed with unhandled exception", error=str(e), exc_info=True)
         if not _shutdown_requested.is_set(): _shutdown_requested.set()
         exit_code = 1

    finally:
         # --- Final CLI Layer Cleanup ---
         _cli_safe_log("debug", f"watch_cli finally block entered. Loop {id(loop)} running: {loop.is_running()}, closed: {loop.is_closed()}")

         # --- Remove Signal Handlers ---
         if handlers_added and not loop.is_closed():
             _cli_safe_log("debug", f"Removing signal handlers from loop {id(loop)}")
             for sig in signals_to_handle:
                 try:
                     removed = loop.remove_signal_handler(sig)
                     _cli_safe_log("debug", f"Attempted removal of signal handler for {signal.Signals(sig).name} (found/removed: {removed})")
                 except (ValueError, RuntimeError) as e:
                     _cli_safe_log("debug", f"Signal handler for {signal.Signals(sig).name} not found or loop closing during removal.", error=str(e))
                 except Exception as e:
                     _cli_safe_log("error", f"Error removing signal handler for {signal.Signals(sig).name}", error=str(e), exc_info=True)

         # --- Explicitly Shutdown Standard Logging ---
         _cli_safe_log("debug", "Attempting standard logging shutdown...")
         try:
             logging.shutdown()
             _cli_safe_log("debug", "Standard logging shutdown completed.")
         except Exception as log_shutdown_exc:
             _cli_safe_log("error", "Error during logging.shutdown()", error=str(log_shutdown_exc), exc_info=True)

         # --- Close the Event Loop ---
         _cli_safe_log("debug", f"Closing event loop {id(loop)}")
         try:
             if not loop.is_closed():
                 if sys.version_info >= (3, 6):
                     loop.run_until_complete(loop.shutdown_asyncgens())
                     _cli_safe_log("debug", "Async generators shut down.")
                 loop.close()
                 _cli_safe_log("info", "Event loop closed.")
             else:
                 _cli_safe_log("warning", "Event loop was already closed before final cleanup.")
         except Exception as loop_close_exc:
             _cli_safe_log("error", "Error during event loop closing", error=str(loop_close_exc), exc_info=True)

    _cli_safe_log("info", "'watch' command finished.")
    if exit_code != 0:
        sys.exit(exit_code)

# 🔼⚙️
