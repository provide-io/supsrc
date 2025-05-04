#
# supsrc/monitor/handler.py
#
"""
Custom watchdog FileSystemEventHandler for supsrc.

Filters events based on .git directory and .gitignore rules, then
puts relevant events onto an asyncio Queue.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import pathspec
import structlog
from watchdog.events import FileSystemEvent, FileSystemEventHandler

# Use relative import for the event structure
from .events import MonitoredEvent

log = structlog.get_logger("monitor.handler")

# Define parts of the .git directory to always ignore
# Convert to strings for simple startswith check
GIT_DIR_PARTS = (
    f"{os.sep}.git{os.sep}",
    f"{os.sep}.git", # Should catch root .git folder itself if listed
)

class SupsrcEventHandler(FileSystemEventHandler):
    """
    Handles filesystem events, filters them, and queues them for processing.

    Runs within the watchdog observer thread. Uses queue.put_nowait()
    for thread-safe communication with the main asyncio loop.
    """

    def __init__(
        self,
        repo_id: str,
        repo_path: Path,
        event_queue: asyncio.Queue[MonitoredEvent],
    ):
        """
        Initializes the event handler for a specific repository.

        Args:
            repo_id: The unique identifier for the repository.
            repo_path: The absolute Path object to the repository root.
            event_queue: The asyncio Queue to put filtered MonitoredEvent objects onto.
        """
        super().__init__()
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.event_queue = event_queue
        self.logger = log.bind(repo_id=repo_id, repo_path=str(repo_path))
        self.gitignore_spec: Optional[pathspec.PathSpec] = self._load_gitignore()

        self.logger.debug("Initialized event handler")

    def _load_gitignore(self) -> Optional[pathspec.PathSpec]:
        """Loads and parses the .gitignore file for the repository."""
        gitignore_path = self.repo_path / ".gitignore"
        spec = None
        if gitignore_path.is_file():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    spec = pathspec.PathSpec.from_lines(
                        pathspec.patterns.GitWildMatchPattern, f
                    )
                self.logger.info("Loaded .gitignore patterns", path=str(gitignore_path))
            except OSError as e:
                self.logger.error(
                    "Failed to read .gitignore file",
                    path=str(gitignore_path),
                    error=str(e),
                )
            except Exception as e:
                self.logger.error(
                    "Failed to parse .gitignore file",
                    path=str(gitignore_path),
                    error=str(e),
                    exc_info=True,
                )
        else:
            self.logger.debug(".gitignore file not found, no ignore patterns loaded.")
        return spec

    def _is_ignored(self, file_path: Path) -> bool:
        """Checks if a given absolute path should be ignored."""
        # 1. Check if inside .git directory
        # Use os.path.normpath for consistent separator handling
        norm_path_str = os.path.normpath(str(file_path))
        repo_path_str = os.path.normpath(str(self.repo_path))
        # Check if path starts with repo_path + /.git/ or /.git
        if norm_path_str.startswith(os.path.join(repo_path_str, ".git") + os.sep) or \
           norm_path_str == os.path.join(repo_path_str, ".git"):
             self.logger.debug("Ignoring event inside .git directory", path=str(file_path))
             return True


        # 2. Check against .gitignore patterns (if loaded)
        if self.gitignore_spec:
            # pathspec works with paths relative to where .gitignore is
            try:
                relative_path = file_path.relative_to(self.repo_path)
                if self.gitignore_spec.match_file(str(relative_path)):
                    self.logger.debug("Ignoring event due to .gitignore match", path=str(file_path))
                    return True
            except ValueError:
                # Path is not relative to repo_path (shouldn't happen with watchdog)
                 self.logger.warning("Event path not relative to repo path", path=str(file_path))
                 return True # Ignore paths outside the repo being watched


        return False

    def _queue_event(self, event: FileSystemEvent):
        """Processes, filters, and queues a watchdog event."""
        event_type = event.event_type
        src_path_str = event.src_path
        dest_path_str = getattr(event, "dest_path", None) # For moved events

        try:
            src_path = Path(src_path_str).resolve()
            dest_path = Path(dest_path_str).resolve() if dest_path_str else None
        except Exception as e:
             self.logger.error("Failed to resolve event path(s)", src=src_path_str, dest=dest_path_str, error=str(e))
             return # Cannot process further


        # Filter based on path
        if self._is_ignored(src_path):
            return # Logged within _is_ignored

        # For 'moved' events, also check the destination
        if event_type == "moved" and dest_path and self._is_ignored(dest_path):
             self.logger.debug("Ignoring 'moved' event, destination is ignored", dest_path=str(dest_path))
             return

        # Create the structured event
        monitored_event = MonitoredEvent(
            repo_id=self.repo_id,
            event_type=event_type,
            src_path=src_path,
            is_directory=event.is_directory,
            dest_path=dest_path,
        )

        # Put onto the queue (non-blocking from worker thread)
        try:
            self.event_queue.put_nowait(monitored_event)
            self.logger.info(
                "Queued filesystem event",
                event_type=event_type,
                path=str(src_path),
                is_dir=event.is_directory,
                dest=str(dest_path) if dest_path else None,
            )
        except asyncio.QueueFull:
            self.logger.error(
                "Event queue is full, discarding event. Consumer might be blocked.",
                event_details=monitored_event,
            )
        except Exception as e:
             self.logger.error(
                 "Unexpected error queuing event",
                 error=str(e),
                 exc_info=True,
                 event_details=monitored_event
             )


    # Override watchdog methods
    def on_created(self, event: FileSystemEvent):
        self._queue_event(event)

    def on_modified(self, event: FileSystemEvent):
        # Ignore directory modifications unless specifically needed later
        if not event.is_directory:
            self._queue_event(event)
        else:
             self.logger.debug("Ignoring directory modification event", path=event.src_path)


    def on_deleted(self, event: FileSystemEvent):
        self._queue_event(event)

    def on_moved(self, event: FileSystemEvent):
        self._queue_event(event)

# 🔼⚙️
