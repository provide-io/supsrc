#
# supsrc/runtime/orchestrator.py
#

import asyncio
import sys
import logging # For logging.shutdown
from pathlib import Path
from typing import Any, Set, TypeAlias

import structlog
import attrs # For attrs.asdict if needed later

# Use absolute imports from within supsrc
from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.rules import check_trigger_condition # Assuming this handles the structured rule object
from supsrc.config.models import (
    RepositoryConfig, RuleConfig, InactivityRuleConfig, SaveCountRuleConfig, ManualRuleConfig
)
# Import protocols and plugin loader if/when implementing dynamic engines
# from supsrc.protocols import Rule, ConversionStep, RepositoryEngine, PluginResult
# from supsrc.plugins import load_plugin

# Logger for this module
log: StructLogger = structlog.get_logger("runtime.orchestrator")

# Type alias for state map
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]

# --- Action Callback (Placeholder) ---
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

    # Get the structured rule config object
    rule_config_obj = repo_config.rule
    # Get rule type string (might be useful for logging/logic)
    rule_type_str = getattr(rule_config_obj, 'type', 'unknown_rule_type')

    callback_log.info(
        "Trigger condition met!",
        rule_type=rule_type_str,
        current_save_count=repo_state.save_count
    )
    repo_state.update_status(RepositoryStatus.TRIGGERED)
    repo_state.inactivity_timer_handle = None

    # --- Placeholder for Git Action / Engine Call ---
    callback_log.info(">>> Intent: Perform Repository Action (e.g., Git Commit) <<<", engine_config=repo_config.repository)
    # TODO: Replace with actual engine loading and execution
    # engine_config_dict = repo_config.repository
    # engine_type = engine_config_dict.get("type", "unknown_engine")
    # try:
    #     engine: RepositoryEngine = load_plugin(engine_type, RepositoryEngine)
    #     # ... call engine methods: get_status, stage_changes, perform_commit, perform_push ...
    # except Exception as engine_e:
    #     callback_log.error("Failed to load or execute repository engine", engine_type=engine_type, error=str(engine_e))
    #     repo_state.update_status(RepositoryStatus.ERROR, f"Engine failed: {engine_e}")
    #     return # Stop processing

    # Simulate work and reset
    callback_log.debug("Simulating successful action for state reset")
    repo_state.reset_after_action()
    # --- End Placeholder ---

# --- Event Consumer Logic ---
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

            shutdown_wait_task = asyncio.create_task(shutdown_event.wait(), name="ShutdownWait")
            consumer_log.debug("Consumer waiting for event or shutdown...")

            done, pending = await asyncio.wait(
                {get_task, shutdown_wait_task}, return_when=asyncio.FIRST_COMPLETED
            )
            consumer_log.debug("Consumer woke up.", done_tasks=len(done), pending_tasks=len(pending))

            if shutdown_wait_task in done or shutdown_event.is_set():
                 consumer_log.info("Consumer detected shutdown request.")
                 if get_task in pending:
                     consumer_log.debug("Cancelling pending event get task during shutdown.")
                     get_task.cancel()
                 break # Exit loop cleanly

            if get_task in done:
                try:
                     event = get_task.result()
                except asyncio.CancelledError:
                     consumer_log.debug("Queue get task was cancelled.")
                     continue
                except Exception as e:
                     consumer_log.error("Error retrieving event from queue", error=str(e), exc_info=True)
                     get_task = None
                     await asyncio.sleep(0.5)
                     continue

                get_task = None
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

                # --- Check Rules using the structured rule object ---
                rule_config_obj: RuleConfig = repo_config.rule # <<< Access the structured rule object
                rule_type_str = getattr(rule_config_obj, 'type', 'unknown_rule_type') # For logging

                try:
                    # check_trigger_condition should accept repo_state and repo_config
                    # It can then access repo_config.rule internally.
                    if check_trigger_condition(repo_state, repo_config):
                        event_log.info("Rule condition met, scheduling action", rule_type=rule_type_str)
                        asyncio.create_task(_trigger_action_callback(event.repo_id, repo_states, config))
                    else:
                        # Reschedule inactivity timer if applicable
                        if isinstance(rule_config_obj, InactivityRuleConfig):
                             delay = rule_config_obj.period.total_seconds()
                             event_log.debug("Rescheduling inactivity check", delay_seconds=delay)
                             timer_handle = loop.call_later(
                                 delay,
                                 lambda rid=event.repo_id: asyncio.create_task(
                                     _trigger_action_callback(rid, repo_states, config)
                                 )
                             )
                             repo_state.set_inactivity_timer(timer_handle)

                except Exception as e:
                    event_log.error("Error checking rule", rule_type=rule_type_str, error=str(e), exc_info=True)
                    repo_state.update_status(RepositoryStatus.ERROR, f"Rule check failed: {e}")

                event_queue.task_done()

        except asyncio.CancelledError:
            consumer_log.info("Event consumer task explicitly cancelled.")
            if get_task and not get_task.done():
                 consumer_log.debug("Cancelling internal queue get task during consumer cancellation.")
                 get_task.cancel()
            raise

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
        self._log = log.bind(orchestrator_id=id(self))

    def _safe_log(self, level: str, msg: str, **kwargs):
        """Helper to suppress logging errors during final shutdown."""
        try:
            getattr(self._log, level)(msg, **kwargs)
        except (BrokenPipeError, RuntimeError, ValueError) as e:
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
                 raise # Re-raise for the CLI layer to handle exit
            except Exception as e:
                 self._safe_log("critical", "Unexpected error loading configuration", error=str(e), exc_info=True)
                 raise

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
                 return

            # --- Start Monitoring ---
            self._safe_log("debug", "Starting monitor service...")
            self.monitor_service.start()
            if not self.monitor_service.is_running:
                 self._safe_log("critical", "Monitoring service failed to start. Exiting run.")
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
            self._safe_log("critical", "A critical supsrc error occurred during watch", error=str(e), exc_info=True)
        except asyncio.CancelledError:
             self._safe_log("warning", "Orchestrator run task was cancelled.")
             if not self.shutdown_event.is_set(): self.shutdown_event.set()
        except Exception as e:
            self._safe_log("critical", "An unexpected error occurred in orchestrator run", error=str(e), exc_info=True)
            if not self.shutdown_event.is_set(): self.shutdown_event.set()
        finally:
            # --- Orchestrator Cleanup ---
            self._safe_log("info", "Orchestrator starting cleanup...")

            # 1. Cancel Repository Timers
            self._safe_log("debug", "Cancelling active repository timers...")
            timers_cancelled = 0
            for repo_id, state in self.repo_states.items():
                 if state.inactivity_timer_handle:
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
                         await self.monitor_service.stop()
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
        if not self.config: return []

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
