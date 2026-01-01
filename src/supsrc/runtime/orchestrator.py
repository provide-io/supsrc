# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""High-level coordinator for the supsrc watch process.
Manages lifecycle of all runtime components."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, TypeAlias

# Add Foundation error handling and metrics patterns
from provide.foundation.errors import resilient
from provide.foundation.logger import get_logger
from provide.foundation.metrics import counter, gauge
from rich.console import Console

from supsrc.config import SupsrcConfig, load_config
from supsrc.events.collector import EventCollector
from supsrc.events.json_logger import JSONEventLogger
from supsrc.events.processor import EventProcessor
from supsrc.exceptions import ConfigurationError
from supsrc.monitor import MonitoredEvent
from supsrc.output.console_formatter import ConsoleEventFormatter
from supsrc.protocols import RepositoryEngine
from supsrc.runtime.action_handler import ActionHandler
from supsrc.runtime.monitoring_coordinator import MonitoringCoordinator
from supsrc.runtime.repository_manager import RepositoryManager
from supsrc.runtime.status_manager import StatusManager
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.state import RepositoryState

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


log = get_logger("runtime.orchestrator")
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]
RULE_EMOJI_MAP: dict[str, str] = {
    "supsrc.rules.inactivity": "⏳",
    "supsrc.rules.save_count": "💾",
    "supsrc.rules.manual": "✋",
}

# Initialize Foundation metrics (work with or without OpenTelemetry)
orchestrator_starts = counter("orchestrator_starts", "Number of orchestrator start attempts")
orchestrator_errors = counter("orchestrator_errors", "Number of orchestrator errors")
active_repositories = gauge("active_repositories", "Number of actively monitored repositories")
config_reloads = counter("config_reloads", "Number of configuration reloads")


