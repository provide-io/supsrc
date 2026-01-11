# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Status management functionality extracted from orchestrator to reduce file size
and provide dedicated repository status refresh capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

from supsrc.protocols import RepositoryEngine
from supsrc.state import RepositoryState

if TYPE_CHECKING:
    from supsrc.config import SupsrcConfig

log = get_logger(__name__)


class StatusManager:
    """Manages repository status updates and statistics refresh."""

    def __init__(
        self,
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, RepositoryEngine],
        config: SupsrcConfig,
        state_update_callback: callable,
    ):
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.config = config
        self.state_update_callback = state_update_callback

    def set_repo_refreshing_status(self, repo_id: str, is_refreshing: bool) -> None:
        """Sets the refreshing status for a repository."""
        repo_state = self.repo_states.get(repo_id)
        if repo_state:
            repo_state.is_refreshing = is_refreshing
            repo_state._update_display_emoji()
            self.state_update_callback()

    async def refresh_repository_status(self, repo_id: str) -> bool:
        """Force a refresh of the repository's status and statistics."""
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id) if self.config else None
        repo_engine = self.repo_engines.get(repo_id)

        if not repo_state or not repo_config or not repo_engine:
            log.warning(
                "Cannot refresh status: missing components",
                repo_id=repo_id,
                has_state=bool(repo_state),
                has_config=bool(repo_config),
                has_engine=bool(repo_engine),
            )
            return False

        log.info("Refreshing repository status", repo_id=repo_id)
        try:
            # Get current status and statistics
            status_result = await repo_engine.get_status(
                repo_state,
                repo_config.repository,
                self.config.global_config if self.config else {},
                repo_config.path,
            )

            if status_result.success:
                # Update all relevant fields in repo_state from status_result
                repo_state.total_files = status_result.total_files or 0
                repo_state.changed_files = status_result.changed_files or 0
                repo_state.added_files = status_result.added_files or 0
                repo_state.deleted_files = status_result.deleted_files or 0
                repo_state.modified_files = status_result.modified_files or 0
                repo_state.has_uncommitted_changes = not status_result.is_clean
                repo_state.current_branch = status_result.current_branch
                # Update remote sync status
                repo_state.commits_ahead = status_result.commits_ahead
                repo_state.commits_behind = status_result.commits_behind
                repo_state.has_upstream = status_result.has_upstream
                repo_state.upstream_branch = status_result.upstream_branch

                # Get repository summary to update commit information
                summary = await repo_engine.get_summary(repo_config.path)
                if hasattr(summary, "head_commit_timestamp") and summary.head_commit_timestamp:
                    repo_state.last_commit_timestamp = summary.head_commit_timestamp
                    if hasattr(summary, "head_commit_hash") and summary.head_commit_hash:
                        repo_state.last_commit_short_hash = summary.head_commit_hash[:7]
                    if hasattr(summary, "head_commit_message_summary"):
                        repo_state.last_commit_message_summary = summary.head_commit_message_summary

                # Trigger state update to refresh UI
                self.state_update_callback()
                log.info("Repository status refreshed successfully", repo_id=repo_id)
                return True
            else:
                log.error(
                    "Failed to get status during refresh",
                    repo_id=repo_id,
                    error=status_result.message,
                )
                return False

        except Exception as e:
            log.error("Error refreshing repository status", repo_id=repo_id, error=str(e))
            return False

    async def update_repository_statistics(
        self, repo_id: str, repo_state: RepositoryState, repo_engine: RepositoryEngine
    ) -> bool:
        """Update repository statistics after an action or during initialization."""
        repo_config = self.config.repositories.get(repo_id) if self.config else None
        if not repo_config:
            return False

        try:
            # Get current status and update statistics
            status_result = await repo_engine.get_status(
                repo_state,
                repo_config.repository,
                self.config.global_config if self.config else {},
                repo_config.path,
            )

            if status_result.success:
                # Copy statistics from status result to repository state
                repo_state.total_files = status_result.total_files or 0
                repo_state.changed_files = status_result.changed_files or 0
                repo_state.added_files = status_result.added_files or 0
                repo_state.deleted_files = status_result.deleted_files or 0
                repo_state.modified_files = status_result.modified_files or 0
                repo_state.has_uncommitted_changes = not status_result.is_clean
                repo_state.current_branch = status_result.current_branch
                # Update remote sync status
                repo_state.commits_ahead = status_result.commits_ahead
                repo_state.commits_behind = status_result.commits_behind
                repo_state.has_upstream = status_result.has_upstream
                repo_state.upstream_branch = status_result.upstream_branch

                log.debug(
                    "Repository statistics updated",
                    repo_id=repo_id,
                    total_files=repo_state.total_files,
                    changed_files=repo_state.changed_files,
                )
                return True

        except Exception as e:
            log.error("Error updating repository statistics", repo_id=repo_id, error=str(e))

        return False


# 🔼⚙️🔚
