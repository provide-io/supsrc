# src/supsrc/runtime/orchestrator.py

"""
High-level coordinator for the supsrc watch process.
Manages lifecycle of all runtime components.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

# Add Foundation error handling and metrics patterns
from provide.foundation.errors import with_error_handling
from provide.foundation.logger import get_logger
from provide.foundation.metrics import counter, gauge
from rich.console import Console

from supsrc.config import SupsrcConfig, load_config
from supsrc.exceptions import ConfigurationError
from supsrc.monitor import MonitoredEvent
from supsrc.protocols import RepositoryEngine
from supsrc.state import RepositoryState

from .action_handler import ActionHandler
from .event_processor import EventProcessor
from .monitoring_coordinator import MonitoringCoordinator
from .repository_manager import RepositoryManager
from .status_manager import StatusManager
from .tui_interface import TUIInterface

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


log = get_logger("runtime.orchestrator")
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]
RULE_EMOJI_MAP: dict[str, str] = {
    "supsrc.rules.inactivity": "⏳",
    "supsrc.rules.save_count": "💾",
    "supsrc.rules.manual": "✋",
    "default": "⚙️",
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
    ):
        self.config_path = config_path
        self.shutdown_event = shutdown_event
        self.app = app
        self.console = console
        self.event_queue: asyncio.Queue[MonitoredEvent] = asyncio.Queue()
        self.repo_states: RepositoryStatesMap = {}
        self.repo_engines: dict[str, RepositoryEngine] = {}
        self.event_processor: EventProcessor | None = None
        self.config: SupsrcConfig | None = None
        self.status_manager: StatusManager | None = None

        # Initialize helper managers
        self.repository_manager: RepositoryManager | None = None
        self.monitoring_coordinator: MonitoringCoordinator | None = None

    @with_error_handling(
        log_errors=True, context_provider=lambda: {"component": "orchestrator", "method": "run"}
    )
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

            # Initialize helper managers
            self.repository_manager = RepositoryManager(
                self.repo_states, self.repo_engines, self._post_tui_state_update
            )
            self.monitoring_coordinator = MonitoringCoordinator(
                self.event_queue, self.config_path, self.repo_states
            )

            enabled_repos = await self.repository_manager.initialize_repositories(self.config, tui)
            active_repositories.set(len(enabled_repos))

            # Initialize status manager for repository status updates
            self.status_manager = StatusManager(
                self.repo_states, self.repo_engines, self.config, self._post_tui_state_update
            )

            action_handler = ActionHandler(self.config, self.repo_states, self.repo_engines, tui)
            self.event_processor = EventProcessor(
                self,
                self.config,
                self.event_queue,
                self.shutdown_event,
                action_handler,
                self.repo_states,
                tui,
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

            # Reset metrics
            active_repositories.set(0)
            log.info("Orchestrator cleanup complete.")

    def pause_monitoring(self) -> None:
        if self.monitoring_coordinator:
            self.monitoring_coordinator.pause_monitoring()
        self._post_tui_state_update()

    def suspend_monitoring(self) -> None:
        if self.monitoring_coordinator:
            self.monitoring_coordinator.suspend_monitoring()

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

    def _post_tui_state_update(self):
        if self.app:
            tui = TUIInterface(self.app)
            tui.post_state_update(self.repo_states)

    async def reload_config(self) -> bool:
        """Reload configuration - delegate to monitoring coordinator."""
        if not self.monitoring_coordinator or not self.repository_manager:
            return False

        tui = TUIInterface(self.app)

        def initialize_repositories_callback(
            config: SupsrcConfig, tui_interface: TUIInterface
        ) -> Any:
            return asyncio.create_task(
                self.repository_manager.initialize_repositories(config, tui_interface)
            )

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

    def set_repo_refreshing_status(self, repo_id: str, is_refreshing: bool) -> None:
        """Set the refreshing status for a repository."""
        if self.repository_manager:
            self.repository_manager.set_repo_refreshing_status(
                repo_id, is_refreshing, self.status_manager
            )

    async def refresh_repository_status(self, repo_id: str) -> bool:
        """Refresh the status and statistics for a specific repository."""
        if self.repository_manager:
            return await self.repository_manager.refresh_repository_status(
                repo_id, self.status_manager
            )
        return False
