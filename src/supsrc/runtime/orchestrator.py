#
# supsrc/runtime/orchestrator.py
#$

import asyncio
import sys
import logging # For logging.shutdown
from pathlib import Path
from typing import Any, Set, TypeAlias

import structlog

# Use absolute imports from within supsrc
from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.rules import check_trigger_condition
from supsrc.config.models import RepositoryConfig, InactivityTrigger, SaveCountTrigger, ManualTrigger

# Logger for this module
log: StructLogger = structlog.get_logger("runtime.orchestrator")

# Type alias for state map
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]

# --- Action Callback (Placeholder) ---
# Keep this separate or move to another module later (e.g., runtime.actions)
async def _trigger_action_callback(repo_id: str, repo_states: RepositoryStatesMap, config: SupsrcConfig) -> None:
    """
    Callback executed when a trigger condition is met. Placeholder for Git ops.
    """
    repo_state = repo_states.get(repo_id)
    repo_config = config.repositories.get(repo_id)
    callback_log = log.bind(repo_id=repo_id) # Bind context

    if not repo_state or not repo_config:
        callback_log.error("Could not find state or config for triggered action")
        return

    if repo_state.status not in (RepositoryStatus.CHANGED, RepositoryStatus.IDLE):
         callback_log.warning("Trigger fired but repository is not in CHANGED/IDLE state",
                     current_status=repo_state.status.name)
         repo_state.inactivity_timer_handle = None
         return

    trigger_type_name = type(repo_config.trigger).__name__
    callback_log.info(
        "Trigger condition met!",
        trigger_type=trigger_type_name,
        current_save_count=repo_state.save_count
    )
    repo_state.update_status(RepositoryStatus.TRIGGERED)
    repo_state.inactivity_timer_handle = None

    # --- Placeholder for Git Action ---
    callback_log.info(">>> Intent: Perform Git Add/Commit Action <<<")
    # Simulate work and reset
    # await asyncio.sleep(0.1) # Simulate tiny delay if needed
    callback_log.debug("Simulating successful action for state reset")
    repo_state.reset_after_action()
    # --- End Placeholder ---

# --- Event Consumer Logic ---
# Keep this separate or move to another module later (e.g., runtime.events)
async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    repo_states: RepositoryStatesMap,
    config: SupsrcConfig,
    shutdown_event: asyncio.Event
) -> None:
    """
    Consumes events from the queue, updates state, manages timers, and checks rules.
    """
    consumer_log = log.bind(component="EventConsumer") # Bind context
    consumer_log.info("Event consumer started, waiting for file events...")
    loop = asyncio.get_running_loop()
    get_task: asyncio.Task | None = None

    while not shutdown_event.is_set(): # Check event directly
        try:
            if get_task is None or get_task.done():
                 get_task = asyncio.create_task(event_queue.get(), name=f"QueueGet-{id(event_queue)}")

            # Wait for either an event or the shutdown signal
            shutdown_wait_task = asyncio.create_task(shutdown_event.wait(), name="ShutdownWait")
            consumer_log.debug("Consumer waiting for event or shutdown...")

            done, pending = await asyncio.wait(
                {get_task, shutdown_wait_task}, return_when=asyncio.FIRST_COMPLETED
            )
            consumer_log.debug("Consumer woke up.", done_tasks=len(done), pending_tasks=len(pending))

            # Prioritize shutdown check
            if shutdown_wait_task in done or shutdown_event.is_set():
                 consumer_log.info("Consumer detected shutdown request.")
                 if get_task in pending:
                     consumer_log.debug("Cancelling pending event get task during shutdown.")
                     get_task.cancel()
                 break # Exit loop cleanly

            # Process event if received
            if get_task in done:
                try:
                     event = get_task.result()
                except asyncio.CancelledError:
                     consumer_log.debug("Queue get task was cancelled.")
                     continue # Go back to check shutdown signal
                except Exception as e:
                     consumer_log.error("Error retrieving event from queue", error=str(e), exc_info=True)
                     get_task = None
                     await asyncio.sleep(0.5)
                     continue

                get_task = None # Reset for next iteration
                event_log = consumer_log.bind(repo_id=event.repo_id, event_type=event.event_type, src_path=str(event.src_path))
                event_log.debug("Consumer received event details")

                repo_id = event.repo_id
                repo_state = repo_states.get(repo_id)
                repo_config = config.repositories.get(repo_id)

                if not repo_state or not repo_config:
                    event_log.warning("Received event for unknown/disabled repository, ignoring.")
                    event_queue.task_done(); continue

                repo_state.record_change()
                event_log = event_log.bind(save_count=repo_state.save_count, status=repo_state.status.name)

                trigger_config = repo_config.trigger
                match trigger_config:
                    case InactivityTrigger(period=period):
                        delay_seconds = period.total_seconds()
                        event_log.debug("Scheduling inactivity check", delay_seconds=delay_seconds)
                        timer_handle = loop.call_later(
                            delay_seconds,
                            lambda rid=repo_id: asyncio.create_task(
                                 _trigger_action_callback(rid, repo_states, config)
                            )
                        )
                        repo_state.set_inactivity_timer(timer_handle)
                    case SaveCountTrigger():
                         event_log.debug("Checking save count trigger")
                         if check_trigger_condition(repo_state, repo_config):
                             event_log.info("Save count met, scheduling action")
                             asyncio.create_task(_trigger_action_callback(repo_id, repo_states, config))
                    case ManualTrigger():
                         event_log.debug("Manual trigger: Change recorded, no automatic action.")

                event_queue.task_done()

        except asyncio.CancelledError:
            consumer_log.info("Event consumer task explicitly cancelled.")
            if get_task and not get_task.done():
                 consumer_log.debug("Cancelling internal queue get task during consumer cancellation.")
                 get_task.cancel()
            raise # Re-raise for the orchestrator to handle

        except Exception as e:
            logger_to_use = consumer_log
            if 'event_log' in locals(): logger_to_use = event_log
            logger_to_use.error("Error in event consumer loop", error=str(e), exc_info=True)
            get_task = None
            await asyncio.sleep(1)

    consumer_log.info("Event consumer finished.")


