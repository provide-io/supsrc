#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Monitoring for state file changes."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.state.control import StateData

log = get_logger(__name__)


class StateMonitor:
    """Monitors state files for changes and manages state lifecycle."""

    def __init__(self, repo_paths: list[Path] | None = None) -> None:
        """Initialize state monitor.

        Args:
            repo_paths: Repository paths to monitor for state files
        """
        self.repo_paths = repo_paths or []
        self._callbacks: list[Callable[[str, StateData | None], None]] = []
        self._file_stats: dict[str, tuple[float, int]] = {}  # path -> (mtime, size)
        self._current_states: dict[str, StateData] = {}  # repo_id -> StateData
        self._is_running = False
        self._monitor_task: asyncio.Task[None] | None = None
        self._check_interval = 2.0  # Check every 2 seconds

    def register_callback(self, callback: Callable[[str, StateData | None], None]) -> None:
        """Register a callback for state changes.

        Args:
            callback: Function called with (repo_id, state_data) when state changes
        """
        self._callbacks.append(callback)
        log.debug("Registered state change callback", callback=callback.__name__)

    def unregister_callback(self, callback: Callable[[str, StateData | None], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            log.debug("Unregistered state change callback", callback=callback.__name__)

    async def start(self) -> None:
        """Start monitoring state files."""
        if self._is_running:
            log.warning("State monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        log.info("State monitor started", repo_count=len(self.repo_paths))

        # Initial load of existing state files
        await self._check_all_files()

    async def stop(self) -> None:
        """Stop monitoring state files."""
        if not self._is_running:
            return

        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        log.info("State monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        try:
            while self._is_running:
                await self._check_all_files()
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            log.debug("State monitor loop cancelled")
        except Exception:
            log.exception("Error in state monitor loop")

    async def _check_all_files(self) -> None:
        """Check all relevant state files for changes."""
        from supsrc.state.file import StateFile

        # Check global state file
        global_state_file = StateFile.find_state_file()
        if global_state_file:
            await self._check_file_change(global_state_file, "global")

        # Check repository-specific state files
        for repo_path in self.repo_paths:
            repo_id = repo_path.name
            repo_state_file = repo_path / StateFile.STATE_FILENAME
            if repo_state_file.exists():
                await self._check_file_change(repo_state_file, repo_id)

        # Check for expired states
        await self._check_expiration()

    async def _check_file_change(self, file_path: Path, repo_id: str) -> None:
        """Check if a specific file has changed."""
        try:
            stat = file_path.stat()
            current_stats = (stat.st_mtime, stat.st_size)
            file_key = str(file_path)

            # Check if file has changed
            if file_key in self._file_stats and self._file_stats[file_key] == current_stats:
                return  # No change

            # File has changed or is new
            self._file_stats[file_key] = current_stats

            # Load and process new state
            from supsrc.state.file import StateFile

            state_data = StateFile.load(file_path)
            if state_data:
                await self._process_state_change(repo_id, state_data)
            else:
                log.warning("Failed to load changed state file", path=str(file_path))

        except OSError as e:
            log.warning("Failed to check state file", path=str(file_path), error=str(e))

    async def _process_state_change(self, repo_id: str, state_data: StateData) -> None:
        """Process a state change and notify callbacks."""
        previous_state = self._current_states.get(repo_id)

        # Check if state actually changed
        if previous_state and self._states_equal(previous_state, state_data):
            return

        self._current_states[repo_id] = state_data
        log.info(
            "State changed",
            repo_id=repo_id,
            paused=state_data.paused,
            reason=state_data.pause_reason,
            updated_by=state_data.updated_by,
        )

        # Notify all callbacks
        for callback in self._callbacks:
            try:
                callback(repo_id, state_data)
            except Exception:
                log.exception("Error in state change callback", callback=callback.__name__)

    async def _check_expiration(self) -> None:
        """Check for expired pause states and clean them up."""
        expired_repos = []

        for repo_id, state_data in self._current_states.items():
            if state_data.is_expired():
                expired_repos.append(repo_id)

        for repo_id in expired_repos:
            log.info("State expired, clearing pause", repo_id=repo_id)

            # Find and remove the expired state file
            from supsrc.state.file import StateFile

            if repo_id == "global":
                state_file = StateFile.find_state_file()
            else:
                repo_path = next((p for p in self.repo_paths if p.name == repo_id), None)
                state_file = StateFile.find_state_file(repo_path) if repo_path else None

            if state_file:
                StateFile.delete(state_file)

            # Remove from current states and notify
            del self._current_states[repo_id]
            for callback in self._callbacks:
                try:
                    callback(repo_id, None)  # None indicates cleared state
                except Exception:
                    log.exception("Error in state expiration callback", callback=callback.__name__)

    def _states_equal(self, state1: StateData, state2: StateData) -> bool:
        """Check if two states are functionally equal."""
        return (
            state1.paused == state2.paused
            and state1.paused_until == state2.paused_until
            and state1.repositories == state2.repositories
        )

    def get_current_state(self, repo_id: str) -> StateData | None:
        """Get the current state for a repository."""
        return self._current_states.get(repo_id)

    def is_paused(self, repo_id: str | None = None) -> bool:
        """Check if monitoring is paused for a repository or globally."""
        # Check global pause state
        global_state = self._current_states.get("global")
        if global_state and global_state.paused and not global_state.is_expired():
            return True

        # Check repository-specific pause
        if repo_id:
            repo_state = self._current_states.get(repo_id)
            if repo_state and repo_state.is_repo_paused(repo_id) and not repo_state.is_expired():
                return True

        return False

    def add_repo_path(self, repo_path: Path) -> None:
        """Add a repository path to monitor."""
        if repo_path not in self.repo_paths:
            self.repo_paths.append(repo_path)
            log.debug("Added repository to state monitor", repo_path=str(repo_path))

    def remove_repo_path(self, repo_path: Path) -> None:
        """Remove a repository path from monitoring."""
        if repo_path in self.repo_paths:
            self.repo_paths.remove(repo_path)
            repo_id = repo_path.name
            if repo_id in self._current_states:
                del self._current_states[repo_id]
            log.debug("Removed repository from state monitor", repo_path=str(repo_path))


# 🔼⚙️🔚
