#
# runtime/orchestrator.py
#
"""
Manages the core watch lifecycle, orchestrating monitoring, state, rules, and engines.
"""

import asyncio
import sys
import logging # For logging.shutdown
from pathlib import Path
from typing import Any, Set, TypeAlias, cast # Added cast

import structlog
import attrs # For attrs.asdict if needed later

# Use absolute imports from within supsrc
from supsrc.telemetry import StructLogger
from supsrc.config import load_config, SupsrcConfig
from supsrc.exceptions import ConfigurationError, MonitoringSetupError, SupsrcError
from supsrc.monitor import MonitoringService, MonitoredEvent
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.rules import check_trigger_condition
from supsrc.config.models import (
    RepositoryConfig, RuleConfig, InactivityRuleConfig, SaveCountRuleConfig, ManualRuleConfig
)
# Import protocols and plugin loader if/when implementing dynamic engines
# from supsrc.protocols import Rule, ConversionStep, RepositoryEngine, PluginResult
# from supsrc.plugins import load_plugin
# --- Import specific engine and result types for now ---
from supsrc.engines.git import GitEngine
from supsrc.engines.git.info import GitRepoSummary
from supsrc.protocols import RepositoryEngine # Import base protocol

# Logger for this module
log: StructLogger = structlog.get_logger("runtime.orchestrator")

# Type alias for state map
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]

# --- Action Callback ---
async def _trigger_action_callback(
    repo_id: str,
    repo_states: RepositoryStatesMap,
    config: SupsrcConfig,
    # Pass the engine instance to avoid reloading it every time
    repo_engine: RepositoryEngine
    ) -> None:
    """
    Callback executed when a trigger condition is met. Executes repository actions.
    """
    repo_state = repo_states.get(repo_id)
    repo_config = config.repositories.get(repo_id)
    global_config = config.global_config
    callback_log = log.bind(repo_id=repo_id) # Bind context

    if not repo_state or not repo_config:
        callback_log.error("Could not find state or config for triggered action")
        return

    if repo_state.status not in (RepositoryStatus.CHANGED, RepositoryStatus.IDLE):
         callback_log.warning("Trigger fired but repository is not in CHANGED/IDLE state",
                     current_status=repo_state.status.name)
         repo_state.inactivity_timer_handle = None # Ensure timer is cleared
         return

    # Get the structured rule config object and type string
    rule_config_obj = repo_config.rule
    rule_type_str = getattr(rule_config_obj, 'type', 'unknown_rule_type')

    callback_log.info(
        "Trigger condition met, performing action...",
        rule_type=rule_type_str,
        current_save_count=repo_state.save_count
    )
    repo_state.update_status(RepositoryStatus.PROCESSING) # General processing state
    repo_state.inactivity_timer_handle = None # Action is triggering

    # Get engine config dictionary
    engine_config_dict = repo_config.repository
    working_dir = repo_config.path

    try:
        # --- 1. Get Status (Check for changes) ---
        callback_log.debug("Checking repository status before action...")
        status_result = await repo_engine.get_status(repo_state, engine_config_dict, global_config, working_dir)
        if not status_result.success:
             raise SupsrcError(f"Failed to get repository status: {status_result.message}")

        if status_result.is_clean:
             callback_log.info("Repository is clean, no commit action needed.")
             repo_state.reset_after_action() # Reset to IDLE
             return

        # --- 2. Stage Changes ---
        repo_state.update_status(RepositoryStatus.STAGING) # More specific state
        callback_log.debug("Staging changes...")
        # Stage all detected changes for now (files=None)
        # TODO: Potentially pass specific changed files if needed/available
        stage_result = await repo_engine.stage_changes(None, repo_state, engine_config_dict, global_config, working_dir)
        if not stage_result.success:
            raise SupsrcError(f"Failed to stage changes: {stage_result.message}")
        callback_log.debug("Staging successful.")

        # --- 3. Perform Commit ---
        repo_state.update_status(RepositoryStatus.COMMITTING)
        callback_log.debug("Performing commit...")
        # Pass the template string (message_template is just a placeholder name here)
        commit_result = await repo_engine.perform_commit(
            message_template="Placeholder", # The engine gets the template from its config dict
            state=repo_state,
            config=engine_config_dict,
            global_config=global_config,
            working_dir=working_dir
        )
        if not commit_result.success:
            raise SupsrcError(f"Commit failed: {commit_result.message}")

        if commit_result.commit_hash is None:
             # This indicates "nothing to commit" was detected by the engine
             callback_log.info("Commit skipped by engine (no changes detected after staging).")
             repo_state.reset_after_action() # Reset to IDLE
             return
        else:
             callback_log.info("Commit successful", hash=commit_result.commit_hash)

        # --- 4. Perform Push (if applicable) ---
        # The engine's perform_push method internally checks the 'auto_push' config
        repo_state.update_status(RepositoryStatus.PUSHING)
        callback_log.debug("Checking auto-push and potentially pushing...")
        push_result = await repo_engine.perform_push(repo_state, engine_config_dict, global_config, working_dir)

        if not push_result.success:
             # Log push failure as warning, but don't necessarily stop monitoring
             callback_log.warning("Push failed or skipped", reason=push_result.message)
             # Decide if state should be ERROR or just go back to IDLE after commit success
             # For now, go back to IDLE as commit succeeded.
             repo_state.reset_after_action()
        else:
             if "skipped" not in push_result.message.lower(): # Avoid logging success if skipped
                  callback_log.info("Push successful.")
             repo_state.reset_after_action() # Reset to IDLE after successful push/skip

    except Exception as action_exc:
        callback_log.error("Error during triggered action execution", error=str(action_exc), exc_info=True)
        repo_state.update_status(RepositoryStatus.ERROR, f"Action failed: {action_exc}")
        # Do not reset state here, leave it in ERROR

