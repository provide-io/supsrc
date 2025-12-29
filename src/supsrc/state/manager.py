#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Main state management coordination class."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.state.control import StateData
    from supsrc.state.monitor import StateMonitor
    from supsrc.state.runtime import RepositoryState

log = get_logger("state.manager")


class StateManager:
    """Main coordination class for supsrc state management."""

    def __init__(self, repo_paths: list[Path] | None = None) -> None:
        """Initialize state manager.

        Args:
            repo_paths: Repository paths to manage state for
        """
        self.repo_paths = repo_paths or []
        self._monitor: StateMonitor | None = None
        self._repo_states: dict[str, RepositoryState] = {}

    async def start(self) -> None:
        """Start the state management system."""
        from supsrc.state.monitor import StateMonitor

        if self._monitor:
            log.warning("State manager already started")
            return

        self._monitor = StateMonitor(self.repo_paths)
        self._monitor.register_callback(self._on_state_change)
        await self._monitor.start()
        log.info("State manager started", repo_count=len(self.repo_paths))

    async def stop(self) -> None:
        """Stop the state management system."""
        if self._monitor:
            await self._monitor.stop()
            self._monitor = None
        log.info("State manager stopped")

    def _on_state_change(self, repo_id: str, state_data: StateData | None) -> None:
        """Callback for state file changes."""
        if repo_id == "global":
            log.info("Global state changed", paused=state_data.paused if state_data else False)
        else:
            log.info(
                "Repository state changed",
                repo_id=repo_id,
                paused=state_data.is_repo_paused(repo_id) if state_data else False,
            )

        # Apply state changes to repository states
        if state_data:
            self._apply_state_to_repositories(repo_id, state_data)
        else:
            self._clear_state_overrides(repo_id)

    def _apply_state_to_repositories(self, repo_id: str, state_data: StateData) -> None:
        """Apply state data changes to repository state objects."""
        if repo_id == "global":
            # Apply global pause to all repositories
            for repo_state in self._repo_states.values():
                if state_data.paused and not state_data.is_expired():
                    repo_state.is_paused = True
                    repo_state.pause_until = state_data.paused_until
                else:
                    repo_state.is_paused = False
                    repo_state.pause_until = None
                repo_state._update_display_emoji()
        else:
            # Apply repository-specific state
            repo_state = self._repo_states.get(repo_id)
            if repo_state:
                if state_data.is_repo_paused(repo_id) and not state_data.is_expired():
                    repo_state.is_paused = True
                    repo_override = state_data.repositories.get(repo_id)
                    if repo_override:
                        # Apply repository-specific overrides
                        pass  # Could extend with more granular overrides
                else:
                    repo_state.is_paused = False
                    repo_state.pause_until = None
                repo_state._update_display_emoji()

    def _clear_state_overrides(self, repo_id: str) -> None:
        """Clear state overrides when state file is removed or expired."""
        if repo_id == "global":
            for repo_state in self._repo_states.values():
                repo_state.is_paused = False
                repo_state.pause_until = None
                repo_state._update_display_emoji()
        else:
            repo_state = self._repo_states.get(repo_id)
            if repo_state:
                repo_state.is_paused = False
                repo_state.pause_until = None
                repo_state._update_display_emoji()

    def register_repository_state(self, repo_id: str, repo_state: RepositoryState) -> None:
        """Register a repository state object for management."""
        self._repo_states[repo_id] = repo_state
        log.debug("Registered repository state", repo_id=repo_id)

        # Apply any existing state immediately
        if self._monitor:
            current_state = self._monitor.get_current_state("global")
            if current_state:
                self._apply_state_to_repositories("global", current_state)

            repo_state_data = self._monitor.get_current_state(repo_id)
            if repo_state_data:
                self._apply_state_to_repositories(repo_id, repo_state_data)

    def unregister_repository_state(self, repo_id: str) -> None:
        """Unregister a repository state object."""
        if repo_id in self._repo_states:
            del self._repo_states[repo_id]
            log.debug("Unregistered repository state", repo_id=repo_id)

    def is_paused(self, repo_id: str | None = None) -> bool:
        """Check if monitoring is paused globally or for a specific repository."""
        if self._monitor:
            return self._monitor.is_paused(repo_id)
        return False

    def pause(
        self,
        repo_id: str | None = None,
        duration: int | None = None,
        reason: str | None = None,
        updated_by: str | None = None,
    ) -> bool:
        """Pause monitoring globally or for a specific repository.

        Args:
            repo_id: Repository to pause, None for global pause
            duration: Duration in seconds, None for indefinite
            reason: Reason for pause
            updated_by: Who requested the pause

        Returns:
            True if pause was successful
        """
        from supsrc.state.control import RepositoryStateOverride, StateData
        from supsrc.state.file import StateFile

        try:
            # Determine target path
            if repo_id:
                repo_path = next((p for p in self.repo_paths if p.name == repo_id), None)
                if not repo_path:
                    log.error("Repository path not found for pause", repo_id=repo_id)
                    return False
            else:
                repo_path = None

            # Load existing state or create new
            existing_state = StateFile.load(repo_path=repo_path)
            state_data = existing_state if existing_state else StateData()

            # Calculate pause until time
            paused_until = None
            if duration:
                paused_until = datetime.now(UTC) + timedelta(seconds=duration)

            # Set state
            if repo_id:
                # Repository-specific pause
                if repo_id not in state_data.repositories:
                    state_data.repositories[repo_id] = RepositoryStateOverride()
                state_data.repositories[repo_id].paused = True
            else:
                # Global pause
                state_data.paused = True
                state_data.paused_until = paused_until
                state_data.pause_reason = reason

            # Update metadata
            state_data.updated_at = datetime.now(UTC)
            state_data.updated_by = updated_by or "state_manager"
            state_data.pid = os.getpid()

            # Save state
            success = StateFile.save(state_data, repo_path=repo_path)
            if success:
                log.info(
                    "Successfully paused",
                    repo_id=repo_id or "global",
                    duration=duration,
                    reason=reason,
                    until=paused_until.isoformat() if paused_until else None,
                )
            return success

        except Exception:
            log.exception("Failed to pause", repo_id=repo_id)
            return False

    def resume(self, repo_id: str | None = None) -> bool:
        """Resume monitoring globally or for a specific repository.

        Args:
            repo_id: Repository to resume, None for global resume

        Returns:
            True if resume was successful
        """
        from supsrc.state.file import StateFile

        try:
            # Determine target path
            if repo_id:
                repo_path = next((p for p in self.repo_paths if p.name == repo_id), None)
                if not repo_path:
                    log.error("Repository path not found for resume", repo_id=repo_id)
                    return False
            else:
                repo_path = None

            # Load existing state
            state_data = StateFile.load(repo_path=repo_path)
            if not state_data:
                log.debug("No state file found, nothing to resume", repo_id=repo_id)
                return True

            # Clear pause state
            if repo_id:
                # Repository-specific resume
                if repo_id in state_data.repositories:
                    state_data.repositories[repo_id].paused = False
                    # Remove empty repository entries
                    repo_override = state_data.repositories[repo_id]
                    if not any(
                        [
                            repo_override.paused,
                            repo_override.save_count_disabled,
                            repo_override.inactivity_seconds,
                            repo_override.rule_overrides,
                        ]
                    ):
                        del state_data.repositories[repo_id]
            else:
                # Global resume
                state_data.paused = False
                state_data.paused_until = None
                state_data.pause_reason = None

            # Update metadata
            state_data.updated_at = datetime.now(UTC)
            state_data.updated_by = "state_manager"

            # If no active state remains, delete the file
            if not state_data.paused and not state_data.repositories and not state_data.pause_reason:
                success = StateFile.delete(repo_path=repo_path)
            else:
                success = StateFile.save(state_data, repo_path=repo_path)

            if success:
                log.info("Successfully resumed", repo_id=repo_id or "global")
            return success

        except Exception:
            log.exception("Failed to resume", repo_id=repo_id)
            return False

    @contextmanager
    def pause_context(
        self,
        repo_id: str | None = None,
        duration: int | None = None,
        reason: str | None = None,
        updated_by: str | None = None,
    ) -> Iterator[None]:
        """Context manager for temporary pause/resume.

        Args:
            repo_id: Repository to pause, None for global pause
            duration: Duration in seconds, None for indefinite
            reason: Reason for pause
            updated_by: Who requested the pause

        Example:
            with state_manager.pause_context(repo_id="my-repo", duration=300):
                # Do work that needs supsrc paused
                pass
            # Automatically resumed here
        """
        paused = self.pause(repo_id, duration, reason, updated_by)
        try:
            yield
        finally:
            if paused:
                self.resume(repo_id)

    def get_state_info(self, repo_id: str | None = None) -> dict[str, Any]:
        """Get current state information.

        Args:
            repo_id: Repository to get state for, None for global

        Returns:
            Dictionary with state information
        """
        from supsrc.state.file import StateFile

        # Determine target path
        repo_path = next((p for p in self.repo_paths if p.name == repo_id), None) if repo_id else None

        state_data = StateFile.load(repo_path=repo_path)

        if not state_data:
            return {"paused": False, "state_file_exists": False}

        info = {
            "state_file_exists": True,
            "paused": state_data.paused if not repo_id else state_data.is_repo_paused(repo_id or ""),
            "paused_until": state_data.paused_until.isoformat() if state_data.paused_until else None,
            "pause_reason": state_data.pause_reason,
            "updated_by": state_data.updated_by,
            "updated_at": state_data.updated_at.isoformat(),
            "is_expired": state_data.is_expired(),
        }

        if repo_id and repo_id in state_data.repositories:
            repo_override = state_data.repositories[repo_id]
            info["repository_overrides"] = {
                "paused": repo_override.paused,
                "save_count_disabled": repo_override.save_count_disabled,
                "inactivity_seconds": repo_override.inactivity_seconds,
                "rule_overrides": repo_override.rule_overrides,
            }

        return info

    def add_repository(self, repo_path: Path) -> None:
        """Add a repository to state management."""
        if repo_path not in self.repo_paths:
            self.repo_paths.append(repo_path)
            if self._monitor:
                self._monitor.add_repo_path(repo_path)
            log.debug("Added repository to state manager", repo_path=str(repo_path))

    def remove_repository(self, repo_path: Path) -> None:
        """Remove a repository from state management."""
        if repo_path in self.repo_paths:
            self.repo_paths.remove(repo_path)
            if self._monitor:
                self._monitor.remove_repo_path(repo_path)
            # Clean up state
            repo_id = repo_path.name
            if repo_id in self._repo_states:
                del self._repo_states[repo_id]
            log.debug("Removed repository from state manager", repo_path=str(repo_path))


# 🔼⚙️🔚
