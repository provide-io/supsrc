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
async def _handle_signal_async(sig: int): # Removed loop parameter, get it if needed
    """Async wrapper for signal handling logic."""
    timestamp = time.time()
    signame = signal.Signals(sig).name
    print(f"[{timestamp:.3f}] !!! Signal handler _handle_signal_async started for {signame} !!!", file=sys.stderr)
    log.warning("!!! Received shutdown signal !!!", signal=signame, signal_num=sig)

    if _shutdown_requested.is_set():
        print(f"[{timestamp:.3f}] !!! Shutdown already requested !!!", file=sys.stderr)
        log.warning("Shutdown already requested, signal ignored.")
        return

    print(f"[{timestamp:.3f}] !!! Setting shutdown_requested event... !!!", file=sys.stderr)
    _shutdown_requested.set()
    print(f"[{timestamp:.3f}] !!! Shutdown_requested event set. !!!", file=sys.stderr)
    log.info("Shutdown requested event set.")
    # Optional: Cancel tasks immediately here? Often better done in finally block
    # loop = asyncio.get_running_loop() # Get current loop if needed
    # for task in _running_tasks:
    #     task.cancel()

# --- Core Async Functions ---

async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    monitor_service: MonitoringService
) -> None:
    # ... (No changes needed in consume_events itself) ...
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
                log.warning(">>> Consumer detected shutdown request <<<")
                print(f"[{time.time():.3f}] >>> Consumer detected shutdown request <<<", file=sys.stderr)
                if not get_task.done():
                    log.debug("Cancelling pending event get task...")
                    get_task.cancel()
                else:
                     log.debug("Checking potentially completed event task during shutdown...")
                     try: await get_task
                     except asyncio.CancelledError: log.debug("Event task was cancelled.")
                     except Exception as e: log.warning("Exception during final event get on shutdown", error=str(e), exc_info=True)
                log.info("Exiting event consumer loop.")
                print(f"[{time.time():.3f}] >>> Consumer exiting loop <<<", file=sys.stderr)
                break
            if get_task in done:
                event = get_task.result()
                log.debug(
                    "Received event from queue", repo_id=event.repo_id, type=event.event_type,
                    path=str(event.src_path), is_dir=event.is_directory,
                    dest=str(event.dest_path) if event.dest_path else None
                )
                # --- Placeholder for Phase 3: Dispatch Event ---
                event_queue.task_done()
            else:
                 log.warning("Consumer loop woke up unexpectedly.")
                 if get_task in pending: get_task.cancel()
                 if shutdown_task in pending: shutdown_task.cancel()
        except asyncio.CancelledError:
             log.info("Event consumer task explicitly cancelled.")
             print(f"[{time.time():.3f}] >>> Consumer task cancelled <<<", file=sys.stderr)
             break
        except Exception as e:
            log.error("Error in event consumer loop", error=str(e), exc_info=True)
            await asyncio.sleep(1)


