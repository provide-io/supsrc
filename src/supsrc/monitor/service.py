#
# supsrc/monitor/service.py
#
"""
Manages the watchdog observer thread and repository event handlers.
"""

import asyncio
from pathlib import Path
from typing import Dict

import structlog
from watchdog.observers import Observer

# Use relative imports
from ..config.models import RepositoryConfig
from ..exceptions import MonitoringSetupError
from .events import MonitoredEvent
from .handler import SupsrcEventHandler

log = structlog.get_logger("monitor.service")


class MonitoringService:
    """
    Manages the filesystem monitoring using watchdog.

    Creates and manages event handlers for each repository and runs the
    watchdog observer in a separate thread.
    """

    def __init__(self, event_queue: asyncio.Queue[MonitoredEvent]):
        """
        Initializes the MonitoringService.

        Args:
            event_queue: The asyncio Queue where filtered events will be placed.
        """
        self._event_queue = event_queue
        self._observer = Observer()
        self._handlers: Dict[str, SupsrcEventHandler] = {}
        self._logger = log
        self._is_running = False

    def add_repository(
        self, repo_id: str, repo_config: RepositoryConfig
    ) -> None:
        """
        Adds a repository to be monitored.

        Creates an event handler and schedules it with the observer.

        Args:
            repo_id: Unique identifier for the repository.
            repo_config: The configuration object for the repository.

        Raises:
            MonitoringSetupError: If the repository path is invalid or scheduling fails.
        """
        if not repo_config.enabled or not repo_config._path_valid:
            self._logger.warning(
                "Skipping disabled or invalid repository",
                repo_id=repo_id,
                path=str(repo_config.path),
                enabled=repo_config.enabled,
                path_valid=repo_config._path_valid,
            )
            return

        repo_path = repo_config.path
        if not repo_path.is_dir():
            # This should have been caught by config loading, but double-check
            raise MonitoringSetupError(
                f"Repository path is not a valid directory",
                repo_id=repo_id,
                path=str(repo_path),
            )

        self._logger.info("Adding repository to monitor", repo_id=repo_id, path=str(repo_path))
        handler = SupsrcEventHandler(
            repo_id=repo_id,
            repo_path=repo_path,
            event_queue=self._event_queue,
        )
        self._handlers[repo_id] = handler

        try:
            # Schedule monitoring recursively for the repository path
            self._observer.schedule(handler, str(repo_path), recursive=True)
            self._logger.debug("Scheduled handler with observer", repo_id=repo_id)
        except Exception as e:
            # Catch potential OS errors during scheduling
            self._logger.error(
                "Failed to schedule monitoring for repository",
                repo_id=repo_id,
                path=str(repo_path),
                error=str(e),
                exc_info=True,
            )
            # Remove handler if scheduling failed
            if repo_id in self._handlers:
                del self._handlers[repo_id]
            raise MonitoringSetupError(
                f"Failed to schedule monitoring: {e}",
                repo_id=repo_id,
                path=str(repo_path),
            ) from e

    def start(self) -> None:
        """Starts the watchdog observer thread."""
        if not self._handlers:
             self._logger.warning("No repositories configured or added for monitoring. Observer not started.")
             return

        if self._is_running:
            self._logger.warning("Monitoring service already running.")
            return

        try:
            self._observer.start()
            self._is_running = True
            self._logger.info("Monitoring service started", num_handlers=len(self._handlers))
        except Exception as e:
            self._logger.critical("Failed to start monitoring observer", error=str(e), exc_info=True)
            # Potentially re-raise or handle more gracefully depending on requirements
            raise MonitoringError(f"Failed to start observer thread: {e}") from e


    def stop(self) -> None:
        """Stops the watchdog observer thread gracefully."""
        if not self._is_running:
            self._logger.info("Monitoring service already stopped.")
            return

        self._logger.info("Stopping monitoring service...")
        try:
            self._observer.stop()
            # Wait for the observer thread to finish
            self._observer.join(timeout=5.0) # Add a timeout
            if self._observer.is_alive():
                 self._logger.warning("Observer thread did not stop within timeout.")
            else:
                 self._logger.info("Observer thread stopped.")

        except Exception as e:
            self._logger.error("Error stopping monitoring observer", error=str(e), exc_info=True)
        finally:
             self._is_running = False
             self._logger.info("Monitoring service stopped.")

    @property
    def is_running(self) -> bool:
        """Returns True if the observer thread is currently active."""
        return self._is_running

# 🔼⚙️