class WatchOrchestrator:
    """Instantiates and coordinates all runtime components for the watch command."""

    def __init__(
        self,
        config_path: Path,
        shutdown_event: asyncio.Event,
        app: SupsrcTuiApp | None = None,
        console: Console | None = None,
        event_log_path: Path | None = None,
        use_color: bool = True,
        use_ascii: bool = False,
        verbose: bool = False,
        verbose_format: str = "table",
        app_log_path: Path | None = None,
    ):
        self.config_path = config_path
        self.shutdown_event = shutdown_event
        self.app = app
        self.console = console
        self.event_log_path = event_log_path
        self.use_color = use_color
        self.use_ascii = use_ascii
        self.verbose = verbose
        self.verbose_format = verbose_format
        self.app_log_path = app_log_path or Path(tempfile.gettempdir()) / "supsrc_app.log"
        self.event_queue: asyncio.Queue[MonitoredEvent] = asyncio.Queue()
        self.repo_states: RepositoryStatesMap = {}
        self.repo_engines: dict[str, RepositoryEngine] = {}
        self.event_processor: EventProcessor | None = None
        self.config: SupsrcConfig | None = None
        self.status_manager: StatusManager | None = None

        # Event system for headless mode
        self.event_collector: EventCollector | None = None
        self.json_logger: JSONEventLogger | None = None
        self.console_formatter: ConsoleEventFormatter | None = None

        # Timer update task for headless mode
        self.timer_update_task: asyncio.Task | None = None
        self._last_emitted_timers: dict[str, int] = {}  # Track last emitted timer value per repo

        # Initialize helper managers
        self.repository_manager: RepositoryManager | None = None
        self.monitoring_coordinator: MonitoringCoordinator | None = None

    @resilient(log_errors=True, context_provider=lambda: {"component": "orchestrator", "method": "run"})
    async def run(self) -> None:
        """Main execution method: setup, run, and cleanup."""
        orchestrator_starts.inc()
        log.info("Orchestrator run sequence starting.")
        processor_task = None
        tui = TUIInterface(self.app)

        try:
            try:
                self.config = await asyncio.to_thread(load_config, self.config_path)
            except ConfigurationError as e:
                log.critical("Failed to load or validate config", error=str(e), exc_info=True)
                tui.post_log_update(None, "CRITICAL", f"Config Error: {e}")
                await asyncio.sleep(0.1)
                return

            # Initialize event system
            if self.app:
                # TUI mode: use the app's event collector
                log.info("Using TUI app event collector for event collection")
                self.event_collector = self.app.event_collector
            elif self.event_log_path:
                # Headless mode: create standalone event collector with JSON logging and console output
                log.info(
                    "Initializing headless event collection",
                    event_log_path=str(self.event_log_path),
                )
                self.event_collector = EventCollector()
                self.json_logger = JSONEventLogger(self.event_log_path)
                self.event_collector.subscribe(self.json_logger.log_event)

                # Initialize console formatter for headless mode
                self.console_formatter = ConsoleEventFormatter(
                    console=self.console,
                    use_color=self.use_color,
                    use_ascii=self.use_ascii,
                    verbose=self.verbose,
                    verbose_format=self.verbose_format,
                )

                # Subscribe console formatter to events
                self.event_collector.subscribe(self._print_event_to_console)

                # Print startup banner showing monitoring info
                # We'll print this after repositories are initialized
            else:
                # No event collection configured
                log.debug("No event collection configured")

            # Initialize helper managers
            self.repository_manager = RepositoryManager(
                self.repo_states,
                self.repo_engines,
                self._post_tui_state_update,
                self.event_collector,
            )
            self.monitoring_coordinator = MonitoringCoordinator(
                self.event_queue, self.config_path, self.repo_states
            )

            enabled_repos = await self.repository_manager.initialize_repositories(self.config, tui)
            active_repositories.set(len(enabled_repos))

            # Print startup banner in headless mode
            if self.console_formatter:
                self.console_formatter.print_startup_banner(
                    repo_count=len(enabled_repos),
                    event_log_path=self.event_log_path,
                    app_log_path=self.app_log_path,
                )

                # Start timer update task for headless mode
                self.timer_update_task = asyncio.create_task(self._timer_update_loop())
                log.info("Started timer update task for headless mode")

            # Initialize status manager for repository status updates
            self.status_manager = StatusManager(
                self.repo_states, self.repo_engines, self.config, self._post_tui_state_update
            )

            action_handler = ActionHandler(
                self.config, self.repo_states, self.repo_engines, tui, self.event_collector
            )
            self.event_processor = EventProcessor(
                config=self.config,
                event_queue=self.event_queue,
                shutdown_event=self.shutdown_event,
                action_handler=action_handler,
                repo_states=self.repo_states,
                repo_engines=self.repo_engines,
                tui=tui,
                config_reload_callback=self.reload_config,
                event_collector=self.event_collector,
            )

            # Setup monitoring services
            self.monitoring_coordinator.setup_monitoring(self.config, enabled_repos, tui)
            self.monitoring_coordinator.setup_config_watcher(tui)

            # Start monitoring services
            services_started = await self.monitoring_coordinator.start_services(tui)
            if not services_started:
                log.error("Failed to start one or more monitoring services")
                return

            log.info("Starting event processor task.")
            processor_task = asyncio.create_task(self.event_processor.run())
            await processor_task

        except asyncio.CancelledError:
            log.warning("Orchestrator task was cancelled.")
        except Exception:
            orchestrator_errors.inc()
            log.critical("Orchestrator run failed with an unhandled exception.", exc_info=True)
        finally:
            log.info("Orchestrator entering cleanup phase.")

            # Cancel timer update task
            if self.timer_update_task and not self.timer_update_task.done():
                self.timer_update_task.cancel()
                try:
                    await asyncio.wait_for(self.timer_update_task, timeout=2.0)
                except (TimeoutError, asyncio.CancelledError):
                    log.debug("Timer update task cleanup completed")

            # Cancel processor task first
            if processor_task and not processor_task.done():
                processor_task.cancel()
                try:
                    await asyncio.wait_for(processor_task, timeout=5.0)
                except (TimeoutError, asyncio.CancelledError):
                    log.warning("Processor task cleanup timed out or was cancelled.")

            # Clean up all repository timers
            if self.repository_manager:
                await self.repository_manager.cleanup_repository_timers()

            # Stop monitoring services
            if self.monitoring_coordinator:
                await self.monitoring_coordinator.stop_services()

            # Close JSON logger
            if self.json_logger:
                self.json_logger.close()

            # Reset metrics
            active_repositories.set(0)
            log.info("Orchestrator cleanup complete.")

    @property
    def _is_paused(self) -> bool:
        """Check if monitoring is currently paused."""
        return self.monitoring_coordinator._is_paused if self.monitoring_coordinator else False

    @property
    def _is_suspended(self) -> bool:
        """Check if monitoring is currently suspended."""
        return self.monitoring_coordinator._is_suspended if self.monitoring_coordinator else False

    def pause_monitoring(self) -> None:
        if self.monitoring_coordinator:
            self.monitoring_coordinator.pause_monitoring()
        self._post_tui_state_update()

    def suspend_monitoring(self) -> None:
        if self.monitoring_coordinator:
            self.monitoring_coordinator.suspend_monitoring()
        self._post_tui_state_update()

    def resume_monitoring(self) -> None:
        if self.monitoring_coordinator and self.config:
            tui = TUIInterface(self.app)
            self.monitoring_coordinator.resume_monitoring(self.config, tui)
        self._post_tui_state_update()

    def toggle_repository_pause(self, repo_id: str) -> bool:
        if self.repository_manager:
            result = self.repository_manager.toggle_repository_pause(repo_id)
            self._post_tui_state_update()
            return result
        return False

    async def toggle_repository_stop(self, repo_id: str) -> bool:
        """Toggle stop state for a repository - delegate to repository manager."""
        if self.repository_manager and self.config and self.monitoring_coordinator:
            return await self.repository_manager.toggle_repository_stop(
                repo_id, self.config, self.monitoring_coordinator.monitor_service
            )
        return False

    def acknowledge_circuit_breaker(self, repo_id: str) -> bool:
        """Acknowledge and reset circuit breaker for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            True if circuit breaker was successfully acknowledged, False otherwise
        """
        if not self.repository_manager:
            log.warning("Cannot acknowledge circuit breaker: repository manager not initialized")
            return False

        # Get the repository state
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            log.warning("Cannot acknowledge circuit breaker: repository not found", repo_id=repo_id)
            return False

        # Reset the circuit breaker via the circuit breaker service
        if self.event_processor and hasattr(self.event_processor, "_circuit_breaker"):
            self.event_processor._circuit_breaker.acknowledge_circuit_breaker(repo_state, auto_recovery=False)
            log.info(
                "Circuit breaker acknowledged",
                repo_id=repo_id,
                reason=repo_state.circuit_breaker_reason,
            )
            self._post_tui_state_update()
            return True

        log.warning("Cannot acknowledge circuit breaker: event processor not available")
        return False

    def _post_tui_state_update(self):
        if self.app:
            tui = TUIInterface(self.app)
            tui.post_state_update(self.repo_states)

    async def reload_config(self) -> bool:
        """Reload configuration - delegate to monitoring coordinator."""
        if not self.monitoring_coordinator or not self.repository_manager:
            return False

        tui = TUIInterface(self.app)

        def initialize_repositories_callback(config: SupsrcConfig, tui_interface: TUIInterface) -> Any:
            return asyncio.create_task(self.repository_manager.initialize_repositories(config, tui_interface))

        def cleanup_timers_callback() -> Any:
            return asyncio.create_task(self.repository_manager.cleanup_repository_timers())

        def update_processor_config_callback(new_config: SupsrcConfig) -> None:
            self.config = new_config
            if self.event_processor:
                self.event_processor.config = new_config

        success = await self.monitoring_coordinator.reload_config(
            tui,
            initialize_repositories_callback,
            cleanup_timers_callback,
            update_processor_config_callback,
        )

        if success:
            # Update metrics after successful reload
            enabled_repos = (
                [
                    repo_id
                    for repo_id, repo in self.config.repositories.items()
                    if repo.enabled and repo._path_valid
                ]
                if self.config
                else []
            )
            active_repositories.set(len(enabled_repos))

        self._post_tui_state_update()
        return success

    async def resume_repository_monitoring(self, repo_id: str) -> bool:
        """Resume repository monitoring - delegate to repository manager."""
        if self.repository_manager:
            return await self.repository_manager.resume_repository_monitoring(repo_id)
        return False

    async def get_repository_details(self, repo_id: str) -> dict[str, Any]:
        if self.repository_manager and self.config:
            return await self.repository_manager.get_repository_details(repo_id, self.config)
        return {"error": "Repository manager not available."}

    def _print_event_to_console(self, event: Any) -> None:
        """Print events to console in headless mode."""
        if self.console_formatter:
            try:
                self.console_formatter.format_and_print(event)
            except Exception as e:
                log.debug(
                    "Failed to print event to console",
                    error=str(e),
                    event_type=type(event).__name__,
                )

    def set_repo_refreshing_status(self, repo_id: str, is_refreshing: bool) -> None:
        """Set the refreshing status for a repository."""
        if self.repository_manager:
            self.repository_manager.set_repo_refreshing_status(repo_id, is_refreshing, self.status_manager)

    async def refresh_repository_status(self, repo_id: str) -> bool:
        """Refresh the status and statistics for a specific repository."""
        if self.repository_manager:
            return await self.repository_manager.refresh_repository_status(repo_id, self.status_manager)
        return False

    async def _timer_update_loop(self) -> None:
        """Background task to emit timer update events for headless mode display."""
        from supsrc.events.timer import TimerUpdateEvent

        log.info("Timer update loop starting")
        try:
            while True:
                await asyncio.sleep(1.0)  # Update every second

                if not self.event_collector:
                    continue

                # Update and emit timer events for each repository
                for repo_id, repo_state in self.repo_states.items():
                    # Update the timer countdown
                    repo_state.update_timer_countdown()

                    # Only emit if there's an active timer
                    if repo_state.timer_seconds_left is not None:
                        seconds_left = repo_state.timer_seconds_left
                        last_emitted = self._last_emitted_timers.get(repo_id, -1)

                        # Emit based on smart intervals:
                        # - Every 10s when > 10s remaining
                        # - Every 5s when between 10-20s
                        # - Every second when ≤ 10s
                        should_emit = False

                        if seconds_left <= 10:
                            # Final countdown: emit every second
                            should_emit = seconds_left != last_emitted
                        elif seconds_left <= 20:
                            # Mid countdown: emit every 5 seconds
                            should_emit = seconds_left % 5 == 0 and seconds_left != last_emitted
                        else:
                            # Early countdown: emit every 10 seconds
                            should_emit = seconds_left % 10 == 0 and seconds_left != last_emitted

                        if should_emit:
                            self._last_emitted_timers[repo_id] = seconds_left

                            timer_event = TimerUpdateEvent(
                                description=f"Timer: {seconds_left}s remaining",
                                repo_id=repo_id,
                                seconds_remaining=seconds_left,
                                total_seconds=repo_state._timer_total_seconds or seconds_left,
                                rule_name=repo_state.active_rule_description,
                            )

                            self.event_collector.emit(timer_event)
                            log.debug(
                                "Emitted timer update event",
                                repo_id=repo_id,
                                seconds_left=seconds_left,
                            )
                    elif repo_id in self._last_emitted_timers:
                        # Timer finished or cancelled, clear tracking
                        del self._last_emitted_timers[repo_id]

        except asyncio.CancelledError:
            log.info("Timer update loop cancelled")
            raise
        except Exception as e:
            log.error("Timer update loop error", error=str(e), exc_info=True)


# 🔼⚙️🔚
