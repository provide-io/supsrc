# src/supsrc/runtime/event_processor.py
"""
Consumes filesystem events, checks rules, manages timers, and triggers actions.
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

from supsrc.config import InactivityRuleConfig, RepositoryConfig, SupsrcConfig
from supsrc.monitor import MonitoredEvent
from supsrc.rules import check_trigger_condition
from supsrc.state import RepositoryState, RepositoryStatus

if TYPE_CHECKING:
    from supsrc.protocols import RepositoryEngine
    from supsrc.runtime.action_handler import ActionHandler
    from supsrc.runtime.tui_interface import TUIInterface

log = get_logger("runtime.event_processor")
# Debounce delay to group rapid file system events (e.g., create + modify) into one action.
DEBOUNCE_DELAY = 0.25  # 250 milliseconds


class EventProcessor:
    """Consumes events, checks rules, and delegates actions."""

    def __init__(
        self,
        config: SupsrcConfig,
        event_queue: asyncio.Queue[MonitoredEvent],
        shutdown_event: asyncio.Event,
        action_handler: "ActionHandler",
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, "RepositoryEngine"],
        tui: "TUIInterface",
        config_reload_callback: "Any",
    ):
        self.config = config
        self.event_queue = event_queue
        self.shutdown_event = shutdown_event
        self.action_handler = action_handler
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui = tui
        self.config_reload_callback = config_reload_callback
        self._action_tasks: set[asyncio.Task] = set()
        self._recent_moves: set[Path] = set()
        log.debug("EventProcessor initialized.")

    async def run(self) -> None:
        """Main event consumption loop."""
        log.info("Event processor is running.")
        loop = asyncio.get_running_loop()

        while not self.shutdown_event.is_set():
            try:
                # Gracefully wait for either an event or a shutdown signal
                get_task = asyncio.create_task(self.event_queue.get())
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())
                done, pending = await asyncio.wait(
                    {get_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if shutdown_task in done:
                    get_task.cancel()
                    break

                event = get_task.result()
                shutdown_task.cancel()

                # Handle special config reload event
                if event.repo_id == "__config__":
                    log.info("Configuration change event received, triggering reload.")
                    reload_task = asyncio.create_task(self.config_reload_callback())
                    # Store task reference to avoid warning (task runs independently)
                    reload_task.add_done_callback(lambda t: None)
                    continue

                # Get state and check if processing is paused
                repo_state = self.repo_states.get(event.repo_id)
                if not repo_state:
                    log.warning("Ignoring event for unknown repo", repo_id=event.repo_id)
                    continue
                orchestrator_paused = (
                    (
                        self.orchestrator.monitoring_coordinator
                        and self.orchestrator.monitoring_coordinator.is_paused
                    )
                    if self.orchestrator.monitoring_coordinator
                    else False
                )
                if repo_state.is_paused or orchestrator_paused:
                    log.debug(
                        "Repo or orchestrator is paused, event ignored", repo_id=event.repo_id
                    )
                    continue

                # Deduplicate moved/deleted events
                if event.event_type == "moved":
                    self._recent_moves.add(event.src_path)
                    loop.call_later(0.5, self._recent_moves.discard, event.src_path)
                elif event.event_type == "deleted" and event.src_path in self._recent_moves:
                    log.debug(
                        "Ignoring duplicate delete event for a moved file", path=str(event.src_path)
                    )
                    continue

                # Record the change and update UI
                repo_state.record_change()

                # Schedule async refresh of repository statistics for real-time UI updates
                task = asyncio.create_task(self._refresh_repository_statistics(event.repo_id))
                task.add_done_callback(lambda _: None)  # Ensure task is properly handled

                self.tui_post_state_update(self.repo_states)

                # Emit file change event for TUI event feed
                if hasattr(self.tui_app, "event_collector"):
                    from supsrc.events.monitor import FileChangeEvent

                    change_event = FileChangeEvent(
                        description=f"File {event.event_type}: {event.src_path.name}",
                        repo_id=event.repo_id,
                        file_path=event.src_path,
                        change_type=event.event_type,
                    )
                    self.tui_app.event_collector.emit(change_event)  # type: ignore[arg-type,union-attr]

                # Instead of acting immediately, start a debounced check
                self._debounce_trigger_check(event.repo_id)

            except asyncio.CancelledError:
                log.info("Event processor run loop cancelled.")
                break
            except Exception:
                log.exception("Error in event processor loop.")

        await self.stop()
        log.info("Event processor has stopped.")

    def _debounce_trigger_check(self, repo_id: str):
        """Schedules a trigger check to run after a short delay, canceling any pending one."""
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            return

        repo_state.cancel_debounce_timer()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(DEBOUNCE_DELAY, self._execute_trigger_check, repo_id)
        repo_state.set_debounce_timer(handle)
        log.debug("Debounce timer set", repo_id=repo_id, delay=DEBOUNCE_DELAY)

    def _execute_trigger_check(self, repo_id: str):
        """Called by the debounce timer. Checks rules and triggers the appropriate action."""
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        if not repo_state or not repo_config:
            return

        log.debug("Executing debounced trigger check", repo_id=repo_id)

        # Do not proceed if an action is already in progress for this repo
        if repo_state.status not in (RepositoryStatus.IDLE, RepositoryStatus.CHANGED):
            log.debug(
                "Action already in progress, skipping trigger check",
                repo_id=repo_id,
                status=repo_state.status.name,
            )
            return

        if check_trigger_condition(repo_state, repo_config):
            self._schedule_action(repo_id)
        elif isinstance(repo_config.rule, InactivityRuleConfig):
            # If the save count rule wasn't met, the inactivity rule might still apply
            self._start_inactivity_timer(repo_state, repo_config)

    def _schedule_action(self, repo_id: str) -> None:
        """Schedules the action handler to execute for a repo."""
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            return

        # Set status to TRIGGERED to act as a lock
        repo_state.update_status(RepositoryStatus.TRIGGERED)
        # Clean up all timers for this repo before starting the action
        repo_state.cancel_inactivity_timer()
        repo_state.cancel_debounce_timer()

        log.info("Trigger condition met, scheduling action sequence.", repo_id=repo_id)
        task = asyncio.create_task(self.action_execution_callback(repo_id))
        self._action_tasks.add(task)
        task.add_done_callback(self._action_tasks.discard)

    def _start_inactivity_timer(self, state: RepositoryState, config: RepositoryConfig) -> None:
        """Sets or resets an inactivity timer for a repository."""
        if not isinstance(config.rule, InactivityRuleConfig):
            return

        delay = config.rule.period.total_seconds()
        log.debug("Starting inactivity timer", repo_id=state.repo_id, delay=delay)

        loop = asyncio.get_running_loop()
        handle = loop.call_later(delay, self._schedule_action, state.repo_id)
        state.set_inactivity_timer(handle, int(delay))

    async def _refresh_repository_statistics(self, repo_id: str) -> None:
        """Refresh repository file statistics after file changes for real-time UI updates."""
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)

        if not all((repo_state, repo_config, repo_engine)):
            log.debug(
                "Cannot refresh statistics: missing state, config, or engine", repo_id=repo_id
            )
            return

        try:
            status_result = await repo_engine.get_status(
                repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )
            if status_result.success:
                repo_state.total_files = status_result.total_files or 0
                repo_state.changed_files = status_result.changed_files or 0
                repo_state.added_files = status_result.added_files or 0
                repo_state.deleted_files = status_result.deleted_files or 0
                repo_state.modified_files = status_result.modified_files or 0
                repo_state.has_uncommitted_changes = not status_result.is_clean
                repo_state.current_branch = status_result.current_branch
                log.debug(
                    "Repository statistics refreshed",
                    repo_id=repo_id,
                    changed_files=repo_state.changed_files,
                )
                # Update UI with refreshed statistics
                self.tui_post_state_update(self.repo_states)
        except Exception as e:
            log.debug("Failed to refresh repository statistics", repo_id=repo_id, error=str(e))

    async def stop(self) -> None:
        """Gracefully stop all scheduled action tasks."""
        if not self._action_tasks:
            return
        log.debug("Stopping in-flight action tasks", count=len(self._action_tasks))
        for task in list(self._action_tasks):
            task.cancel()
        await asyncio.gather(*self._action_tasks, return_exceptions=True)
        log.debug("All action tasks cancelled.")
