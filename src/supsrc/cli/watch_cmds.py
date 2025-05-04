#
# src/supsrc/cli/watch_cmds.py
#

"""
CLI command for watching repositories ('supsrc watch').
Integrates monitoring, state management, and rule checking.
"""

import asyncio
import signal
import sys
import time # Keep for potential future use
from pathlib import Path
from typing import Coroutine, Any, Set, TypeAlias

import click
import structlog

# Use absolute imports
from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent
from supsrc.state import RepositoryState, RepositoryStatus # NEW Import
from supsrc.rules import check_trigger_condition # NEW Import
from supsrc.config.models import RepositoryConfig, InactivityTrigger, SaveCountTrigger, ManualTrigger # NEW Import

log: StructLogger = structlog.get_logger("cli.watch")

# --- Globals for Signal Handling ---
_shutdown_requested = asyncio.Event()
_running_tasks: Set[asyncio.Task[Any]] = set()

# Type alias for state map
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]

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

# --- Action Callback (Triggered by Rules) ---
async def _trigger_action_callback(repo_id: str, repo_states: RepositoryStatesMap, config: SupsrcConfig) -> None:
    """
    Callback executed when a trigger condition is met (by timer or save count).

    For now, this just logs the intention to act. Later, it will schedule Git tasks.
    """
    repo_state = repo_states.get(repo_id)
    repo_config = config.repositories.get(repo_id)

    if not repo_state or not repo_config:
        log.error("Could not find state or config for triggered action", repo_id=repo_id)
        return

    # Prevent triggering actions if already processing or in error state?
    # Allow triggering from CHANGED (normal case) or IDLE (rare edge case, maybe?)
    # Disallow if already TRIGGERED, COMMITTING, PUSHING, or ERROR.
    if repo_state.status not in (RepositoryStatus.CHANGED, RepositoryStatus.IDLE):
         log.warning("Trigger fired but repository is not in CHANGED/IDLE state",
                     repo_id=repo_id, current_status=repo_state.status.name)
         # Decide if the timer should be cleared or action retried later
         repo_state.inactivity_timer_handle = None # Clear timer handle if it was the source
         return

    trigger_type_name = type(repo_config.trigger).__name__
    log.info(
        "Trigger condition met!",
        repo_id=repo_id,
        trigger_type=trigger_type_name,
        current_save_count=repo_state.save_count # Log count even if inactivity
    )
    repo_state.update_status(RepositoryStatus.TRIGGERED)
    repo_state.inactivity_timer_handle = None # Action is triggering, clear timer handle if it exists

    # --- Placeholder for Git Action ---
    log.info(">>> Intent: Perform Git Add/Commit Action <<<", repo_id=repo_id)
    # In the future, schedule perform_git_commit_task here.
    # For now, simulate success to reset state for further testing.
    # await asyncio.sleep(0.1) # Simulate tiny delay
    log.debug("Simulating successful action for state reset", repo_id=repo_id)
    # This reset assumes the (future) commit/push was successful.
    # Error handling in GitOps tasks will need to manage state differently on failure.
    repo_state.reset_after_action() # Resets save count, status to IDLE
    # --- End Placeholder ---


