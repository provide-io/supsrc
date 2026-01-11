# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""State management system for supsrc.

This module provides external control over supsrc's monitoring behavior through
.supsrc.state files and programmatic APIs.

Usage:
    # Quick pause/resume for LLM editing
    from supsrc.state import pause_global, resume_global

    # Pause for 5 minutes
    pause_global(duration=300, reason="LLM editing")

    # Context manager for safe operations
    from supsrc.state import StateManager

    state_manager = StateManager([Path("/path/to/repo")])
    with state_manager.pause_context(duration=300, reason="Batch processing"):
        # Do work that needs supsrc paused
        pass"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Import main classes
from .control import RepositoryStateOverride, StateData
from .file import StateFile
from .manager import StateManager
from .monitor import StateMonitor
from .runtime import STATUS_EMOJI_MAP, RepositoryState, RepositoryStatus

__all__ = [
    "STATUS_EMOJI_MAP",
    "RepositoryState",
    "RepositoryStateOverride",
    "RepositoryStatus",
    "StateData",
    "StateFile",
    "StateManager",
    "StateMonitor",
    "get_state_info",
    "is_paused",
    "pause_global",
    "pause_repository",
    "resume_global",
    "resume_repository",
]

# Global state manager instance for convenience functions
_global_state_manager: StateManager | None = None


def _get_global_state_manager() -> StateManager:
    """Get or create the global state manager instance."""
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = StateManager()
    return _global_state_manager


def pause_global(
    duration: int | None = None,
    reason: str | None = None,
    updated_by: str | None = None,
) -> bool:
    """Pause supsrc monitoring globally.

    Args:
        duration: Duration in seconds, None for indefinite
        reason: Reason for pause
        updated_by: Who requested the pause

    Returns:
        True if pause was successful

    Example:
        # Pause for 5 minutes while doing LLM editing
        pause_global(duration=300, reason="LLM editing session")
    """
    manager = _get_global_state_manager()
    return manager.pause(
        repo_id=None,
        duration=duration,
        reason=reason,
        updated_by=updated_by or "supsrc.state.api",
    )


def resume_global() -> bool:
    """Resume supsrc monitoring globally.

    Returns:
        True if resume was successful
    """
    manager = _get_global_state_manager()
    return manager.resume(repo_id=None)


def pause_repository(
    repo_path: Path | str,
    duration: int | None = None,
    reason: str | None = None,
    updated_by: str | None = None,
) -> bool:
    """Pause supsrc monitoring for a specific repository.

    Args:
        repo_path: Path to the repository
        duration: Duration in seconds, None for indefinite
        reason: Reason for pause
        updated_by: Who requested the pause

    Returns:
        True if pause was successful

    Example:
        # Pause specific repository
        pause_repository("/path/to/repo", duration=300, reason="Database migration")
    """
    repo_path_obj = Path(repo_path)
    repo_id = repo_path_obj.name

    manager = _get_global_state_manager()
    if repo_path_obj not in manager.repo_paths:
        manager.add_repository(repo_path_obj)

    return manager.pause(
        repo_id=repo_id,
        duration=duration,
        reason=reason,
        updated_by=updated_by or "supsrc.state.api",
    )


def resume_repository(repo_path: Path | str) -> bool:
    """Resume supsrc monitoring for a specific repository.

    Args:
        repo_path: Path to the repository

    Returns:
        True if resume was successful
    """
    repo_path_obj = Path(repo_path)
    repo_id = repo_path_obj.name

    manager = _get_global_state_manager()
    return manager.resume(repo_id=repo_id)


def is_paused(repo_path: Path | str | None = None) -> bool:
    """Check if supsrc monitoring is paused.

    Args:
        repo_path: Path to specific repository, None to check global pause

    Returns:
        True if monitoring is paused
    """
    manager = _get_global_state_manager()

    if repo_path is None:
        return manager.is_paused(repo_id=None)

    repo_path_obj = Path(repo_path)
    repo_id = repo_path_obj.name
    return manager.is_paused(repo_id=repo_id)


def get_state_info(repo_path: Path | str | None = None) -> dict[str, Any]:
    """Get current state information.

    Args:
        repo_path: Path to specific repository, None for global state

    Returns:
        Dictionary with state information including:
        - paused: bool
        - paused_until: ISO timestamp or None
        - pause_reason: str or None
        - updated_by: str or None
        - is_expired: bool
    """
    manager = _get_global_state_manager()

    if repo_path is None:
        return manager.get_state_info(repo_id=None)

    repo_path_obj = Path(repo_path)
    repo_id = repo_path_obj.name
    return manager.get_state_info(repo_id=repo_id)


# Context manager class for external use
class PauseContext:
    """Context manager for temporary pause operations."""

    def __init__(
        self,
        repo_path: Path | str | None = None,
        duration: int | None = None,
        reason: str | None = None,
        updated_by: str | None = None,
    ):
        self.repo_path = Path(repo_path) if repo_path else None
        self.duration = duration
        self.reason = reason
        self.updated_by = updated_by or "supsrc.state.context"
        self._paused = False

    def __enter__(self) -> None:
        """Enter the pause context."""
        if self.repo_path:
            self._paused = pause_repository(self.repo_path, self.duration, self.reason, self.updated_by)
        else:
            self._paused = pause_global(self.duration, self.reason, self.updated_by)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the pause context and resume."""
        if self._paused:
            if self.repo_path:
                resume_repository(self.repo_path)
            else:
                resume_global()


def pause_context(
    repo_path: Path | str | None = None,
    duration: int | None = None,
    reason: str | None = None,
    updated_by: str | None = None,
) -> PauseContext:
    """Create a context manager for temporary pause operations.

    Args:
        repo_path: Path to repository, None for global pause
        duration: Duration in seconds, None for indefinite
        reason: Reason for pause
        updated_by: Who requested the pause

    Returns:
        Context manager that pauses on enter and resumes on exit

    Example:
        # Pause globally for 5 minutes
        with pause_context(duration=300, reason="LLM editing"):
            # Do work here
            pass  # Automatically resumes

        # Pause specific repository
        with pause_context("/path/to/repo", duration=300):
            # Repository-specific work
            pass
    """
    return PauseContext(repo_path, duration, reason, updated_by)


# 🔼⚙️🔚
