#
# src/supsrc/monitor/service.py
#
"""
Manages the watchdog observer thread and repository event handlers.
"""

import asyncio
import time
import sys
from pathlib import Path
from typing import Dict

import structlog
from watchdog.observers import Observer

# Use absolute imports
from supsrc.config.models import RepositoryConfig
from supsrc.exceptions import MonitoringSetupError, MonitoringError
from supsrc.monitor.events import MonitoredEvent
from supsrc.monitor.handler import SupsrcEventHandler

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
        print(f"[{time.time():.3f}] $$$ MonitoringService initialized $$$", file=sys.stderr)


    def add_repository(
        self, repo_id: str, repo_config: RepositoryConfig
    ) -> None:
        """ Adds a repository to be monitored. (No changes from previous version) """
        if not repo_config.enabled or not repo_config._path_valid:
             # ... (warning log) ...
            return
        repo_path = repo_config.path
        if not repo_path.is_dir():
            raise MonitoringSetupError(f"Repository path is not a valid directory", repo_id=repo_id, path=str(repo_path))

        self._logger.info("Adding repository to monitor", repo_id=repo_id, path=str(repo_path))
        handler = SupsrcEventHandler(repo_id=repo_id, repo_path=repo_path, event_queue=self._event_queue)
        self._handlers[repo_id] = handler
        try:
            self._observer.schedule(handler, str(repo_path), recursive=True)
            self._logger.debug("Scheduled handler with observer", repo_id=repo_id)
        except Exception as e:
             # ... (error handling) ...
            raise MonitoringSetupError(f"Failed to schedule monitoring: {e}", repo_id=repo_id, path=str(repo_path)) from e


    def start(self) -> None:
        """Starts the watchdog observer thread."""
        if not self._handlers:
             self._logger.warning("No repositories configured or added for monitoring. Observer not started.")
             print(f"[{time.time():.3f}] $$$ MonitoringService.start: No handlers, not starting observer $$$", file=sys.stderr)
             return

        if self._is_running:
            self._logger.warning("Monitoring service already running.")
            print(f"[{time.time():.3f}] $$$ MonitoringService.start: Already running $$$", file=sys.stderr)
            return

        try:
            print(f"[{time.time():.3f}] $$$ MonitoringService: Calling observer.start() $$$", file=sys.stderr)
            self._observer.start()
            self._is_running = True
            self._logger.info("Monitoring service started", num_handlers=len(self._handlers))
            print(f"[{time.time():.3f}] $$$ MonitoringService: observer.start() finished $$$", file=sys.stderr)
        except Exception as e:
            self._logger.critical("Failed to start monitoring observer", error=str(e), exc_info=True)
            print(f"[{time.time():.3f}] $$$ MonitoringService: observer.start() FAILED: {e} $$$", file=sys.stderr)
            raise MonitoringError(f"Failed to start observer thread: {e}") from e


    async def stop(self) -> None:
        """Stops the watchdog observer thread gracefully."""
        if not self._is_running:
            self._logger.info("Monitoring service already stopped.")
            print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Already stopped $$$", file=sys.stderr)
            return

        self._logger.info("Stopping monitoring service...")
        print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Stopping observer... $$$", file=sys.stderr)
        thread_stopped = False
        join_success = False
        try:
            # Signal the observer thread to stop (this is non-blocking)
            print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Calling observer.stop() $$$", file=sys.stderr)
            self._observer.stop()
            print(f"[{time.time():.3f}] $$$ MonitoringService.stop: observer.stop() returned $$$", file=sys.stderr)

            # Wait for the observer thread to finish using asyncio.to_thread
            self._logger.debug("Waiting for observer thread to join...")
            print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Calling asyncio.to_thread(observer.join) $$$", file=sys.stderr)
            try:
                await asyncio.to_thread(self._observer.join, timeout=5.0)
                join_success = True
                print(f"[{time.time():.3f}] $$$ MonitoringService.stop: asyncio.to_thread(observer.join) finished $$$", file=sys.stderr)
            except Exception as join_exc: # Catch potential errors during join (e.g., thread errors)
                print(f"[{time.time():.3f}] $$$ MonitoringService.stop: asyncio.to_thread(observer.join) raised {type(join_exc).__name__}: {join_exc} $$$", file=sys.stderr)
                log.error("Exception during observer join", error=str(join_exc), exc_info=True)


            if self._observer.is_alive():
                 self._logger.warning("Observer thread did not stop within timeout or failed join.")
                 print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Observer thread still alive after join attempt $$$", file=sys.stderr)
            else:
                 # Only set thread_stopped if join seemed successful and thread is dead
                 if join_success:
                     thread_stopped = True
                     self._logger.info("Observer thread stopped.")
                     print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Observer thread confirmed stopped $$$", file=sys.stderr)
                 else:
                      self._logger.warning("Observer thread stopped but join failed.")
                      print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Observer thread stopped but join failed $$$", file=sys.stderr)


        except Exception as e:
            self._logger.error("Error stopping monitoring observer", error=str(e), exc_info=True)
            print(f"[{time.time():.3f}] $$$ MonitoringService.stop: Error during stop sequence: {e} $$$", file=sys.stderr)
        finally:
             self._is_running = False
             # Log the final status based on whether the join completed successfully
             if thread_stopped:
                self._logger.info("Monitoring service cleanup successful.")
                print(f"[{time.time():.3f}] $$$ MonitoringService.stop finally: Cleanup successful $$$", file=sys.stderr)
             else:
                 self._logger.warning("Monitoring service stopped, but observer thread join may have failed or timed out.")
                 print(f"[{time.time():.3f}] $$$ MonitoringService.stop finally: Cleanup may be incomplete $$$", file=sys.stderr)

    @property
    def is_running(self) -> bool:
        """Returns True if the observer thread is currently active."""
        # Check both internal flag and observer thread status for robustness
        # Use observer's state as the primary indicator if it's initialized
        # Check if observer exists and is alive
        observer_alive = hasattr(self, '_observer') and self._observer is not None and self._observer.is_alive()
        # Return true only if internal flag is set AND observer thread is alive
        # print(f"[{time.time():.3f}] $$$ MonitoringService.is_running check: _is_running={self._is_running}, observer_alive={observer_alive} $$$", file=sys.stderr)
        return self._is_running and observer_alive

# 🔼⚙️
