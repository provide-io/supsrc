#
# src/supsrc/cli/watch_cmds.py
#
"""
CLI command for watching repositories ('supsrc watch').
"""

import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Coroutine, Any, Set

import click
import structlog

# Use absolute imports
from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent


log: StructLogger = structlog.get_logger("cli.watch")

# --- Globals for Signal Handling ---
_shutdown_requested = asyncio.Event()
_running_tasks: Set[asyncio.Task[Any]] = set()

# --- Async Signal Handler ---
async def _handle_signal_async(sig: int):
    """Async wrapper for signal handling logic."""
    signame = signal.Signals(sig).name
    log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if _shutdown_requested.is_set():
        log.warning("Shutdown already requested, signal ignored.")
        return
    log.info("Setting shutdown requested event.")
    _shutdown_requested.set()

# --- Core Async Functions ---
async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    monitor_service: MonitoringService
) -> None:
    # ... (No changes from previous version) ...
    log.info("Event consumer started, waiting for file events...")
    while True:
        try:
            get_task = asyncio.create_task(event_queue.get())
            shutdown_task = asyncio.create_task(_shutdown_requested.wait())
            log.debug("Consumer waiting for event or shutdown...")
            done, pending = await asyncio.wait(
                {get_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
            )
            log.debug("Consumer woke up.", done_tasks=len(done), pending_tasks=len(pending))
            if shutdown_task in done or _shutdown_requested.is_set():
                log.info("Consumer detected shutdown request.")
                if not get_task.done(): log.debug("Cancelling pending event get task..."); get_task.cancel()
                else:
                     log.debug("Checking potentially completed event task during shutdown...")
                     try: await get_task
                     except asyncio.CancelledError: log.debug("Event task was cancelled.")
                     except Exception as e: log.warning("Exception during final event get on shutdown", error=str(e), exc_info=True)
                log.info("Exiting event consumer loop."); break
            if get_task in done:
                event = get_task.result()
                log.debug(
                    "Received event from queue", repo_id=event.repo_id, type=event.event_type,
                    path=str(event.src_path), is_dir=event.is_directory,
                    dest=str(event.dest_path) if event.dest_path else None
                )
                event_queue.task_done()
            else:
                 log.warning("Consumer loop woke up unexpectedly.")
                 if get_task in pending: get_task.cancel()
                 if shutdown_task in pending: shutdown_task.cancel()
        except asyncio.CancelledError: log.info("Event consumer task explicitly cancelled."); break
        except Exception as e: log.error("Error in event consumer loop", error=str(e), exc_info=True); await asyncio.sleep(1)


async def run_watch(config_path: Path) -> None:
    # ... (No changes from previous version) ...
    global _running_tasks
    log.info("Starting 'watch' command execution", config_path=str(config_path))
    monitor_service: MonitoringService | None = None
    event_queue: asyncio.Queue[MonitoredEvent] | None = None
    try:
        log.debug("run_watch: Loading config...")
        try:
            config: SupsrcConfig = load_config(config_path)
            log.info("Configuration loaded successfully for watch command.")
            enabled_repos = [rid for rid, rcfg in config.repositories.items() if rcfg.enabled]
            log.info("Enabled repositories found", count=len(enabled_repos), repos=enabled_repos)
            if not enabled_repos: log.warning("No enabled repositories found in configuration. Exiting."); return
        except ConfigurationError as e: log.error("Failed to load configuration", error=str(e), path=str(config_path)); sys.exit(1)
        log.debug("run_watch: Setting up monitoring service...")
        event_queue = asyncio.Queue()
        monitor_service = MonitoringService(event_queue)
        log.debug("run_watch: Adding repositories...")
        setup_errors = 0
        for repo_id, repo_config in config.repositories.items():
            if repo_config.enabled:
                try: monitor_service.add_repository(repo_id, repo_config)
                except MonitoringSetupError as e: log.error("Failed to setup monitoring for repository", repo_id=repo_id, error=str(e)); setup_errors += 1
                except Exception as e: log.error("Unexpected error adding repository", repo_id=repo_id, error=str(e), exc_info=True); setup_errors += 1
        if setup_errors > 0:
             log.warning(f"Encountered {setup_errors} error(s) during monitoring setup.")
             if not monitor_service._handlers: log.critical("No repositories could be successfully setup for monitoring. Exiting."); sys.exit(1)
        log.debug("run_watch: Starting monitor service...")
        monitor_service.start()
        if not monitor_service.is_running and monitor_service._handlers: log.critical("Monitoring service failed to start despite having handlers. Exiting."); sys.exit(1)
        elif not monitor_service.is_running: log.info("Monitoring service not started (no enabled/valid repositories?). Exiting."); return
        log.debug("run_watch: Creating consumer task...")
        consumer_task = asyncio.create_task(consume_events(event_queue, monitor_service), name="EventConsumer")
        _running_tasks.add(consumer_task)
        consumer_task.add_done_callback(_running_tasks.discard)
        # --- Placeholder Tasks ---
        log.info("Monitoring active. Press Ctrl+C to stop.")
        await _shutdown_requested.wait()
        log.info("Shutdown initiated...")
    except SupsrcError as e: log.critical("A critical supsrc error occurred during watch", error=str(e), exc_info=True)
    except asyncio.CancelledError:
         log.warning("run_watch task was cancelled.")
         if not _shutdown_requested.is_set(): _shutdown_requested.set()
    except Exception as e: log.critical("An unexpected error occurred during watch", error=str(e), exc_info=True)
    finally:
        log.info("Starting cleanup...")
        if _running_tasks:
            log.debug(f"Cancelling {len(_running_tasks)} running task(s)...", tasks=[t.get_name() for t in _running_tasks])
            tasks_to_cancel = list(_running_tasks)
            for task in tasks_to_cancel:
                if not task.done(): log.debug(f"Cancelling task: {task.get_name()}"); task.cancel()
            log.debug("Gathering cancelled tasks...")
            gathered_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            log.debug("Running tasks cancelled.", results=gathered_results)
        else: log.debug("No running tasks found to cancel.")
        if monitor_service is not None:
            if monitor_service.is_running:
                 log.debug("Stopping monitoring service (includes joining observer thread)...")
                 await monitor_service.stop()
                 log.debug("Monitoring service stop completed.")
            else: log.debug("Monitoring service was not running or already stopped.")
        else: log.debug("Monitoring service was not initialized.")
        log.info("supsrc watch finished.")


# --- Click Command Definition ---

@click.command(name="watch")
@click.option(
    '-c', '--config-path',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    help="Path to the supsrc configuration file."
)
@click.pass_context
def watch_cli(ctx: click.Context, config_path: Path):
    """
    Monitor configured repositories for changes and trigger actions.
    """
    log.info("Initializing 'watch' command")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    signals_to_handle = (signal.SIGINT, signal.SIGTERM)
    handlers_added = True

    log.debug(f"Adding signal handlers to loop {id(loop)}")
    try:
        for sig in signals_to_handle:
            current_sig = sig
            loop.add_signal_handler(
                current_sig,
                lambda s=current_sig: asyncio.create_task(_handle_signal_async(s))
            )
            log.debug(f"Added signal handler for {signal.Signals(sig).name}")
    except NotImplementedError:
         handlers_added = False
         log.warning("Signal handlers for SIGTERM/SIGINT could not be added (possibly on Windows). Ctrl+C might not guarantee graceful shutdown.")
    except Exception as e:
         handlers_added = False
         log.error("Failed to add signal handlers", error=str(e), exc_info=True)

    main_task = None
    try:
        log.debug(f"Calling loop.run_until_complete(run_watch(config_path='{config_path}'))")
        main_task = loop.create_task(run_watch(config_path), name="MainRunWatch")
        loop.run_until_complete(main_task)
        log.debug("loop.run_until_complete finished normally")

    except KeyboardInterrupt:
         log.warning("KeyboardInterrupt caught directly in watch_cli. Attempting graceful shutdown.")
         if not _shutdown_requested.is_set():
              _shutdown_requested.set()
    except asyncio.CancelledError:
         log.warning("Main run_watch task was cancelled.")
    finally:
         log.debug("watch_cli finally block entered")

         if main_task and not main_task.done():
             log.debug("Explicitly cancelling main task in finally")
             main_task.cancel()
             try:
                 # Still attempt to run gather on the main task to process cancellation
                 loop.run_until_complete(asyncio.gather(main_task, return_exceptions=True))
             except asyncio.CancelledError:
                 log.debug("Main task cancellation processed during final gather")
             except Exception as e:
                 log.error(f"Error during final main task gather: {e}", exc_info=True)

         if handlers_added:
             log.debug(f"Removing signal handlers from loop {id(loop)}")
             for sig in signals_to_handle:
                 try:
                    # remove_signal_handler might fail if loop is closing/closed
                    if not loop.is_closed():
                        removed = loop.remove_signal_handler(sig)
                        log.debug(f"Removed signal handler for {signal.Signals(sig).name} (found: {removed})")
                 except ValueError:
                     log.debug(f"Signal handler for {signal.Signals(sig).name} not found (may be expected).")
                 except Exception as e:
                     log.error(f"Error removing signal handler for {signal.Signals(sig).name}", error=str(e), exc_info=True)

         log.debug(f"Closing event loop {id(loop)}")
         try:
              # --- MODIFIED FINAL CLEANUP START ---
              tasks = asyncio.all_tasks(loop=loop)
              # No longer filter asyncio.current_task()
              if tasks:
                   log.debug(f"Cancelling {len(tasks)} remaining tasks before loop close: {[t.get_name() for t in tasks]}")
                   for task in tasks:
                        task.cancel()
                   # Wait for cancellation to complete *by running the loop again briefly*
                   log.debug("Gathering remaining tasks after cancellation...")
                   loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                   log.debug("Remaining tasks gathered/cancelled")
              else:
                  log.debug("No remaining tasks found before loop close.")

              if not loop.is_closed():
                 log.debug("Closing the loop object.")
                 loop.close()
                 log.info("Event loop closed.")
              else:
                 log.warning("Event loop was already closed.")
              # --- MODIFIED FINAL CLEANUP END ---

         except Exception as e:
             # Catch potential RuntimeErrors if loop state is unexpected
             log.error("Error during final task cancellation or loop closing", error=str(e), exc_info=True)

    log.info("'watch' command finished.")


# 🔼⚙️
