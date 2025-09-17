# src/supsrc/runtime/orchestrator.py

"""
High-level coordinator for the supsrc watch process.
Manages lifecycle of all runtime components.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import structlog

# Add Foundation error handling and metrics patterns
from provide.foundation.errors import with_error_handling
from provide.foundation.metrics import counter, gauge
from rich.console import Console
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import SupsrcConfig, load_config
from supsrc.engines.git import GitEngine, GitRepoSummary
from supsrc.exceptions import ConfigurationError, MonitoringSetupError
from supsrc.monitor import MonitoredEvent, MonitoringService
from supsrc.protocols import RepositoryEngine
from supsrc.state import RepositoryState, RepositoryStatus

from .action_handler import ActionHandler
from .event_processor import EventProcessor
from .monitoring_coordinator import MonitoringCoordinator
from .repository_manager import RepositoryManager
from .status_manager import StatusManager
from .tui_interface import TUIInterface

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


log: StructLogger = structlog.get_logger("runtime.orchestrator")
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
            self.monitoring_coordinator.setup_monitoring(
                self.config, enabled_repos, tui
            )
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
        repo_state = self.repo_states.get(repo_id)
        if not self.config or not (repo_config := self.config.repositories.get(repo_id)):
            log.warning("Attempted to toggle stop on non-existent repo config", repo_id=repo_id)
            return False

        if not repo_state:
            log.warning("Attempted to toggle stop on non-existent repo state", repo_id=repo_id)
            return False

        repo_state.is_stopped = not repo_state.is_stopped

        if repo_state.is_stopped:
            log.info("Stopping monitoring for repository", repo_id=repo_id)
            if self.monitor_service:
                self.monitor_service.unschedule_repository(repo_id)
        else:
            log.info("Resuming monitoring for stopped repository", repo_id=repo_id)
            if self.monitor_service:
                try:
                    loop = asyncio.get_running_loop()
                    self.monitor_service.add_repository(repo_id, repo_config, loop)
                    if repo_state.status == RepositoryStatus.ERROR:
                        repo_state.reset_after_action()
                except Exception as e:
                    log.error(
                        "Failed to re-add repository to monitor",
                        repo_id=repo_id,
                        error=str(e),
                        exc_info=True,
                    )
                    repo_state.update_status(
                        RepositoryStatus.ERROR, f"Failed to resume monitoring: {e}"
                    )
                    repo_state.is_stopped = True
                    return False

        repo_state._update_display_emoji()
        self._post_tui_state_update()
        return True

    def _post_tui_state_update(self):
        if self.app:
            tui = TUIInterface(self.app)
            tui.post_state_update(self.repo_states)

    async def reload_config(self) -> bool:
        config_reloads.inc()
        log.info("Reloading configuration...")
        self._is_paused = True
        tui = TUIInterface(self.app)
        tui.post_log_update(None, "INFO", "Pausing all monitoring for config reload...")
        self._post_tui_state_update()

        if self.monitor_service and self.monitor_service.is_running:
            await self.monitor_service.stop()
            self.monitor_service.clear_handlers()

        try:
            await asyncio.sleep(1)
            new_config = await asyncio.to_thread(load_config, self.config_path)
            self.config = new_config
            if self.event_processor:
                self.event_processor.config = new_config

            # Clean up timers before clearing states
            await self._cleanup_repository_timers()

            self.repo_states.clear()
            self.repo_engines.clear()
            enabled_repos = await self._initialize_repositories(self.config, tui)
            active_repositories.set(len(enabled_repos))

            if not enabled_repos:
                log.warning("No enabled repositories after reload.")
                tui.post_log_update(
                    None, "WARNING", "Config reloaded, but no repositories are enabled."
                )
                active_repositories.set(0)
                return True

            self.monitor_service = self._setup_monitoring(self.config, enabled_repos, tui)
            if self.monitor_service:
                self.monitor_service.start()
                tui.post_log_update(None, "INFO", "Monitoring resumed with new configuration.")

            log.info("Configuration reloaded and monitoring restarted.")
            return True
        except ConfigurationError as e:
            log.error("Failed to reload configuration", error=str(e), exc_info=True)
            tui.post_log_update(None, "ERROR", f"Config reload failed: {e}")
            return False
        finally:
            self._is_paused = False
            self._post_tui_state_update()

    async def _initialize_repositories(self, config: SupsrcConfig, tui: TUIInterface) -> list[str]:
        log.info("Initializing repositories...")
        tui.post_log_update(None, "INFO", "Initializing repositories...")
        enabled_repo_ids = []

        for repo_id, repo_config in config.repositories.items():
            init_log = log.bind(repo_id=repo_id)
            if not repo_config.enabled or not repo_config._path_valid:
                init_log.info("Skipping disabled/invalid repo")
                continue

            repo_state = RepositoryState(repo_id=repo_id)
            self.repo_states[repo_id] = repo_state

            try:
                engine_type = repo_config.repository.get("type", "supsrc.engines.git")
                init_log.debug("Attempting to load engine", engine_type=engine_type)
                if engine_type == "supsrc.engines.git":
                    self.repo_engines[repo_id] = GitEngine()
                else:
                    raise NotImplementedError(f"Engine '{engine_type}' not supported.")
                init_log.debug("Engine loaded successfully")

                rule_type_str = getattr(repo_config.rule, "type", "default")
                repo_state.rule_emoji = RULE_EMOJI_MAP.get(rule_type_str, RULE_EMOJI_MAP["default"])
                repo_state.rule_dynamic_indicator = (
                    rule_type_str.split(".")[-1].replace("_", " ").capitalize()
                )

                engine = self.repo_engines[repo_id]
                if hasattr(engine, "get_summary"):
                    init_log.debug("Getting initial repository summary")
                    summary = cast(GitRepoSummary, await engine.get_summary(repo_config.path))
                    if summary.head_commit_hash:
                        repo_state.last_commit_short_hash = summary.head_commit_hash[:7]
                        repo_state.last_commit_message_summary = summary.head_commit_message_summary
                        if (
                            hasattr(summary, "head_commit_timestamp")
                            and summary.head_commit_timestamp
                        ):
                            repo_state.last_commit_timestamp = summary.head_commit_timestamp
                        msg = (
                            f"HEAD at {summary.head_ref_name} ({repo_state.last_commit_short_hash})"
                        )
                        init_log.info(msg)
                        tui.post_log_update(repo_id, "INFO", msg)
                    elif summary.is_empty or summary.head_ref_name == "UNBORN":
                        init_log.info("Repo is empty or unborn.")
                        tui.post_log_update(repo_id, "INFO", "Repo is empty or unborn.")
                    elif summary.head_ref_name == "ERROR":
                        init_log.warning(
                            "Failed to get repo summary.",
                            details=summary.head_commit_message_summary,
                        )
                        repo_state.update_status(
                            RepositoryStatus.ERROR,
                            f"Init failed: {summary.head_commit_message_summary}",
                        )
                    else:
                        init_log.warning(
                            "Could not determine initial HEAD commit.", summary_details=summary
                        )

                # Load initial repository statistics
                init_log.debug("Loading initial repository statistics")
                try:
                    status_result = await engine.get_status(
                        repo_state, repo_config.repository, config.global_config, repo_config.path
                    )
                    if status_result.success:
                        repo_state.total_files = status_result.total_files or 0
                        repo_state.changed_files = status_result.changed_files or 0
                        repo_state.added_files = status_result.added_files or 0
                        repo_state.deleted_files = status_result.deleted_files or 0
                        repo_state.modified_files = status_result.modified_files or 0
                        repo_state.has_uncommitted_changes = not status_result.is_clean
                        repo_state.current_branch = status_result.current_branch
                        init_log.debug(
                            "Repository statistics loaded",
                            total_files=repo_state.total_files,
                            changed_files=repo_state.changed_files,
                        )
                    else:
                        init_log.warning(
                            "Failed to load initial statistics", error=status_result.message
                        )
                except Exception as stats_error:
                    init_log.warning("Error loading initial statistics", error=str(stats_error))

                enabled_repo_ids.append(repo_id)
            except Exception as e:
                init_log.error("Failed to initialize repository", error=str(e), exc_info=True)
                repo_state.update_status(RepositoryStatus.ERROR, f"Initialization failed: {e}")
                continue

        tui.post_state_update(self.repo_states)
        log.info(f"Initialized {len(enabled_repo_ids)} repositories.")
        return enabled_repo_ids

    def _setup_monitoring(
        self, config: SupsrcConfig, enabled_repo_ids: list[str], tui: TUIInterface
    ) -> MonitoringService | None:
        if not enabled_repo_ids:
            return None

        log.info("Setting up filesystem monitoring...")
        tui.post_log_update(None, "INFO", "Setting up filesystem monitoring...")
        service = MonitoringService(self.event_queue)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.critical("Cannot get running event loop during monitoring setup.")
            return None

        for repo_id in enabled_repo_ids:
            try:
                service.add_repository(repo_id, config.repositories[repo_id], loop)
            except MonitoringSetupError as e:
                log.error("Failed to add repo to monitor", repo_id=repo_id, error=str(e))
                if self.repo_states.get(repo_id):
                    self.repo_states[repo_id].update_status(
                        RepositoryStatus.ERROR, "Monitor setup failed"
                    )
                    tui.post_log_update(repo_id, "ERROR", f"Monitoring setup failed: {e}")

        tui.post_state_update(self.repo_states)
        return service

    async def resume_repository_monitoring(self, repo_id: str) -> bool:
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            return False

        if repo_state.is_paused:
            repo_state.is_paused = False
            repo_state.pause_until = None
            log.info(f"Repository {repo_id} unpaused.")

        if repo_state.is_stopped:
            success = await self.toggle_repository_stop(repo_id)
            if not success:
                log.error(f"Failed to unstop {repo_id} during resume.")
                return False
            log.info(f"Repository {repo_id} unstopped.")

        self._post_tui_state_update()
        return True

    async def get_repository_details(self, repo_id: str) -> dict[str, Any]:
        if self.repository_manager and self.config:
            return await self.repository_manager.get_repository_details(repo_id, self.config)
        return {"error": "Repository manager not available."}

    async def _cleanup_repository_timers(self) -> None:
        """Clean up all repository timers to prevent resource leaks."""
        log.info("Cleaning up repository timers", repo_count=len(self.repo_states))
        cleanup_count = 0

        for repo_id, repo_state in self.repo_states.items():
            try:
                # Cancel any inactivity timers
                if (
                    repo_state.inactivity_timer_handle
                    and not repo_state.inactivity_timer_handle.cancelled()
                ):
                    repo_state.inactivity_timer_handle.cancel()
                    cleanup_count += 1

                # Cancel any debounce timers
                if (
                    repo_state.debounce_timer_handle
                    and not repo_state.debounce_timer_handle.cancelled()
                ):
                    repo_state.debounce_timer_handle.cancel()
                    cleanup_count += 1

                # Reset timer-related state
                repo_state.inactivity_timer_handle = None
                repo_state.debounce_timer_handle = None
                repo_state._timer_total_seconds = None
                repo_state._timer_start_time = None
                repo_state.timer_seconds_left = None

            except Exception as e:
                log.warning(
                    "Error cleaning up timers for repository", repo_id=repo_id, error=str(e)
                )

        log.info("Repository timer cleanup complete", timers_cancelled=cleanup_count)

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
