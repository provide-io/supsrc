#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Monitoring coordination functionality for the WatchOrchestrator.
Handles filesystem monitoring setup, control, and configuration watching."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from provide.foundation.logger import get_logger

# Import foundation metrics with fallback
try:
    from provide.foundation.metrics import config_reloads  # type: ignore[attr-defined]
except ImportError:
    # Fallback for when foundation metrics is not available
    class MockCounter:
        def inc(self) -> None:
            pass

    config_reloads = MockCounter()
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from supsrc.config import SupsrcConfig, load_config
from supsrc.exceptions import ConfigurationError, MonitoringSetupError
from supsrc.monitor import MonitoredEvent, MonitoringService
from supsrc.state import RepositoryStatus
from supsrc.state.manager import StateManager

if TYPE_CHECKING:
    from supsrc.runtime.tui_interface import TUIInterface

log = get_logger("runtime.monitoring_coordinator")


class MonitoringCoordinator:
    """Manages monitoring services, configuration watching, and monitoring control."""

    def __init__(
        self,
        event_queue: asyncio.Queue[MonitoredEvent],
        config_path: Path,
        repo_states: dict[str, Any],
        state_manager: StateManager | None = None,
    ) -> None:
        self.event_queue = event_queue
        self.config_path = config_path
        self.repo_states = repo_states
        self.state_manager = state_manager
        self.monitor_service: MonitoringService | None = None
        self.config_observer: Any = None  # Observer type annotation causes issues
        self._is_paused = False
        self._is_suspended = False
        self._log = log.bind(coordinator_id=id(self))
        self._log.debug("MonitoringCoordinator initialized")

    def setup_monitoring(
        self, config: SupsrcConfig, enabled_repo_ids: list[str], tui: TUIInterface
    ) -> MonitoringService | None:
        """Set up filesystem monitoring for enabled repositories."""
        if not enabled_repo_ids:
            return None

        self._log.info("Setting up filesystem monitoring...")
        tui.post_log_update(None, "INFO", "Setting up filesystem monitoring...")
        service = MonitoringService(self.event_queue)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._log.critical("Cannot get running event loop during monitoring setup.")
            return None

        for repo_id in enabled_repo_ids:
            try:
                service.add_repository(repo_id, config.repositories[repo_id], loop)
            except MonitoringSetupError as e:
                self._log.error("Failed to add repo to monitor", repo_id=repo_id, error=str(e))
                if self.repo_states.get(repo_id):
                    self.repo_states[repo_id].update_status(RepositoryStatus.ERROR, "Monitor setup failed")
                    tui.post_log_update(repo_id, "ERROR", f"Monitoring setup failed: {e}")

                    # Emit error event for monitor setup failure
                    if hasattr(tui.app, "event_collector"):
                        from supsrc.events.system import ErrorEvent

                        monitor_error_event = ErrorEvent(
                            description=f"File monitoring setup failed: {e!s}",
                            source="monitor",
                            error_type="MonitorSetupFailed",
                            repo_id=repo_id,
                        )
                        tui.app.event_collector.emit(monitor_error_event)

        self.monitor_service = service
        return service

    def setup_config_watcher(self, tui: TUIInterface) -> None:
        """Set up file watcher for configuration file changes."""
        loop = asyncio.get_running_loop()

        class ConfigChangeHandler(FileSystemEventHandler):
            def __init__(self, coordinator_ref: MonitoringCoordinator):
                self._coordinator = coordinator_ref
                self._config_path_str = str(self._coordinator.config_path.resolve())

            def on_modified(self, event: FileSystemEvent):
                if str(Path(event.src_path).resolve()) == self._config_path_str:
                    log.info("Configuration file modified, queueing reload event.")
                    monitored_event = MonitoredEvent(
                        repo_id="__config__",
                        event_type="modified",
                        src_path=self._coordinator.config_path,
                        is_directory=False,
                    )
                    loop.call_soon_threadsafe(self._coordinator.event_queue.put_nowait, monitored_event)

        try:
            self.config_observer = Observer()
            handler = ConfigChangeHandler(self)
            watch_dir = str(self.config_path.parent)
            self.config_observer.schedule(handler, watch_dir, recursive=False)
            self._log.info("Configuration file watcher scheduled", path=watch_dir)
            tui.post_log_update(None, "DEBUG", f"Watching config in: {watch_dir}")
        except Exception as e:
            self._log.error("Failed to set up configuration file watcher", error=str(e), exc_info=True)
            self.config_observer = None

    def pause_monitoring(self) -> None:
        """Pause all event processing."""
        self._log.info("Pausing all event processing.")
        self._is_paused = True
        for state in self.repo_states.values():
            if not state.is_stopped:
                state.is_paused = True
                state._update_display_emoji()

    def suspend_monitoring(self) -> None:
        """Suspend filesystem monitoring service."""
        self._log.info("Suspending filesystem monitoring service.")
        self._is_suspended = True
        if self.monitor_service and self.monitor_service.is_running:
            asyncio.create_task(self.monitor_service.stop())  # noqa: RUF006

    def resume_monitoring(self, config: SupsrcConfig, tui: TUIInterface) -> None:
        """Resume event processing and monitoring."""
        self._log.info("Resuming event processing and monitoring.")
        self._is_paused = False
        self._is_suspended = False

        if config and self.monitor_service and not self.monitor_service.is_running:
            self._log.info("Restarting suspended monitoring service...")
            enabled_repos = [
                repo_id for repo_id, repo in config.repositories.items() if repo.enabled and repo._path_valid
            ]
            self.monitor_service = self.setup_monitoring(config, enabled_repos, tui)
            if self.monitor_service:
                self.monitor_service.start()

        for state in self.repo_states.values():
            if state.is_paused:
                state.is_paused = False
                state._update_display_emoji()

    async def reload_config(
        self,
        tui: TUIInterface,
        initialize_repositories_callback: Callable[[Any, Any], Any],
        cleanup_timers_callback: Callable[[], Any],
        update_processor_config_callback: Callable[[Any], None],
    ) -> bool:
        """Reload configuration and restart monitoring."""
        config_reloads.inc()
        self._log.info("Reloading configuration...")
        self._is_paused = True
        tui.post_log_update(None, "INFO", "Pausing all monitoring for config reload...")

        if self.monitor_service and self.monitor_service.is_running:
            await self.monitor_service.stop()
            self.monitor_service.clear_handlers()

        try:
            await asyncio.sleep(1)
            new_config = await asyncio.to_thread(load_config, self.config_path)

            # Update processor config if callback provided
            if update_processor_config_callback:
                update_processor_config_callback(new_config)

            # Clean up timers before clearing states
            if cleanup_timers_callback:
                await cleanup_timers_callback()

            self.repo_states.clear()
            enabled_repos = await initialize_repositories_callback(new_config, tui)

            if not enabled_repos:
                self._log.warning("No enabled repositories after reload.")
                tui.post_log_update(None, "WARNING", "Config reloaded, but no repositories are enabled.")
                return True

            self.monitor_service = self.setup_monitoring(new_config, enabled_repos, tui)
            if self.monitor_service:
                self.monitor_service.start()
                tui.post_log_update(None, "INFO", "Monitoring resumed with new configuration.")

            self._log.info("Configuration reloaded and monitoring restarted.")
            return True
        except ConfigurationError as e:
            self._log.error("Failed to reload configuration", error=str(e), exc_info=True)
            tui.post_log_update(None, "ERROR", f"Config reload failed: {e}")
            return False
        finally:
            self._is_paused = False

    async def start_services(self, tui: TUIInterface) -> bool:
        """Start monitoring and config watcher services."""
        if self.monitor_service:
            try:
                self.monitor_service.start()
                if not self.monitor_service.is_running:
                    self._log.error("Monitoring service for repositories failed to start silently.")
                    tui.post_log_update(None, "ERROR", "Filesystem monitoring service failed to start.")
                    return False
            except Exception as e:
                self._log.critical(
                    "Failed to start filesystem monitoring service", error=str(e), exc_info=True
                )
                tui.post_log_update(None, "CRITICAL", f"FATAL: Filesystem monitor failed: {e}")
                return False

        if self.config_observer:
            try:
                self.config_observer.start()
            except Exception as e:
                self._log.critical("Failed to start configuration file watcher", error=str(e), exc_info=True)
                tui.post_log_update(None, "CRITICAL", f"FATAL: Config watcher failed to start: {e}")
                return False

        return True

    async def stop_services(self) -> None:
        """Stop monitoring and config watcher services."""
        # Stop monitoring service
        if self.monitor_service and self.monitor_service.is_running:
            await self.monitor_service.stop()

        # Stop config observer
        if self.config_observer and self.config_observer.is_alive():
            self.config_observer.stop()
            self.config_observer.join(timeout=2.0)
            if self.config_observer.is_alive():
                self._log.warning("Config observer thread did not stop within timeout.")

    @property
    def is_paused(self) -> bool:
        """Check if monitoring is currently paused."""
        # Check both internal pause state and external state manager
        if self._is_paused:
            return True

        if self.state_manager:
            return self.state_manager.is_paused(repo_id=None)  # Check global pause

        return False

    @property
    def is_suspended(self) -> bool:
        """Check if monitoring is currently suspended."""
        return self._is_suspended


# 🔼⚙️🔚
