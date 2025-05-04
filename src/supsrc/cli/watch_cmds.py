#
# supsrc/cli/watch_cmds.py
#
"""
CLI command for watching repositories ('supsrc watch').
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Coroutine, Any, Set

import click
import structlog

from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent


log: StructLogger = structlog.get_logger("cli.watch")

# --- Globals for Signal Handling ---
_shutdown_requested = asyncio.Event()
_running_tasks: Set[asyncio.Task[Any]] = set()

# --- Signal Handling ---
def _handle_signal(sig: int, loop: asyncio.AbstractEventLoop):
    """Sets the shutdown event when a signal is received."""
    signame = signal.Signals(sig).name
    log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    _shutdown_requested.set()
    # Optional: Add a second Ctrl+C handler for forceful exit?
    # loop.remove_signal_handler(sig)
    # loop.add_signal_handler(sig, lambda: loop.stop()) # Force stop on second signal


# --- Core Async Functions ---

async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    monitor_service: MonitoringService
) -> None:
    """Consumes and logs events from the monitoring queue."""
    log.info("Event consumer started, waiting for file events...")
    while True:
        try:
            # Wait for an event or shutdown signal
            get_task = asyncio.create_task(event_queue.get())
            done, pending = await asyncio.wait(
                {get_task, asyncio.create_task(_shutdown_requested.wait())},
                return_when=asyncio.FIRST_COMPLETED
            )

            # Check if shutdown was requested
            if _shutdown_requested.is_set():
                log.info("Shutdown requested, stopping event consumer.")
                get_task.cancel() # Cancel the pending queue read if any
                break # Exit the loop

            # Process the event if received
            event = get_task.result() # Should be done if shutdown wasn't triggered
            log.debug(
                "Received event from queue",
                repo_id=event.repo_id,
                type=event.event_type,
                path=str(event.src_path),
                is_dir=event.is_directory,
                dest=str(event.dest_path) if event.dest_path else None
            )
            # --- Placeholder for Phase 3 ---
            # Here, dispatch the event to the specific repository's state handler/task
            # e.g., await dispatch_event_to_repo(event)
            # --- End Placeholder ---

            event_queue.task_done() # Signal that the event has been processed

        except asyncio.CancelledError:
             log.info("Event consumer task cancelled.")
             break
        except Exception as e:
            log.error("Error in event consumer loop", error=str(e), exc_info=True)
            # Decide whether to continue or break on errors
            await asyncio.sleep(1) # Avoid tight loop on persistent errors


async def run_watch(config_path: Path) -> None:
    """Main asynchronous function to run the watch command."""
    global _running_tasks
    log.info("Starting 'watch' command execution", config_path=str(config_path))

    # 1. Load Configuration
    try:
        config: SupsrcConfig = load_config(config_path)
        log.info("Configuration loaded successfully for watch command.")
        # Log basic info about loaded repos
        enabled_repos = [rid for rid, rcfg in config.repositories.items() if rcfg.enabled]
        log.info("Enabled repositories found", count=len(enabled_repos), repos=enabled_repos)
        if not enabled_repos:
             log.warning("No enabled repositories found in configuration. Exiting.")
             return

    except ConfigurationError as e:
        log.error("Failed to load configuration", error=str(e), path=str(config_path))
        # click.echo(f"Error: {e}", err=True) # Logged already, avoid double print
        sys.exit(1) # Exit if config fails

    # 2. Setup Monitoring Service
    event_queue: asyncio.Queue[MonitoredEvent] = asyncio.Queue()
    monitor_service = MonitoringService(event_queue)

    # 3. Add Repositories to Monitor
    setup_errors = 0
    for repo_id, repo_config in config.repositories.items():
        if repo_config.enabled: # Only add enabled ones
            try:
                monitor_service.add_repository(repo_id, repo_config)
            except MonitoringSetupError as e:
                log.error("Failed to setup monitoring for repository", repo_id=repo_id, error=str(e))
                setup_errors += 1
            except Exception as e:
                 log.error("Unexpected error adding repository", repo_id=repo_id, error=str(e), exc_info=True)
                 setup_errors += 1


    if setup_errors > 0:
         log.warning(f"Encountered {setup_errors} error(s) during monitoring setup.")
         # Decide if we should continue if *some* repos failed setup
         # For now, we continue if at least one succeeded.
         if not monitor_service._handlers: # Check internal dict if needed
              log.critical("No repositories could be successfully setup for monitoring. Exiting.")
              sys.exit(1)


    # 4. Start Monitoring & Event Consumption
    try:
        monitor_service.start() # Starts the observer thread
        if not monitor_service.is_running and monitor_service._handlers:
             log.critical("Monitoring service failed to start despite having handlers. Exiting.")
             sys.exit(1)
        elif not monitor_service.is_running:
             log.info("Monitoring service not started (no repositories?). Exiting.")
             return # Exit cleanly if nothing to monitor


        # Start the event consumer task
        consumer_task = asyncio.create_task(consume_events(event_queue, monitor_service))
        _running_tasks.add(consumer_task)
        consumer_task.add_done_callback(_running_tasks.discard) # Clean up task set

        # --- Placeholder for Phase 3 ---
        # Start per-repository processing tasks here
        # for repo_id in monitor_service._handlers.keys():
        #    repo_task = asyncio.create_task(process_repo_events(repo_id, ...))
        #    _running_tasks.add(repo_task)
        #    repo_task.add_done_callback(_running_tasks.discard)
        # --- End Placeholder ---


        # 5. Wait for Shutdown Signal
        log.info("Monitoring active. Press Ctrl+C to stop.")
        await _shutdown_requested.wait() # Keep running until signal is received
        log.info("Shutdown initiated...")

    except SupsrcError as e:
        log.critical("A critical supsrc error occurred during watch", error=str(e), exc_info=True)
    except Exception as e:
        log.critical("An unexpected error occurred during watch", error=str(e), exc_info=True)
    finally:
        log.info("Starting cleanup...")

        # Cancel all running tasks
        if _running_tasks:
            log.debug(f"Cancelling {_running_tasks} running task(s)...")
            for task in list(_running_tasks): # Iterate over a copy
                if not task.done():
                    task.cancel()
            # Wait briefly for tasks to finish cancellation
            await asyncio.gather(*_running_tasks, return_exceptions=True)
            log.debug("Running tasks cancelled.")

        # Stop the monitoring service (joins the observer thread)
        if monitor_service.is_running:
            monitor_service.stop()

        # Ensure queue is processed? (May not be needed if consumer task is cancelled)
        # try:
        #     await asyncio.wait_for(event_queue.join(), timeout=5.0)
        #     log.info("Event queue processed.")
        # except asyncio.TimeoutError:
        #     log.warning("Timeout waiting for event queue to finish processing.")

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
@click.pass_context # Get context from the parent group (for log level etc)
def watch_cli(ctx: click.Context, config_path: Path):
    """
    Monitor configured repositories for changes and trigger actions.
    """
    log.info("Initializing 'watch' command")

    # Setup signal handling for graceful shutdown
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _handle_signal, signal.SIGINT, loop)
        loop.add_signal_handler(signal.SIGTERM, _handle_signal, signal.SIGTERM, loop)
    except NotImplementedError:
         # Windows doesn't support add_signal_handler for SIGTERM etc.
         # Consider alternative shutdown mechanisms for Windows if needed.
         log.warning("Signal handlers for SIGTERM/SIGINT could not be added (possibly on Windows). Ctrl+C might not guarantee graceful shutdown.")


    # Run the main async function
    try:
        asyncio.run(run_watch(config_path))
    except KeyboardInterrupt:
         # This might catch Ctrl+C if signal handlers fail or aren't setup
         log.warning("KeyboardInterrupt caught directly. Attempting shutdown.")
         # Ensure shutdown event is set if it wasn't by signal handler
         if not _shutdown_requested.is_set():
              _shutdown_requested.set()
         # Re-run loop briefly to allow cleanup? Less clean.
         # loop.run_until_complete(asyncio.sleep(0.1)) # Give cleanup a chance
    finally:
         # Clean up signal handlers
         try:
              loop.remove_signal_handler(signal.SIGINT)
              loop.remove_signal_handler(signal.SIGTERM)
         except NotImplementedError:
              pass # Ignore if they couldn't be added
         except Exception as e:
              log.error("Error removing signal handlers", error=str(e))


    log.info("'watch' command finished.")
    # Exit code is handled implicitly by exceptions or normal exit

# 🔼⚙️