async def run_watch(config_path: Path) -> None:
    # ... (No changes needed in run_watch itself, keep the debugging prints) ...
    global _running_tasks
    print(f"[{time.time():.3f}] --- run_watch started ---", file=sys.stderr)
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
            if not enabled_repos:
                 log.warning("No enabled repositories found in configuration. Exiting.")
                 return
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
        print(f"[{time.time():.3f}] --- run_watch entering await _shutdown_requested.wait() ---", file=sys.stderr)
        await _shutdown_requested.wait()
        print(f"[{time.time():.3f}] --- run_watch passed await _shutdown_requested.wait() ---", file=sys.stderr)
        log.info("Shutdown initiated...")
    except SupsrcError as e: log.critical("A critical supsrc error occurred during watch", error=str(e), exc_info=True)
    except asyncio.CancelledError:
         log.warning("run_watch task was cancelled.")
         print(f"[{time.time():.3f}] --- run_watch task cancelled ---", file=sys.stderr)
         if not _shutdown_requested.is_set(): _shutdown_requested.set()
    except Exception as e: log.critical("An unexpected error occurred during watch", error=str(e), exc_info=True)
    finally:
        print(f"[{time.time():.3f}] --- run_watch entering finally block ---", file=sys.stderr)
        log.info("Starting cleanup...")
        if _running_tasks:
            log.debug(f"Cancelling {len(_running_tasks)} running task(s)...", tasks=[t.get_name() for t in _running_tasks])
            print(f"[{time.time():.3f}] --- Cancelling {len(_running_tasks)} tasks ---", file=sys.stderr)
            tasks_to_cancel = list(_running_tasks)
            for task in tasks_to_cancel:
                if not task.done(): log.debug(f"Cancelling task: {task.get_name()}"); task.cancel()
            log.debug("Gathering cancelled tasks...")
            gathered_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            log.debug("Running tasks cancelled.", results=gathered_results)
            print(f"[{time.time():.3f}] --- Tasks cancelled/gathered ---", file=sys.stderr)
        else: log.debug("No running tasks found to cancel."); print(f"[{time.time():.3f}] --- No tasks to cancel ---", file=sys.stderr)
        if monitor_service is not None:
            if monitor_service.is_running:
                 log.debug("Stopping monitoring service (includes joining observer thread)...")
                 print(f"[{time.time():.3f}] --- Calling await monitor_service.stop() ---", file=sys.stderr)
                 await monitor_service.stop()
                 log.debug("Monitoring service stop completed.")
                 print(f"[{time.time():.3f}] --- Finished await monitor_service.stop() ---", file=sys.stderr)
            else: log.debug("Monitoring service was not running or already stopped."); print(f"[{time.time():.3f}] --- Monitor service not running ---", file=sys.stderr)
        else: log.debug("Monitoring service was not initialized."); print(f"[{time.time():.3f}] --- Monitor service not initialized ---", file=sys.stderr)
        log.info("supsrc watch finished.")
        print(f"[{time.time():.3f}] --- run_watch finally block finished ---", file=sys.stderr)


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
    print(f"[{time.time():.3f}] +++ watch_cli started +++", file=sys.stderr)

    # --- MODIFIED SECTION START ---
    loop = asyncio.new_event_loop() # Create a new loop explicitly
    asyncio.set_event_loop(loop)    # Set it as the current loop for this thread

    signals_to_handle = (signal.SIGINT, signal.SIGTERM)
    handlers_added = True

    print(f"[{time.time():.3f}] +++ Adding signal handlers to loop {id(loop)} +++", file=sys.stderr)
    try:
        for sig in signals_to_handle:
            current_sig = sig
            loop.add_signal_handler(
                current_sig,
                # The lambda now calls the async handler using loop.create_task
                lambda s=current_sig: asyncio.create_task(_handle_signal_async(s))
            )
            log.debug(f"Added signal handler for {signal.Signals(sig).name}")
            print(f"[{time.time():.3f}] +++ Added handler for {signal.Signals(sig).name} +++", file=sys.stderr)
    except NotImplementedError:
         handlers_added = False
         log.warning("Signal handlers for SIGTERM/SIGINT could not be added (possibly on Windows). Ctrl+C might not guarantee graceful shutdown.")
         print(f"[{time.time():.3f}] +++ Failed to add signal handlers (NotImplementedError) +++", file=sys.stderr)
    except Exception as e: # Catch other potential errors like RuntimeError if loop is closed
         handlers_added = False
         log.error("Failed to add signal handlers", error=str(e), exc_info=True)
         print(f"[{time.time():.3f}] +++ Failed to add signal handlers ({type(e).__name__}: {e}) +++", file=sys.stderr)


    main_task = None
    try:
        print(f"[{time.time():.3f}] +++ Calling loop.run_until_complete(run_watch(...)) +++", file=sys.stderr)
        main_task = loop.create_task(run_watch(config_path), name="MainRunWatch")
        loop.run_until_complete(main_task) # Run the main coroutine
        print(f"[{time.time():.3f}] +++ loop.run_until_complete finished normally +++", file=sys.stderr)

    except KeyboardInterrupt:
         # This might still occur if the signal is delivered before the handler is fully effective
         log.warning("KeyboardInterrupt caught directly in watch_cli. Attempting graceful shutdown.")
         print(f"[{time.time():.3f}] +++ KeyboardInterrupt caught in watch_cli +++", file=sys.stderr)
         if not _shutdown_requested.is_set():
              _shutdown_requested.set()
              # Give the event loop a chance to process the shutdown event if needed
              # loop.run_until_complete(asyncio.sleep(0.1))
    except asyncio.CancelledError:
         log.warning("Main run_watch task was cancelled.")
         print(f"[{time.time():.3f}] +++ Main run_watch task cancelled +++", file=sys.stderr)
    finally:
         print(f"[{time.time():.3f}] +++ watch_cli finally block entered +++", file=sys.stderr)

         # Ensure main task is cancelled if it's still around and not done
         if main_task and not main_task.done():
             print(f"[{time.time():.3f}] +++ Explicitly cancelling main task in finally +++", file=sys.stderr)
             main_task.cancel()
             try:
                 # Give cancellation a chance to propagate
                 loop.run_until_complete(main_task)
             except asyncio.CancelledError:
                 print(f"[{time.time():.3f}] +++ Main task cancellation processed +++", file=sys.stderr)
             except Exception as e:
                 print(f"[{time.time():.3f}] +++ Error during final main task wait: {e} +++", file=sys.stderr)


         # Clean up signal handlers
         if handlers_added:
             log.debug("Removing signal handlers...")
             print(f"[{time.time():.3f}] +++ Removing signal handlers from loop {id(loop)} +++", file=sys.stderr)
             for sig in signals_to_handle:
                 removed = loop.remove_signal_handler(sig)
                 log.debug(f"Removed signal handler for {signal.Signals(sig).name} (found: {removed})")
                 print(f"[{time.time():.3f}] +++ Removed handler for {signal.Signals(sig).name} (found: {removed}) +++", file=sys.stderr)

         # Important: Close the loop properly
         print(f"[{time.time():.3f}] +++ Closing event loop {id(loop)} +++", file=sys.stderr)
         # Cancel remaining tasks before closing loop
         try:
              tasks = asyncio.all_tasks(loop=loop)
              if tasks:
                   print(f"[{time.time():.3f}] +++ Cancelling {len(tasks)} remaining tasks before loop close +++", file=sys.stderr)
                   for task in tasks:
                        task.cancel()
                   loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                   print(f"[{time.time():.3f}] +++ Remaining tasks gathered/cancelled +++", file=sys.stderr)
         except Exception as e: # Catch errors during final task cleanup
             print(f"[{time.time():.3f}] +++ Error cancelling remaining tasks: {e} +++", file=sys.stderr)

         try:
              loop.close()
              print(f"[{time.time():.3f}] +++ Event loop {id(loop)} closed +++", file=sys.stderr)
              log.info("Event loop closed.")
         except Exception as e:
             log.error("Error closing event loop", error=str(e), exc_info=True)
             print(f"[{time.time():.3f}] +++ Error closing loop {id(loop)}: {e} +++", file=sys.stderr)


    log.info("'watch' command finished.")
    print(f"[{time.time():.3f}] +++ watch_cli finished +++", file=sys.stderr)

    # --- MODIFIED SECTION END ---


# 🔼⚙️