# --- Event Consumer Logic ---
async def consume_events(
    event_queue: asyncio.Queue[MonitoredEvent],
    repo_states: RepositoryStatesMap,
    config: SupsrcConfig,
    shutdown_event: asyncio.Event,
    # Pass the dictionary of loaded engines
    repo_engines: dict[str, RepositoryEngine]
) -> None:
    """
    Consumes events from the queue, updates state, manages timers, and checks rules.
    """
    consumer_log = log.bind(component="EventConsumer")
    consumer_log.info("Event consumer started, waiting for file events...")
    loop = asyncio.get_running_loop()
    get_task: asyncio.Task | None = None

    while not shutdown_event.is_set():
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
                     get_task = None; await asyncio.sleep(0.5); continue

                get_task = None
                event_log = consumer_log.bind(repo_id=event.repo_id, event_type=event.event_type, src_path=str(event.src_path))
                event_log.debug("Consumer received event details")

                repo_id = event.repo_id
                repo_state = repo_states.get(repo_id)
                repo_config = config.repositories.get(repo_id)
                repo_engine = repo_engines.get(repo_id) # Get pre-loaded engine

                if not repo_state or not repo_config or not repo_engine:
                    event_log.warning("Received event for unknown/disabled/unconfigured repository, ignoring.",
                                      has_state=bool(repo_state), has_config=bool(repo_config), has_engine=bool(repo_engine))
                    event_queue.task_done(); continue

                repo_state.record_change()
                event_log = event_log.bind(save_count=repo_state.save_count, status=repo_state.status.name)

                # --- Check Rules ---
                rule_config_obj: RuleConfig = repo_config.rule
                rule_type_str = getattr(rule_config_obj, 'type', 'unknown_rule_type')

                try:
                    if check_trigger_condition(repo_state, repo_config):
                        event_log.info("Rule condition met, scheduling action", rule_type=rule_type_str)
                        # Pass the specific engine instance for this repo
                        asyncio.create_task(_trigger_action_callback(event.repo_id, repo_states, config, repo_engine))
                    else:
                        if isinstance(rule_config_obj, InactivityRuleConfig):
                             delay = rule_config_obj.period.total_seconds()
                             event_log.debug("Rescheduling inactivity check", delay_seconds=delay)
                             timer_handle = loop.call_later(
                                 delay,
                                 # Pass engine to the lambda as well
                                 lambda rid=event.repo_id, eng=repo_engine: asyncio.create_task(
                                     _trigger_action_callback(rid, repo_states, config, eng)
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
            get_task = None; await asyncio.sleep(1)

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
        self.repo_engines: dict[str, RepositoryEngine] = {} # Store loaded engines
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
                 raise
            except Exception as e:
                 self._safe_log("critical", "Unexpected error loading configuration", error=str(e), exc_info=True)
                 raise

            # --- Initialize State & Load Engines ---
            self._safe_log("debug", "Initializing repository states, loading engines, and getting summaries...")
            # Pass the engine registry (or loading function) if dynamic
            enabled_repo_ids = await self._initialize_repositories() # Combined init
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
                # Pass the loaded engines to the consumer
                consume_events(self.event_queue, self.repo_states, self.config, self.shutdown_event, self.repo_engines),
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
            # ... (Cleanup logic for timers, tasks, monitor service remains the same) ...
            # 1. Cancel Repository Timers
            self._safe_log("debug", "Cancelling active repository timers...")
            timers_cancelled = 0
            for repo_id, state in self.repo_states.items():
                 if state.inactivity_timer_handle:
                     try: state.cancel_inactivity_timer(); timers_cancelled += 1
                     except Exception as timer_cancel_e: self._safe_log("warning", "Error cancelling timer", repo_id=repo_id, error=str(timer_cancel_e))
            self._safe_log("debug", f"Cancelled {timers_cancelled} repository timer(s).")

            # 2. Cancel Running Async Tasks (Consumer)
            if self._running_tasks:
                self._safe_log("debug", f"Cancelling {len(self._running_tasks)} running task(s)...", tasks=[t.get_name() for t in self._running_tasks])
                tasks_to_cancel = list(self._running_tasks); [t.cancel() for t in tasks_to_cancel if not t.done()]
                self._safe_log("debug", "Waiting for cancelled tasks to finish...")
                try:
                     gathered_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                     self._safe_log("debug", "Running tasks cancellation gathered.", results=[type(r).__name__ for r in gathered_results])
                except Exception as gather_exc: self._safe_log("error", "Exception during task gathering", error=str(gather_exc), exc_info=True)
            else: self._safe_log("debug", "No running asyncio tasks found to cancel.")

            # 3. Stop Monitoring Service (joins thread)
            if self.monitor_service and self.monitor_service.is_running:
                 self._safe_log("debug", "Stopping monitoring service (includes joining observer thread)...")
                 try: await self.monitor_service.stop(); self._safe_log("debug", "Monitoring service stop completed.")
                 except Exception as stop_exc: self._safe_log("error", "Error during monitoring service stop", error=str(stop_exc), exc_info=True)
            elif self.monitor_service: self._safe_log("debug", "Monitoring service was not running or already stopped.")
            else: self._safe_log("debug", "Monitoring service was not initialized.")

            self._safe_log("info", "Orchestrator finished cleanup.")

    async def _initialize_repositories(self) -> list[str]:
        """Initializes states, loads engines, and logs initial repo summary."""
        enabled_repo_ids = []
        if not self.config: return []

        self._safe_log("info", "--- Initializing Repositories ---")
        for repo_id, repo_config in self.config.repositories.items():
            if repo_config.enabled and repo_config._path_valid:
                # Initialize state
                self.repo_states[repo_id] = RepositoryState(repo_id=repo_id)
                enabled_repo_ids.append(repo_id)
                self._safe_log("debug", "Initialized state object", repo_id=repo_id)

                # Load Engine for this repo
                engine_config = repo_config.repository
                engine_type = engine_config.get("type")
                engine_instance: Optional[RepositoryEngine] = None
                if not engine_type:
                     self._safe_log("error", "Repository configuration missing 'type' for engine.", repo_id=repo_id)
                     self.repo_states[repo_id].update_status(RepositoryStatus.ERROR, "Missing engine type in config")
                     continue # Skip this repo

                try:
                    # TODO: Replace direct instantiation with plugin loading
                    if engine_type == "supsrc.engines.git":
                         engine_instance = GitEngine() # Instantiate directly for now
                         self.repo_engines[repo_id] = engine_instance
                         self._safe_log("debug", "Loaded GitEngine", repo_id=repo_id)
                    else:
                         raise NotImplementedError(f"Engine type '{engine_type}' not supported yet.")
                    # engine_instance = load_plugin(engine_type, RepositoryEngine) # Future state
                    # self.repo_engines[repo_id] = engine_instance
                except Exception as load_exc:
                    self._safe_log("error", "Failed to load repository engine", repo_id=repo_id, engine_type=engine_type, error=str(load_exc))
                    self.repo_states[repo_id].update_status(RepositoryStatus.ERROR, f"Failed to load engine: {load_exc}")
                    continue # Skip summary if engine failed

                # Get and log summary using the loaded engine
                try:
                    summary = await engine_instance.get_summary(repo_config.path)
                    if summary.is_empty:
                         self._safe_log("info", "Repository empty (no commits yet).", repo_id=repo_id)
                    elif "ERROR" in (summary.head_ref_name or ""):
                         self._safe_log("warning", f"Could not retrieve repository HEAD summary: {summary.head_ref_name}", repo_id=repo_id)
                    elif summary.head_ref_name == "UNBORN":
                         self._safe_log("info", "Repository HEAD is unborn (no commits yet).", repo_id=repo_id)
                    else:
                         log_msg = f"HEAD: {summary.head_ref_name or 'DETACHED'}@{summary.head_commit_hash[:7] if summary.head_commit_hash else 'N/A'}"
                         if summary.head_commit_message_summary:
                              log_msg += f" | Last commit: {summary.head_commit_message_summary}"
                         self._safe_log("info", log_msg, repo_id=repo_id)
                except Exception as summary_exc:
                    self._safe_log("error", "Failed to get initial repo summary", repo_id=repo_id, error=str(summary_exc))

            else:
                self._safe_log("info", "Skipping initialization for disabled/invalid repo", repo_id=repo_id)

        self._safe_log("info", "--- Repository Initialization Complete ---")
        self._safe_log("info", "Enabled repositories active", count=len(enabled_repo_ids), repos=enabled_repo_ids)
        return enabled_repo_ids

    def _setup_monitoring(self, enabled_repo_ids: list[str]) -> list[str]:
        """Adds repositories to the MonitoringService."""
        # ... (implementation remains the same) ...
        setup_errors = 0
        successfully_added_ids = []
        if not self.monitor_service or not self.config: return []

        for repo_id in enabled_repo_ids:
             # Only add repos that successfully loaded an engine in the previous step
             if repo_id not in self.repo_engines:
                  self._safe_log("warning", "Skipping monitoring setup for repo with failed engine load", repo_id=repo_id)
                  continue

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
