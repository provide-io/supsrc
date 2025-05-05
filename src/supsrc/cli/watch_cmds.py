# file: src/supsrc/cli/watch_cmds.py

import asyncio
import signal
import sys
import logging
import os
from pathlib import Path
from typing import Any

import click
import structlog
# Use absolute imports
from supsrc.telemetry import StructLogger
from supsrc.runtime.orchestrator import WatchOrchestrator

# --- Try importing TUI App Class ---
# This will fail if 'textual' is not installed OR if app.py has errors.
try:
    from supsrc.tui.app import SupsrcTuiApp
    TEXTUAL_AVAILABLE = True
    log_tui = structlog.get_logger("cli.watch.tui_check")
    log_tui.debug("Successfully imported supsrc.tui.app.SupsrcTuiApp.")
except ImportError as e:
    # Catch the ImportError if textual is missing or app.py fails to import
    TEXTUAL_AVAILABLE = False
    SupsrcTuiApp = None # Define as None for type checker clarity below
    log_tui = structlog.get_logger("cli.watch.tui_check")
    log_tui.debug("Failed to import supsrc.tui.app. Possible missing 'supsrc[tui]' install or error in tui module.", error=str(e))


log: StructLogger = structlog.get_logger("cli.watch")

# --- Global Shutdown Event & Signal Handler (remains the same) ---
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


# --- Click Command Definition (remains the same) ---
@click.command(name="watch")
@click.option(
    '-c', '--config-path',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True, envvar='SUPSRC_CONF',
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).", show_envvar=True,
)
@click.option(
    '--tui', is_flag=True, default=False,
    help="Run with an interactive Text User Interface (requires 'supsrc[tui]')."
)
@click.pass_context
def watch_cli(ctx: click.Context, config_path: Path, tui: bool):
    """Monitor configured repositories for changes and trigger actions."""
    def _cli_safe_log(level: str, msg: str, **kwargs):
        try: getattr(log, level)(msg, **kwargs)
        except Exception: print(f"LOGGING ERROR: {msg} {kwargs}", file=sys.stderr)

    if tui:
        if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None: # Check the flag and that the class symbol exists
            click.echo("Error: TUI mode requires 'supsrc[tui]' to be installed and importable.", err=True)
            click.echo("Hint: pip install 'supsrc[tui]' or check for errors in src/supsrc/tui/app.py", err=True)
            ctx.exit(1)

        _cli_safe_log("info", "Initializing TUI mode...")
        app = SupsrcTuiApp(config_path=config_path, cli_shutdown_event=_shutdown_requested)
        app.run()
        _cli_safe_log("info", "TUI application finished.")

    else:
        # --- Standard Mode Logic (remains the same) ---
        _cli_safe_log("info", "Initializing standard 'watch' command (non-TUI)")
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        signals_to_handle = (signal.SIGINT, signal.SIGTERM); handlers_added = False
        _cli_safe_log("debug", f"Adding signal handlers to loop {id(loop)}")
        try:
            for sig in signals_to_handle: loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_handle_signal_async(s))); handlers_added = True
            _cli_safe_log("debug", f"Added signal handlers")
        except Exception as e: _cli_safe_log("error", "Failed to add signal handlers", error=str(e), exc_info=True)

        orchestrator = WatchOrchestrator(config_path=config_path, shutdown_event=_shutdown_requested, app=None)
        exit_code = 0
        try:
            _cli_safe_log("debug", "Creating main orchestrator task...")
            main_task = loop.create_task(orchestrator.run(), name="OrchestratorRun")
            _cli_safe_log("debug", f"Running event loop {id(loop)}...")
            loop.run_until_complete(main_task)
            _cli_safe_log("debug", "Orchestrator task completed normally.")
        except KeyboardInterrupt: _cli_safe_log("warning", "KeyboardInterrupt caught. Signalling shutdown."); _shutdown_requested.set(); exit_code = 130
        except asyncio.CancelledError: _cli_safe_log("warning", "Main orchestrator task cancelled."); _shutdown_requested.set(); exit_code = 1
        except Exception as e: _cli_safe_log("critical", "Orchestrator run failed", error=str(e), exc_info=True); _shutdown_requested.set(); exit_code = 1
        finally:
            _cli_safe_log("debug", f"watch_cli (non-TUI) finally block. Loop closed: {loop.is_closed()}")
            if handlers_added and not loop.is_closed():
                 _cli_safe_log("debug", "Removing signal handlers")
                 for sig in signals_to_handle:
                      try: loop.remove_signal_handler(sig)
                      except (ValueError, RuntimeError, Exception) as e: _cli_safe_log("debug", f"Error removing signal handler for {signal.Signals(sig).name}", error=str(e))
            _cli_safe_log("debug", "Shutting down standard logging..."); logging.shutdown()
            _cli_safe_log("debug", f"Closing event loop {id(loop)}")
            try:
                 if not loop.is_closed(): loop.run_until_complete(loop.shutdown_asyncgens()); loop.close(); _cli_safe_log("info", "Event loop closed.")
                 else: _cli_safe_log("warning", "Event loop already closed.")
            except Exception as e: _cli_safe_log("error", "Error closing event loop", error=str(e), exc_info=True)
        _cli_safe_log("info", "'watch' command finished (non-TUI mode).")
        if exit_code != 0: sys.exit(exit_code)

# 🔼⚙️