# --- Orchestrator Class ---

class WatchOrchestrator:
    """Manages the core watch lifecycle."""

    def __init__(self, config_path: Path, shutdown_event: asyncio.Event):
        self.config_path = config_path
        self.shutdown_event = shutdown_event
        self.config: SupsrcConfig | None = None
        self.monitor_service: MonitoringService | None = None
        self.event_queue: asyncio.Queue[MonitoredEvent] | None = None
        self.repo_states: RepositoryStatesMap = {}
        self._running_tasks: Set[asyncio.Task[Any]] = set()
        self._log = log.bind(orchestrator_id=id(self)) # Add context

    def _safe_log(self, level: str, msg: str, **kwargs):
        """Helper to suppress logging errors during final shutdown."""
        try:
            getattr(self._log, level)(msg, **kwargs)
        except (BrokenPipeError, RuntimeError, ValueError) as e:
            # print(f"Debug (Orchestrator): Suppressed log error: {e}", file=sys.stderr)
            pass

    async def run(self) -> None:
        """Main execution method for the watch process."""
        self._safe_log("info", "Starting orchestrator run", config_path=str(self.config_path))

        try:
            # --- Load Configuration ---
            self._safe_log("debug", "Loading configuration...")
            try:
                self.config = load_config(self.config_path)
                self._safe_log("info", "Configuration loaded successfully.")
            except ConfigurationError as e:
                 self._safe_log("error", "Failed to load configuration", error=str(e), path=str(self.config_path))
                 # Consider raising or returning an error code instead of sys.exit
                 raise # Re-raise for the CLI layer to handle exit
            except Exception as e:
                 self._safe_log("critical", "Unexpected error loading configuration", error=str(e), exc_info=True)
                 raise # Re-raise

            # --- Initialize State ---
            self._safe_log("debug", "Initializing repository states...")
            enabled_repo_ids = self._initialize_states()
            if not enabled_repo_ids:
                 self._safe_log("warning", "No enabled and valid repositories found. Exiting run.")
                 return

            # --- Setup Monitoring ---
            self._safe_log("debug", "Setting up monitoring service...")
            self.event_queue = asyncio.Queue()
            self.monitor_service = MonitoringService(self.event_queue)
            successfully_added_ids = self._setup_monitoring(enabled_repo_ids)
            if not successfully_added_ids:
                 self._safe_log("critical", "No repositories could be successfully monitored. Exiting run.")
                 # Maybe raise a specific setup error
                 return

            # --- Start Monitoring ---
            self._safe_log("debug", "Starting monitor service...")
            self.monitor_service.start()
            if not self.monitor_service.is_running:
                 self._safe_log("critical", "Monitoring service failed to start. Exiting run.")
                 # Maybe raise
                 return

            # --- Start Consumer ---
            self._safe_log("debug", "Creating event consumer task...")
            consumer_task = asyncio.create_task(
                consume_events(self.event_queue, self.repo_states, self.config, self.shutdown_event),
                name="EventConsumer"
            )
            self._running_tasks.add(consumer_task)
            consumer_task.add_done_callback(self._running_tasks.discard)

            self._safe_log("info", f"Monitoring active for {len(successfully_added_ids)} repositories. Waiting for shutdown signal.")

            # --- Wait for Shutdown ---
            await self.shutdown_event.wait()
            self._safe_log("info", "Shutdown signal received by orchestrator.")

        except SupsrcError as e:
            # Log specific supsrc errors
            self._safe_log("critical", "A critical supsrc error occurred during watch", error=str(e), exc_info=True)
            # Potentially re-raise or handle specific types differently
        except asyncio.CancelledError:
             # This happens if the orchestrator task itself is cancelled
             self._safe_log("warning", "Orchestrator run task was cancelled.")
             if not self.shutdown_event.is_set(): self.shutdown_event.set() # Ensure cleanup runs
        except Exception as e:
            # Catch-all for unexpected errors during setup or runtime
            self._safe_log("critical", "An unexpected error occurred in orchestrator run", error=str(e), exc_info=True)
            if not self.shutdown_event.is_set(): self.shutdown_event.set() # Trigger cleanup
        finally:
            # --- Orchestrator Cleanup ---
            self._safe_log("info", "Orchestrator starting cleanup...")

            # 1. Cancel Repository Timers
            self._safe_log("debug", "Cancelling active repository timers...")
            timers_cancelled = 0
            for repo_id, state in self.repo_states.items():
                 if state.inactivity_timer_handle:
                     # Use state's logger if possible, fallback to orchestrator log
                     try:
                         state.cancel_inactivity_timer()
                         timers_cancelled += 1
                     except Exception as timer_cancel_e:
                          self._safe_log("warning", "Error cancelling timer", repo_id=repo_id, error=str(timer_cancel_e))
            self._safe_log("debug", f"Cancelled {timers_cancelled} repository timer(s).")

            # 2. Cancel Running Async Tasks (Consumer)
            if self._running_tasks:
                self._safe_log("debug", f"Cancelling {len(self._running_tasks)} running task(s)...", tasks=[t.get_name() for t in self._running_tasks])
                tasks_to_cancel = list(self._running_tasks)
                for task in tasks_to_cancel:
                    if not task.done():
                        self._safe_log("debug", f"Cancelling task: {task.get_name()}")
                        task.cancel()
                self._safe_log("debug", "Waiting for cancelled tasks to finish...")
                try:
                     gathered_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                     # Use safe log here as tasks might log during cancellation
                     self._safe_log("debug", "Running tasks cancellation gathered.", results=[type(r).__name__ for r in gathered_results])
                except Exception as gather_exc:
                     self._safe_log("error", "Exception during task gathering", error=str(gather_exc), exc_info=True)
            else:
                self._safe_log("debug", "No running asyncio tasks found to cancel.")

            # 3. Stop Monitoring Service (joins thread)
            if self.monitor_service is not None:
                if self.monitor_service.is_running:
                     self._safe_log("debug", "Stopping monitoring service (includes joining observer thread)...")
                     try:
                         await self.monitor_service.stop() # This logs internally, hopefully safely
                         self._safe_log("debug", "Monitoring service stop completed.")
                     except Exception as stop_exc:
                         self._safe_log("error", "Error during monitoring service stop", error=str(stop_exc), exc_info=True)
                else:
                     self._safe_log("debug", "Monitoring service was not running or already stopped.")
            else:
                self._safe_log("debug", "Monitoring service was not initialized.")

            self._safe_log("info", "Orchestrator finished cleanup.")

    def _initialize_states(self) -> list[str]:
        """Initializes RepositoryState objects based on config."""
        enabled_repo_ids = []
        if not self.config: return [] # Should not happen if called after load

        for repo_id, repo_config in self.config.repositories.items():
            if repo_config.enabled and repo_config._path_valid:
                self.repo_states[repo_id] = RepositoryState(repo_id=repo_id)
                enabled_repo_ids.append(repo_id)
                self._safe_log("debug", "Initialized state object", repo_id=repo_id)
            else:
                self._safe_log("info", "Skipping state initialization for disabled/invalid repo", repo_id=repo_id)
        self._safe_log("info", "Enabled repositories found", count=len(enabled_repo_ids), repos=enabled_repo_ids)
        return enabled_repo_ids

    def _setup_monitoring(self, enabled_repo_ids: list[str]) -> list[str]:
        """Adds repositories to the MonitoringService."""
        setup_errors = 0
        successfully_added_ids = []
        if not self.monitor_service or not self.config: return []

        for repo_id in enabled_repo_ids:
             repo_config = self.config.repositories[repo_id]
             try:
                 self.monitor_service.add_repository(repo_id, repo_config)
                 successfully_added_ids.append(repo_id)
             except MonitoringSetupError as e:
                 self._safe_log("error", "Failed to setup monitoring for repository", repo_id=repo_id, error=str(e))
                 if repo_id in self.repo_states:
                     self.repo_states[repo_id].update_status(RepositoryStatus.ERROR, error_msg=f"Monitoring setup failed: {e}")
                 setup_errors += 1
             except Exception as e:
                 self._safe_log("error", "Unexpected error adding repository", repo_id=repo_id, error=str(e), exc_info=True)
                 if repo_id in self.repo_states:
                     self.repo_states[repo_id].update_status(RepositoryStatus.ERROR, error_msg=f"Unexpected setup error: {e}")
                 setup_errors += 1

        if setup_errors > 0:
             self._safe_log("warning", f"Encountered {setup_errors} error(s) during monitoring setup.")

        return successfully_added_ids

# 🔼⚙️
