#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Git operation helpers and utilities for the GitEngine."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygit2
from provide.foundation.logger import get_logger

log = get_logger(__name__)

# --- Constants for Change Summary ---
MAX_SUMMARY_FILES = 10
SUMMARY_ADDED_PREFIX = "A "
SUMMARY_MODIFIED_PREFIX = "M "
SUMMARY_DELETED_PREFIX = "D "
SUMMARY_RENAMED_PREFIX = "R "  # R old -> new
SUMMARY_TYPECHANGE_PREFIX = "T "


class GitOperationsHelper:
    """Helper class for Git repository operations and utilities."""

    def __init__(self) -> None:
        self._log = log.bind(helper_id=id(self))
        self._log.debug("GitOperationsHelper initialized")

    def get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to get the pygit2 Repository object."""
        try:
            # More robustly open the repository assuming working_dir is the root.
            repo = pygit2.Repository(str(working_dir))
            return repo
        except pygit2.GitError as e:
            self._log.error("Failed to open Git repository", path=str(working_dir), error=str(e))
            raise

    def get_config_value(self, key: str, config: dict[str, Any], default: Any = None) -> Any:
        """Safely gets a value from the engine-specific config dict."""
        return config.get(key, default)

    def generate_change_summary(self, diff: pygit2.Diff) -> str:
        """Generate a human-readable summary of changes from a diff."""
        added, modified, deleted, renamed, typechanged = [], [], [], [], []
        for delta in diff.deltas:
            path = (
                delta.new_file.path
                if delta.status != pygit2.GIT_DELTA_DELETED  # type: ignore[attr-defined]
                else delta.old_file.path
            )
            if delta.status == pygit2.GIT_DELTA_ADDED:  # type: ignore[attr-defined]
                added.append(path)
            elif delta.status == pygit2.GIT_DELTA_MODIFIED:  # type: ignore[attr-defined]
                modified.append(path)
            elif delta.status == pygit2.GIT_DELTA_DELETED:  # type: ignore[attr-defined]
                deleted.append(path)
            elif delta.status == pygit2.GIT_DELTA_RENAMED:  # type: ignore[attr-defined]
                renamed.append(f"{delta.old_file.path} -> {delta.new_file.path}")
            elif delta.status == pygit2.GIT_DELTA_TYPECHANGE:  # type: ignore[attr-defined]
                typechanged.append(path)

        summary_lines = []
        if added:
            summary_lines.append(f"Added ({len(added)}):")
            summary_lines.extend([f"  {SUMMARY_ADDED_PREFIX}{f}" for f in added[:MAX_SUMMARY_FILES]])
            if len(added) > MAX_SUMMARY_FILES:
                summary_lines.append(f"  ... ({len(added) - MAX_SUMMARY_FILES} more)")

        if modified:
            summary_lines.append(f"Modified ({len(modified)}):")
            summary_lines.extend([f"  {SUMMARY_MODIFIED_PREFIX}{f}" for f in modified[:MAX_SUMMARY_FILES]])
            if len(modified) > MAX_SUMMARY_FILES:
                summary_lines.append(f"  ... ({len(modified) - MAX_SUMMARY_FILES} more)")

        if deleted:
            summary_lines.append(f"Deleted ({len(deleted)}):")
            summary_lines.extend([f"  {SUMMARY_DELETED_PREFIX}{f}" for f in deleted[:MAX_SUMMARY_FILES]])
            if len(deleted) > MAX_SUMMARY_FILES:
                summary_lines.append(f"  ... ({len(deleted) - MAX_SUMMARY_FILES} more)")

        if renamed:
            summary_lines.append(f"Renamed ({len(renamed)}):")
            summary_lines.extend([f"  {SUMMARY_RENAMED_PREFIX}{f}" for f in renamed[:MAX_SUMMARY_FILES]])
            if len(renamed) > MAX_SUMMARY_FILES:
                summary_lines.append(f"  ... ({len(renamed) - MAX_SUMMARY_FILES} more)")

        if typechanged:
            summary_lines.append(f"Type Changed ({len(typechanged)}):")
            summary_lines.extend(
                [f"  {SUMMARY_TYPECHANGE_PREFIX}{f}" for f in typechanged[:MAX_SUMMARY_FILES]]
            )
            if len(typechanged) > MAX_SUMMARY_FILES:
                summary_lines.append(f"  ... ({len(typechanged) - MAX_SUMMARY_FILES} more)")

        return "\n".join(summary_lines)

    async def get_commit_history(self, working_dir: Path, limit: int = 10) -> list[str]:
        """Retrieves the last N commit messages from the repository asynchronously."""

        def _blocking_get_history() -> list[str]:
            repo = self.get_repo(working_dir)
            if repo.is_empty or repo.head_is_unborn:
                return ["Repository is empty or unborn."]

            last_commits: list[str] = []
            for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):  # type: ignore[attr-defined]
                if len(last_commits) >= limit:
                    break
                commit_time = datetime.fromtimestamp(commit.commit_time, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
                summary = (commit.message or "").split("\n", 1)[0][:60]
                author_name = commit.author.name if commit.author else "Unknown"
                last_commits.append(f"{str(commit.id)[:7]} - {author_name} - {commit_time} - {summary}")
            return last_commits

        try:
            return await asyncio.to_thread(_blocking_get_history)
        except pygit2.GitError as e:
            self._log.error("Failed to get commit history", error=str(e))
            return [f"Error fetching history: {e}"]
        except Exception as e:
            self._log.exception("Unexpected error getting commit history")
            return [f"Unexpected error fetching history: {e}"]


# 🔼⚙️🔚