# --- Core Async Functions ---
async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    monitor_service: MonitoringService, # Keep monitor_service if needed later?
    repo_states: RepositoryStatesMap,   # <<< NEW param
    config: SupsrcConfig                # <<< NEW param
) -> None:
    """
    Consumes events from the queue, updates state, manages timers, and checks rules.
    """
    log.info("Event consumer started, waiting for file events...")
    loop = asyncio.get_running_loop()
    get_task: asyncio.Task | None = None # Define get_task in outer scope

    while True:
        try:
            # Ensure we only create get_task once per loop iteration if needed
            if get_task is None or get_task.done():
                 get_task = asyncio.create_task(event_queue.get(), name=f"QueueGet-{id(event_queue)}")

            shutdown_task = asyncio.create_task(_shutdown_requested.wait(), name="ShutdownWait")
            log.debug("Consumer waiting for event or shutdown...")

            done, pending = await asyncio.wait(
                {get_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
            )
            log.debug("Consumer woke up.", done_tasks=len(done), pending_tasks=len(pending))

            if shutdown_task in done or _shutdown_requested.is_set():
                 log.info("Consumer detected shutdown request.")
                 # Explicitly cancel get_task *before* breaking the loop
                 if get_task in pending:
                     log.debug("Cancelling pending event get task during shutdown.")
                     get_task.cancel()
                     # Give cancellation a chance to propagate within this loop iteration
                     # await asyncio.sleep(0) # May or may not be needed
                 log.info("Exiting event consumer loop."); break

            if get_task in done:
                try:
                     event = get_task.result()
                except asyncio.CancelledError:
                     log.debug("Queue get task was cancelled while retrieving result.")
                     # This can happen if shutdown occurred between wait() completing and result() being called
                     continue # Go back to the top to check shutdown_requested
                except Exception as e:
                     log.error("Error retrieving event from queue", error=str(e), exc_info=True)
                     get_task = None # Reset task to retry
                     await asyncio.sleep(0.5) # Prevent tight loop on queue errors
                     continue


                # Reset get_task so a new one is created next iteration
                get_task = None

                # Use bind for consistent context in subsequent logs for this event
                event_log = log.bind(repo_id=event.repo_id, event_type=event.event_type, src_path=str(event.src_path))
                event_log.debug("Consumer received event details") # No event=event needed


                # --- Find and Update State ---
                repo_id = event.repo_id
                repo_state = repo_states.get(repo_id)
                repo_config = config.repositories.get(repo_id)

                if not repo_state or not repo_config:
                    event_log.warning("Received event for unknown/disabled repository, ignoring.")
                    event_queue.task_done(); continue # Skip if no state/config found

                # Record the change (updates time, increments count, sets status to CHANGED)
                repo_state.record_change()
                # Further bind context for logs within this specific event's processing
                event_log = event_log.bind(save_count=repo_state.save_count, status=repo_state.status.name)

                # --- Check Trigger Conditions ---
                trigger_config = repo_config.trigger

                match trigger_config:
                    case InactivityTrigger(period=period):
                        # Cancel existing timer (done in record_change) and schedule new one
                        delay_seconds = period.total_seconds()
                        event_log.debug("Scheduling inactivity check", delay_seconds=delay_seconds)
                        # Pass necessary context to the callback
                        # Wrap callback in create_task to ensure it runs within the loop's context
                        # Use lambda to capture current values for the callback call
                        timer_handle = loop.call_later(
                            delay_seconds,
                            lambda rid=repo_id: asyncio.create_task(
                                 _trigger_action_callback(rid, repo_states, config)
                            )
                        )
                        repo_state.set_inactivity_timer(timer_handle)

                    case SaveCountTrigger():
                         event_log.debug("Checking save count trigger")
                         # check_trigger_condition handles logging the check details
                         if check_trigger_condition(repo_state, repo_config):
                             # Trigger condition met immediately
                             event_log.info("Save count met, scheduling action") # Use info level for met trigger
                             # Cancel any inactivity timer that might be running concurrently?
                             # Generally not needed, as save count takes precedence here.
                             # repo_state.cancel_inactivity_timer()
                             # Schedule the action callback to run soon
                             asyncio.create_task(_trigger_action_callback(repo_id, repo_states, config))
                             # Note: Save count doesn't reset here, but in reset_after_action

                    case ManualTrigger():
                         event_log.debug("Manual trigger: Change recorded, no automatic action.")
                         # State is already CHANGED by record_change()

                event_queue.task_done()
                # --- End New Logic ---
            else:
                 # This path should ideally not be reached due to asyncio.wait behavior
                 log.warning("Consumer loop woke up unexpectedly without completing get or shutdown.")
                 if get_task in pending: get_task.cancel()
                 if shutdown_task in pending: shutdown_task.cancel()


        except asyncio.CancelledError:
            log.info("Event consumer task explicitly cancelled.")
            # --- Explicitly cancel the pending queue get task ---
            # Check if get_task exists and is still pending
            if get_task and not get_task.done():
                 log.debug("Cancelling internal queue get task during consumer cancellation.")
                 get_task.cancel()
                 # Don't await here, let the outer gather handle final cleanup
            # --- End cancellation ---
            raise # Re-raise CancelledError so run_watch's finally block can gather it

        except Exception as e:
            # Log the error with bound context if available, otherwise use base log
            logger_to_use = log
            if 'event_log' in locals():
                 logger_to_use = event_log # Use logger with context if error happened post-bind
            logger_to_use.error("Error in event consumer loop", error=str(e), exc_info=True)
            # Reset get_task if it might be related to the error
            get_task = None
            await asyncio.sleep(1) # Avoid tight loop on unexpected error


async def run_watch(config_path: Path) -> None:
    """Loads config, sets up state, starts monitoring, and manages the event loop."""
    global _running_tasks
    log.info("Starting 'watch' command execution", config_path=str(config_path))
    monitor_service: MonitoringService | None = None
    event_queue: asyncio.Queue[MonitoredEvent] | None = None
    repo_states: RepositoryStatesMap = {} # Initialize state map

    try:
        log.debug("run_watch: Loading config...")
        try:
            config: SupsrcConfig = load_config(config_path)
            log.info("Configuration loaded successfully for watch command.")
        except ConfigurationError as e:
             log.error("Failed to load configuration", error=str(e), path=str(config_path)); sys.exit(1)

        # --- Initialize Repository States ---
        log.debug("run_watch: Initializing states for enabled repositories...")
        enabled_repo_ids: list[str] = []
        for repo_id, repo_config in config.repositories.items():
            if repo_config.enabled and repo_config._path_valid:
                repo_states[repo_id] = RepositoryState(repo_id=repo_id)
                enabled_repo_ids.append(repo_id)
                log.debug("Initialized state object", repo_id=repo_id)
            else:
                log.info("Skipping state initialization for disabled/invalid repo", repo_id=repo_id)
        log.info("Enabled repositories found", count=len(enabled_repo_ids), repos=enabled_repo_ids)
        if not enabled_repo_ids:
             log.warning("No enabled and valid repositories found in configuration. Exiting.")
             return # Exit cleanly if nothing to watch
        # --- End State Initialization ---

        log.debug("run_watch: Setting up monitoring service...")
        event_queue = asyncio.Queue()
        monitor_service = MonitoringService(event_queue)

        log.debug("run_watch: Adding repositories to monitor...")
        setup_errors = 0
        successfully_added_ids: list[str] = []
        for repo_id in enabled_repo_ids: # Only iterate over those we have state for
             repo_config = config.repositories[repo_id]
             try:
                 monitor_service.add_repository(repo_id, repo_config)
                 successfully_added_ids.append(repo_id)
             except MonitoringSetupError as e:
                 log.error("Failed to setup monitoring for repository", repo_id=repo_id, error=str(e))
                 # Update state to ERROR if setup failed
                 if repo_id in repo_states:
                     repo_states[repo_id].update_status(RepositoryStatus.ERROR, error_msg=f"Monitoring setup failed: {e}")
                 setup_errors += 1
             except Exception as e:
                 log.error("Unexpected error adding repository", repo_id=repo_id, error=str(e), exc_info=True)
                 if repo_id in repo_states:
                     repo_states[repo_id].update_status(RepositoryStatus.ERROR, error_msg=f"Unexpected setup error: {e}")
                 setup_errors += 1

        if setup_errors > 0:
             log.warning(f"Encountered {setup_errors} error(s) during monitoring setup.")
             if not successfully_added_ids:
                 log.critical("No repositories could be successfully setup for monitoring. Exiting.")
                 sys.exit(1)

        log.debug("run_watch: Starting monitor service...")
        monitor_service.start()

        if not monitor_service.is_running and successfully_added_ids:
            log.critical("Monitoring service failed to start despite having repositories. Exiting.")
            sys.exit(1)
        elif not monitor_service.is_running:
             log.info("Monitoring service not started (no repositories successfully added?). Exiting.")
             return

        log.debug("run_watch: Creating consumer task...")
        consumer_task = asyncio.create_task(
            consume_events(event_queue, monitor_service, repo_states, config),
            name="EventConsumer"
        )
        _running_tasks.add(consumer_task)
        consumer_task.add_done_callback(_running_tasks.discard)

        log.info(f"Monitoring active for {len(successfully_added_ids)} repositories. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        await _shutdown_requested.wait()
        log.info("Shutdown initiated by signal...")

    except SupsrcError as e:
        log.critical("A critical supsrc error occurred during watch", error=str(e), exc_info=True)
    except asyncio.CancelledError:
         log.warning("run_watch task was cancelled.")
         # Ensure shutdown event is set if cancelled externally
         if not _shutdown_requested.is_set(): _shutdown_requested.set()
    except Exception as e:
        log.critical("An unexpected error occurred during watch", error=str(e), exc_info=True)
    finally:
        log.info("Starting cleanup...")

        # --- Cancel any active repository timers FIRST ---
        log.debug("Cancelling any active repository timers...")
        timers_cancelled = 0
        for repo_id, state in repo_states.items():
             if state.inactivity_timer_handle:
                 state.cancel_inactivity_timer()
                 timers_cancelled += 1
        log.debug(f"Cancelled {timers_cancelled} repository timer(s).")
        # --- End timer cancellation ---

        # Cancel running asyncio tasks (like the consumer)
        if _running_tasks:
            log.debug(f"Cancelling {len(_running_tasks)} running task(s)...", tasks=[t.get_name() for t in _running_tasks])
            tasks_to_cancel = list(_running_tasks) # Create copy before iterating/modifying
            for task in tasks_to_cancel:
                if not task.done():
                    log.debug(f"Cancelling task: {task.get_name()}")
                    task.cancel()
            log.debug("Waiting for cancelled tasks to finish...")
            # Give cancelled tasks a chance to run their cancellation handlers (including consume_events cancelling get_task)
            try:
                 gathered_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                 log.debug("Running tasks cancellation gathered.", results=[type(r).__name__ for r in gathered_results])
            except Exception as gather_exc:
                 # This might happen if gather itself is interrupted, though less likely here
                 log.error("Exception during task gathering", error=str(gather_exc), exc_info=True)
        else:
            log.debug("No running asyncio tasks found to cancel.")

        # Stop the monitoring service (joins the observer thread)
        if monitor_service is not None:
            if monitor_service.is_running:
                 log.debug("Stopping monitoring service (includes joining observer thread)...")
                 try:
                     await monitor_service.stop() # This internally uses asyncio.to_thread
                     log.debug("Monitoring service stop completed.")
                 except Exception as stop_exc:
                     log.error("Error during monitoring service stop", error=str(stop_exc), exc_info=True)
            else:
                 log.debug("Monitoring service was not running or already stopped.")
        else:
            log.debug("Monitoring service was not initialized.")

        log.info("supsrc watch finished cleanup.")


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
    Monitor configured repositories for changes and trigger actions (commit/push).
    """
    log.info("Initializing 'watch' command")

    # Create and set a new event loop for this command's execution
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    signals_to_handle = (signal.SIGINT, signal.SIGTERM)
    handlers_added = False # Track if handlers were successfully added

    log.debug(f"Adding signal handlers to loop {id(loop)}")
    try:
        for sig in signals_to_handle:
            # Use loop.create_task to ensure the handler runs within the loop
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_handle_signal_async(s))
            )
            log.debug(f"Added signal handler for {signal.Signals(sig).name}")
        handlers_added = True
    except NotImplementedError:
         # Common on Windows for SIGTERM/SIGINT in loops
         log.warning("Signal handlers for SIGTERM/SIGINT could not be added (not supported on this platform/loop implementation). Ctrl+C might not guarantee graceful shutdown.")
    except Exception as e:
         # Catch other potential errors during handler setup
         log.error("Failed to add signal handlers", error=str(e), exc_info=True)

    main_task = None
    try:
        log.debug(f"Creating main task: run_watch(config_path='{config_path}')")
        main_task = loop.create_task(run_watch(config_path), name="MainRunWatch")
        log.debug(f"Running event loop {id(loop)} until main task completes...")
        loop.run_until_complete(main_task)
        log.debug("loop.run_until_complete finished normally")

    except KeyboardInterrupt:
         # This might still catch Ctrl+C if signal handlers fail or are slow
         log.warning("KeyboardInterrupt caught directly in watch_cli. Attempting graceful shutdown via event.")
         if not _shutdown_requested.is_set():
              # Try to trigger the async signal handler logic if possible
              # Use call_soon_threadsafe if KBInterrupt comes from different thread context
              loop.call_soon_threadsafe(_shutdown_requested.set)
              # Give loop a moment to potentially process the event if needed
              # This can be tricky and might still race with loop closing.
              # try:
              #     loop.run_until_complete(asyncio.sleep(0.1))
              # except RuntimeError: # Loop might already be closing/closed
              #     pass

    except asyncio.CancelledError:
         log.warning("Main run_watch task was cancelled unexpectedly.")
         # Ensure shutdown is signalled if the main task is cancelled externally
         if not _shutdown_requested.is_set():
             _shutdown_requested.set() # Signal other tasks to stop
    finally:
         log.debug(f"watch_cli finally block entered. Loop {id(loop)} running: {loop.is_running()}, closed: {loop.is_closed()}")

         # --- Final Async Cleanup within the Loop ---
         # Run task cleanup BEFORE closing the loop.
         if loop.is_running():
             log.debug("Running final cleanup tasks within the loop...")
             try:
                # Gather all tasks associated *with this loop*
                # Use current_task(loop=loop) if needed, though usually not necessary here
                tasks = asyncio.all_tasks(loop=loop)
                # Filter out the current task if cleanup runs as a task (unlikely here)
                tasks_to_cancel = {t for t in tasks if t is not asyncio.current_task(loop=loop) and not t.done()}

                if tasks_to_cancel:
                    log.debug(f"Cancelling {len(tasks_to_cancel)} remaining tasks before loop close: {[t.get_name() for t in tasks_to_cancel]}")
                    for task in tasks_to_cancel:
                        task.cancel()

                    log.debug("Gathering remaining tasks after cancellation...")
                    # This gather allows cancelled tasks (like consume_events)
                    # to run their cancellation handling (including cancelling the internal get_task).
                    # Crucially, this happens *before* the loop is closed.
                    loop.run_until_complete(asyncio.gather(*tasks_to_cancel, return_exceptions=True))
                    log.debug("Remaining tasks gathered/cancelled")
                else:
                    log.debug("No remaining tasks found to cancel before loop close.")
             except Exception as cleanup_exc:
                  log.error(f"Error during final task cancellation/gathering: {cleanup_exc}", exc_info=True)

         # --- Remove Signal Handlers ---
         # Check loop is not closed before attempting removal
         if handlers_added and not loop.is_closed():
             log.debug(f"Removing signal handlers from loop {id(loop)}")
             for sig in signals_to_handle:
                 try:
                     removed = loop.remove_signal_handler(sig)
                     log.debug(f"Attempted removal of signal handler for {signal.Signals(sig).name} (found/removed: {removed})")
                 except (ValueError, RuntimeError) as e: # Also catch RuntimeError if loop is closing
                     log.debug(f"Signal handler for {signal.Signals(sig).name} not found or loop closing during removal.", error=str(e))
                 except Exception as e:
                     log.error(f"Error removing signal handler for {signal.Signals(sig).name}", error=str(e), exc_info=True)

         # --- Close the Event Loop ---
         log.debug(f"Closing event loop {id(loop)}")
         try:
             if not loop.is_closed():
                 # Run pending callbacks scheduled with call_soon/call_later before closing
                 loop.run_until_complete(loop.shutdown_asyncgens())
                 log.debug("Async generators shut down.")
                 loop.close()
                 log.info("Event loop closed.")
             else:
                 log.warning("Event loop was already closed before final cleanup.")
         except Exception as loop_close_exc:
             # Catch potential RuntimeErrors if loop state is unexpected
             log.error("Error during event loop closing", error=str(loop_close_exc), exc_info=True)

    log.info("'watch' command finished.")


# 🔼⚙️
