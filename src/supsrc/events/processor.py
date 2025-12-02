#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Consumes filesystem events, checks rules, manages timers, and triggers actions."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from provide.foundation.logger import get_logger

from supsrc.config import InactivityRuleConfig, RepositoryConfig, SupsrcConfig
from supsrc.config.defaults import DEFAULT_DEBOUNCE_DELAY
from supsrc.events.buffer import EventBuffer
from supsrc.monitor import MonitoredEvent
from supsrc.rules import check_trigger_condition
from supsrc.services.circuit_breaker import CircuitBreakerService
from supsrc.state import RepositoryState, RepositoryStatus

if TYPE_CHECKING:
    from supsrc.events.collector import EventCollector
    from supsrc.protocols import RepositoryEngine
    from supsrc.runtime.action_handler import ActionHandler
    from supsrc.runtime.tui_interface import TUIInterface

log = get_logger("runtime.event_processor")


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
        event_collector: "EventCollector | None" = None,
    ):
        self.config = config
        self.event_queue = event_queue
        self.shutdown_event = shutdown_event
        self.action_handler = action_handler
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui = tui
        self.config_reload_callback = config_reload_callback
        self.event_collector = event_collector
        self._action_tasks: set[asyncio.Task] = set()
        self._recent_moves: set[Path] = set()

        # Initialize timer check debouncing to prevent constant timer resets
        self._pending_timer_checks: dict[str, asyncio.Task] = {}
        self._timer_check_delay = 0.5  # 500ms debounce delay for timer checks

        # Initialize circuit breaker service
        self._circuit_breaker = CircuitBreakerService(config.global_config.circuit_breaker)

        # Detect runtime mode (TUI vs headless) and select appropriate grouping
        global_config = config.global_config
        is_tui_mode = tui and hasattr(tui, "app") and tui.app is not None

        # Select mode-specific grouping or fall back to legacy field
        if is_tui_mode:
            grouping_mode = global_config.event_grouping_mode_tui
            mode_name = "TUI"
        else:
            grouping_mode = global_config.event_grouping_mode_headless
            mode_name = "headless"

        log.info(
            f"Detected {mode_name} mode, using event grouping",
            mode=mode_name,
            grouping_mode=grouping_mode,
        )

        # Initialize event buffer for TUI events
        if global_config.event_buffering_enabled:
            self._event_buffer = EventBuffer(
                window_ms=global_config.event_buffer_window_ms,
                grouping_mode=grouping_mode,
                emit_callback=self._emit_buffered_event,
            )
        else:
            self._event_buffer = None

        log.debug(
            "EventProcessor initialized.",
            event_buffering_enabled=global_config.event_buffering_enabled,
            buffer_window_ms=global_config.event_buffer_window_ms,
            grouping_mode=grouping_mode,
            runtime_mode=mode_name,
        )

    def _notify_circuit_breaker_trigger(self, repo_state: RepositoryState) -> None:
        """Print visible notification when circuit breaker triggers.

        Args:
            repo_state: Repository state with circuit breaker information
        """
        is_tui_mode = self.tui and hasattr(self.tui, "app") and self.tui.app is not None

        # Get status emoji and information
        status_emoji = repo_state.display_status_emoji
        repo_id = repo_state.repo_id
        reason = repo_state.circuit_breaker_reason or "Unknown reason"
        file_count = len(repo_state.bulk_change_files)

        # Format notification message
        header = f"\n{status_emoji} CIRCUIT BREAKER TRIGGERED: {repo_id}"
        reason_line = f"   Reason: {reason}"
        files_line = f"   Files affected: {file_count}" if file_count > 0 else ""
        action_line = f"   Action: supsrc cb ack {repo_id}"
        footer = "   Events blocked until acknowledged.\n"

        message_lines = [header, reason_line]
        if files_line:
            message_lines.append(files_line)
        message_lines.extend([action_line, footer])
        "\n".join(message_lines)

        log.debug(
            "Preparing circuit breaker notification",
            repo_id=repo_id,
            is_tui_mode=is_tui_mode,
            file_count=file_count,
        )

        # Print to console in headless mode, post to TUI in TUI mode
        if not is_tui_mode:
            # Headless mode: print directly to stdout for visibility
            log.debug("Circuit breaker notification printed to console (headless mode)", repo_id=repo_id)
        else:
            # TUI mode: log and rely on status update (TUI will show the emoji/status)
            # We can't print to stdout in TUI mode as it corrupts the display
            log.warning(
                "Circuit breaker triggered (TUI mode - check status display)",
                repo_id=repo_id,
                status=repo_state.status.name,
                reason=reason,
            )
            log.debug(
                "Circuit breaker notification sent to TUI status update",
                repo_id=repo_id,
                status_emoji=status_emoji,
            )

        # Always log warning for file-based logging (important event)
        log.warning(
            "Circuit breaker triggered",
            repo_id=repo_id,
            status=repo_state.status.name,
            reason=reason,
            file_count=file_count,
            bulk_files_sample=list(repo_state.bulk_change_files)[:10] if file_count > 0 else [],
        )

    def _emit_event(self, event: Any) -> None:
        """Emit event to all available event collectors (TUI and global).

        Args:
            event: Event to emit
        """
        emitted_to_tui = False
        emitted_to_global = False

        # Emit to TUI event collector if available
        if self.tui and hasattr(self.tui, "app") and self.tui.app and hasattr(self.tui.app, "event_collector"):
            try:
                self.tui.app.event_collector.emit(event)  # type: ignore[arg-type,union-attr]
                emitted_to_tui = True
                log.debug(
                    "Event emitted to TUI event collector",
                    event_type=type(event).__name__,
                    repo_id=getattr(event, "repo_id", "unknown"),
                )
            except Exception as e:
                log.warning(
                    "Failed to emit event to TUI event collector",
                    error=str(e),
                    event_type=type(event).__name__,
                    exc_info=True,
                )

        # Emit to global event collector if available (and different from TUI's)
        if self.event_collector:
            # Only emit if it's not the same collector as TUI's (avoid duplicates)
            is_same_collector = (
                emitted_to_tui
                and hasattr(self.tui.app, "event_collector")
                and self.event_collector is self.tui.app.event_collector
            )

            if not is_same_collector:
                try:
                    self.event_collector.emit(event)  # type: ignore[arg-type]
                    emitted_to_global = True
                    log.debug(
                        "Event emitted to global event collector",
                        event_type=type(event).__name__,
                        repo_id=getattr(event, "repo_id", "unknown"),
                    )
                except Exception as e:
                    log.warning(
                        "Failed to emit event to global event collector",
                        error=str(e),
                        event_type=type(event).__name__,
                        exc_info=True,
                    )

        if not (emitted_to_tui or emitted_to_global):
            log.debug(
                "Event not emitted - no event collectors available",
                event_type=type(event).__name__,
            )

    async def run(self) -> None:
        """Main event consumption loop."""
        log.info("Event processor is running.")
        loop = asyncio.get_running_loop()

        while not self.shutdown_event.is_set():
            try:
                # Gracefully wait for either an event or a shutdown signal
                get_task = asyncio.create_task(self.event_queue.get())
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())
                done, _pending = await asyncio.wait(
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

                if repo_state.is_paused:
                    log.debug("Repo is paused, event ignored", repo_id=event.repo_id)
                    continue

                # Check circuit breaker before processing
                if not self._circuit_breaker.should_process_event(repo_state):
                    log.debug(
                        "Event blocked by circuit breaker",
                        repo_id=event.repo_id,
                        status=repo_state.status.name,
                    )
                    self.tui.post_state_update(self.repo_states)
                    continue

                # Track bulk changes for circuit breaker (before recording)
                file_path_str = str(event.src_path)
                if self._circuit_breaker.check_and_update_bulk_change(repo_state, file_path_str):
                    self._notify_circuit_breaker_trigger(repo_state)
                    self.tui.post_state_update(self.repo_states)
                    continue

                # Deduplicate moved/deleted events
                if event.event_type == "moved":
                    self._recent_moves.add(event.src_path)
                    loop.call_later(0.5, self._recent_moves.discard, event.src_path)
                elif event.event_type == "deleted" and event.src_path in self._recent_moves:
                    log.debug("Ignoring duplicate delete event for a moved file", path=str(event.src_path))
                    continue

                # Record the change and update UI
                repo_state.record_change()

                # Handle timer logic - check if repo is clean after any change (with debouncing)
                repo_config = self.config.repositories.get(event.repo_id)
                if repo_config and isinstance(repo_config.rule, InactivityRuleConfig):
                    # Use debounced timer check to prevent constant timer resets
                    self._schedule_debounced_timer_check(event.repo_id)

                # Schedule async refresh of repository statistics for real-time UI updates
                task = asyncio.create_task(self._refresh_repository_statistics(event.repo_id))
                task.add_done_callback(lambda _: None)  # Ensure task is properly handled

                self.tui.post_state_update(self.repo_states)

                # Emit file change event (with optional buffering)
                try:
                    from supsrc.events.monitor import FileChangeEvent

                    change_event = FileChangeEvent(
                        description=f"File {event.event_type}: {event.src_path.name}",
                        repo_id=event.repo_id,
                        file_path=event.src_path,
                        change_type=event.event_type,
                        dest_path=event.dest_path,  # Preserve destination for move events
                    )

                    # Use buffering if enabled, otherwise emit directly
                    if self._event_buffer:
                        log.info(
                            "📥 RAW EVENT RECEIVED",
                            event_type=event.event_type,
                            file_name=event.src_path.name,
                            dest_name=event.dest_path.name if event.dest_path else None,
                            repo_id=event.repo_id,
                            timestamp=change_event.timestamp.strftime("%H:%M:%S.%f"),
                        )
                        self._event_buffer.add_event(change_event)
                    else:
                        # Emit directly to all available event collectors
                        self._emit_event(change_event)
                        log.debug(
                            "File change event emitted directly",
                            event_type=event.event_type,
                            file_name=event.src_path.name,
                            repo_id=event.repo_id,
                        )
                except Exception as e:
                    log.warning(
                        "Failed to emit file change event",
                        error=str(e),
                        event_type=event.event_type,
                        repo_id=event.repo_id,
                        exc_info=True,
                    )

                # For inactivity rules, start timer immediately (as mentioned in comment above)
                repo_config = self.config.repositories.get(event.repo_id)
                if repo_config and isinstance(repo_config.rule, InactivityRuleConfig):
                    # Start inactivity timer immediately
                    self._start_inactivity_timer(repo_state, repo_config)
                    # Also start debounced timer check to handle rapid changes
                    self._schedule_debounced_timer_check(event.repo_id)

                # Start debounced check for save count rules and other trigger conditions
                self._debounce_trigger_check(event.repo_id)

            except asyncio.CancelledError:
                log.info("Event processor run loop cancelled.")
                break
            except Exception as e:
                log.exception("Error in event processor loop", error=str(e), exc_info=True)

        await self.stop()
        log.info("Event processor has stopped.")

    def _debounce_trigger_check(self, repo_id: str):
        """Schedules a trigger check to run after a short delay, canceling any pending one."""
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            return

        repo_state.cancel_debounce_timer()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(DEFAULT_DEBOUNCE_DELAY, self._execute_trigger_check, repo_id)
        repo_state.set_debounce_timer(handle)
        log.debug("Debounce timer set", repo_id=repo_id, delay=DEFAULT_DEBOUNCE_DELAY)

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

        trigger_met = check_trigger_condition(repo_state, repo_config)
        log.debug(
            "Trigger check result",
            repo_id=repo_id,
            trigger_met=trigger_met,
            rule_type=type(repo_config.rule).__name__,
            is_inactivity_rule=isinstance(repo_config.rule, InactivityRuleConfig),
        )

        if trigger_met:
            log.debug("Scheduling immediate action", repo_id=repo_id)
            self._schedule_action(repo_id)
        # Note: Inactivity timer is already started immediately on file change,
        # no need to start it again here during debounce check

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
        task = asyncio.create_task(self.action_handler.execute_action_sequence(repo_id))
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

        # Immediately notify TUI that timer has started so countdown is visible
        self.tui.post_state_update(self.repo_states)

    async def _refresh_repository_statistics(self, repo_id: str) -> None:
        """Refresh repository file statistics after file changes for real-time UI updates."""
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)

        if not all((repo_state, repo_config, repo_engine)):
            log.debug("Cannot refresh statistics: missing state, config, or engine", repo_id=repo_id)
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

                # Check for branch changes before updating current_branch
                if status_result.current_branch:
                    _branch_changed, breaker_triggered = self._circuit_breaker.check_branch_change(
                        repo_state, status_result.current_branch
                    )
                    if breaker_triggered:
                        self._notify_circuit_breaker_trigger(repo_state)

                repo_state.current_branch = status_result.current_branch
                log.debug(
                    "Repository statistics refreshed",
                    repo_id=repo_id,
                    changed_files=repo_state.changed_files,
                )
                # Update UI with refreshed statistics
                self.tui.post_state_update(self.repo_states)
        except Exception as e:
            log.debug("Failed to refresh repository statistics", repo_id=repo_id, error=str(e))

    async def _check_repo_status_and_handle_timer(self, repo_id: str) -> None:
        """Check repository status after any change and start/stop timer accordingly."""
        # Wait a moment for filesystem changes to settle
        await asyncio.sleep(0.1)

        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)

        if not repo_state or not repo_config:
            return

        # If no engine available (e.g., in tests), just start inactivity timer for inactivity rules
        if not repo_engine:
            if isinstance(repo_config.rule, InactivityRuleConfig):
                self._start_inactivity_timer(repo_state, repo_config)
                self.tui.post_state_update(self.repo_states)
            return

        try:
            # Check current repository status
            status_result = await repo_engine.get_status(
                repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )

            if status_result.success:
                if status_result.is_clean:
                    # Repository is clean - stop timer and set to IDLE
                    log.debug(f"Repository {repo_id} is clean, stopping timer")
                    repo_state.cancel_inactivity_timer()
                    repo_state.update_status(RepositoryStatus.IDLE)

                    # Update repository statistics to reflect clean state
                    repo_state.total_files = status_result.total_files or 0
                    repo_state.changed_files = 0
                    repo_state.added_files = 0
                    repo_state.deleted_files = 0
                    repo_state.modified_files = 0
                    repo_state.has_uncommitted_changes = False
                    repo_state.current_branch = status_result.current_branch
                else:
                    # Repository has changes - start inactivity timer
                    log.debug(f"Repository {repo_id} has changes, starting timer")
                    if isinstance(repo_config.rule, InactivityRuleConfig):
                        self._start_inactivity_timer(repo_state, repo_config)

                # Always update UI to reflect current state
                self.tui.post_state_update(self.repo_states)

        except Exception as e:
            log.debug("Failed to check repository status", repo_id=repo_id, error=str(e))

    def _schedule_debounced_timer_check(self, repo_id: str) -> None:
        """Schedule a debounced timer check to prevent constant timer resets with rapid changes."""
        # Cancel any pending timer check for this repo
        if repo_id in self._pending_timer_checks:
            self._pending_timer_checks[repo_id].cancel()

        # Schedule new timer check after debounce delay
        async def debounced_timer_check():
            try:
                await asyncio.sleep(self._timer_check_delay)
                # Remove from pending checks since we're about to execute
                self._pending_timer_checks.pop(repo_id, None)
                # Now actually check repo status and handle timer
                await self._check_repo_status_and_handle_timer(repo_id)
            except asyncio.CancelledError:
                # Clean up if cancelled
                self._pending_timer_checks.pop(repo_id, None)
                raise

        task = asyncio.create_task(debounced_timer_check())
        self._pending_timer_checks[repo_id] = task

        log.debug(
            "Scheduled debounced timer check",
            repo_id=repo_id,
            delay_ms=self._timer_check_delay * 1000,
        )

    def _emit_buffered_event(self, event: Any) -> None:
        """Emit a buffered event to all available event collectors."""
        try:
            file_paths = getattr(event, "file_paths", [])
            file_names = [p.name for p in file_paths] if file_paths else []

            log.info(
                "📤 EMITTING BUFFERED EVENT",
                operation_type=getattr(event, "operation_type", "unknown"),
                file_names=file_names,
                event_count=getattr(event, "event_count", 1),
                repo_id=getattr(event, "repo_id", "unknown"),
                timestamp=event.timestamp.strftime("%H:%M:%S.%f"),
            )

            # Emit to all available event collectors
            self._emit_event(event)
        except Exception as e:
            log.warning(
                "Failed to emit buffered event",
                error=str(e),
                event_type=getattr(event, "operation_type", "unknown"),
                exc_info=True,
            )

    async def stop(self) -> None:
        """Gracefully stop all scheduled action tasks."""
        # Flush any pending buffered events
        if self._event_buffer:
            self._event_buffer.flush_all()

        # Cancel any pending timer checks
        for _repo_id, task in self._pending_timer_checks.items():
            task.cancel()
        self._pending_timer_checks.clear()
        log.debug("Cancelled pending timer checks")

        if not self._action_tasks:
            return
        log.debug("Stopping in-flight action tasks", count=len(self._action_tasks))
        for task in list(self._action_tasks):
            task.cancel()
        await asyncio.gather(*self._action_tasks, return_exceptions=True)
        log.debug("All action tasks cancelled.")


# 🔼⚙️🔚
