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
                if delta.status != pygit2.GIT_DELTA_DELETED
                else delta.old_file.path
            )
            if delta.status == pygit2.GIT_DELTA_ADDED:
                added.append(path)
            elif delta.status == pygit2.GIT_DELTA_MODIFIED:
                modified.append(path)
            elif delta.status == pygit2.GIT_DELTA_DELETED:
                deleted.append(path)
            elif delta.status == pygit2.GIT_DELTA_RENAMED:
                renamed.append(f"{delta.old_file.path} -> {delta.new_file.path}")
            elif delta.status == pygit2.GIT_DELTA_TYPECHANGE:
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
            for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
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

    async def get_detailed_commit_history(self, working_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
        """Get detailed commit history with stats for TUI display."""

        def _blocking_get_detailed_history() -> list[dict[str, Any]]:
            repo = self.get_repo(working_dir)
            if repo.is_empty or repo.head_is_unborn:
                return []

            commits: list[dict[str, Any]] = []
            for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
                if len(commits) >= limit:
                    break

                # Get diff stats for this commit
                added, deleted, modified = 0, 0, 0
                if commit.parents:
                    diff = repo.diff(commit.parents[0].tree, commit.tree)
                    for delta in diff.deltas:
                        if delta.status == pygit2.GIT_DELTA_ADDED:
                            added += 1
                        elif delta.status == pygit2.GIT_DELTA_DELETED:
                            deleted += 1
                        elif delta.status == pygit2.GIT_DELTA_MODIFIED:
                            modified += 1

                commits.append(
                    {
                        "hash": str(commit.id)[:7],
                        "full_hash": str(commit.id),
                        "author": commit.author.name if commit.author else "Unknown",
                        "email": commit.author.email if commit.author else "",
                        "timestamp": datetime.fromtimestamp(commit.commit_time, tz=UTC),
                        "message": (commit.message or "").split("\n", 1)[0][:80],
                        "full_message": commit.message or "",
                        "added": added,
                        "deleted": deleted,
                        "modified": modified,
                    }
                )
            return commits

        try:
            return await asyncio.to_thread(_blocking_get_detailed_history)
        except Exception as e:
            self._log.error("Failed to get detailed commit history", error=str(e))
            return []

    async def get_working_diff(self, working_dir: Path, max_lines: int = 500) -> str:
        """Get the diff of unstaged changes in the working directory."""

        def _escape_rich_markup(text: str) -> str:
            """Escape brackets in text to prevent Rich markup interpretation."""
            # Replace [ with \[ to escape Rich markup
            return text.replace("[", "\\[")

        def _blocking_get_diff() -> str:
            repo = self.get_repo(working_dir)
            if repo.is_empty or repo.head_is_unborn:
                return "Repository is empty or has no commits yet."

            # Get diff between HEAD and working directory (unstaged changes)
            diff = repo.diff(repo.head.peel().tree, None, flags=pygit2.GIT_DIFF_INCLUDE_UNTRACKED)

            if not diff:
                return "No changes detected."

            # Format the diff output
            lines = []
            line_count = 0
            truncated = False

            for patch in diff:
                if line_count >= max_lines:
                    truncated = True
                    break

                # File header
                delta = patch.delta
                if delta.status == pygit2.GIT_DELTA_ADDED:
                    header = f"+ NEW FILE: {delta.new_file.path}"
                elif delta.status == pygit2.GIT_DELTA_DELETED:
                    header = f"- DELETED: {delta.old_file.path}"
                elif delta.status == pygit2.GIT_DELTA_MODIFIED:
                    header = f"~ MODIFIED: {delta.new_file.path}"
                elif delta.status == pygit2.GIT_DELTA_RENAMED:
                    header = f"→ RENAMED: {delta.old_file.path} → {delta.new_file.path}"
                else:
                    header = f"? {delta.new_file.path}"

                lines.append(f"\n{'=' * 60}")
                lines.append(header)
                lines.append("=" * 60)
                line_count += 3

                # Hunks
                for hunk in patch.hunks:
                    if line_count >= max_lines:
                        truncated = True
                        break

                    lines.append(
                        f"\n@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@"
                    )
                    line_count += 1

                    for line in hunk.lines:
                        if line_count >= max_lines:
                            truncated = True
                            break

                        origin = line.origin
                        # Escape brackets in content to prevent Rich markup interpretation
                        content = _escape_rich_markup(line.content.rstrip("\n"))

                        if origin == "+":
                            lines.append(f"[green]+{content}[/green]")
                        elif origin == "-":
                            lines.append(f"[red]-{content}[/red]")
                        else:
                            lines.append(f" {content}")
                        line_count += 1

            if truncated:
                lines.append(f"\n... (truncated at {max_lines} lines)")

            return "\n".join(lines) if lines else "No diff content available."

        try:
            return await asyncio.to_thread(_blocking_get_diff)
        except Exception as e:
            self._log.error("Failed to get working diff", error=str(e))
            return f"Error getting diff: {e}"

    async def get_changed_files_tree(self, working_dir: Path) -> list[dict[str, Any]]:
        """Get changed files organized as a tree structure for display."""

        def _blocking_get_tree() -> list[dict[str, Any]]:
            repo = self.get_repo(working_dir)
            files: list[dict[str, Any]] = []

            for filepath, flags in repo.status().items():
                if flags == pygit2.GIT_STATUS_CURRENT:
                    continue

                # Determine status
                if flags & pygit2.GIT_STATUS_WT_NEW:
                    status = "untracked"
                    icon = "?"
                elif flags & pygit2.GIT_STATUS_INDEX_NEW:
                    status = "added"
                    icon = "A"
                elif flags & (pygit2.GIT_STATUS_WT_DELETED | pygit2.GIT_STATUS_INDEX_DELETED):
                    status = "deleted"
                    icon = "D"
                elif flags & (pygit2.GIT_STATUS_WT_MODIFIED | pygit2.GIT_STATUS_INDEX_MODIFIED):
                    status = "modified"
                    icon = "M"
                elif flags & (pygit2.GIT_STATUS_WT_RENAMED | pygit2.GIT_STATUS_INDEX_RENAMED):
                    status = "renamed"
                    icon = "R"
                else:
                    status = "changed"
                    icon = "~"

                # Check if staged
                is_staged = bool(
                    flags
                    & (
                        pygit2.GIT_STATUS_INDEX_NEW
                        | pygit2.GIT_STATUS_INDEX_MODIFIED
                        | pygit2.GIT_STATUS_INDEX_DELETED
                        | pygit2.GIT_STATUS_INDEX_RENAMED
                    )
                )

                # Get file info
                full_path = Path(repo.workdir) / filepath
                file_size = 0
                is_binary = False

                if full_path.exists():
                    try:
                        file_size = full_path.stat().st_size
                        # Check if binary by reading first 8KB
                        with open(full_path, "rb") as f:
                            chunk = f.read(8192)
                            is_binary = b"\x00" in chunk
                    except (OSError, PermissionError):
                        pass

                files.append(
                    {
                        "path": filepath,
                        "status": status,
                        "icon": icon,
                        "is_staged": is_staged,
                        "size": file_size,
                        "is_binary": is_binary,
                        "is_large": file_size > 1_000_000,  # 1MB threshold
                    }
                )

            # Sort by path for tree display
            return sorted(files, key=lambda f: f["path"])

        try:
            return await asyncio.to_thread(_blocking_get_tree)
        except Exception as e:
            self._log.error("Failed to get changed files tree", error=str(e))
            return []

    async def check_upstream_conflicts(self, working_dir: Path) -> dict[str, Any]:
        """Check if there are potential conflicts with upstream."""

        def _blocking_check_conflicts() -> dict[str, Any]:
            repo = self.get_repo(working_dir)

            result: dict[str, Any] = {
                "has_conflicts": False,
                "has_upstream": False,
                "ahead": 0,
                "behind": 0,
                "diverged": False,
                "upstream_branch": None,
                "message": "No issues detected",
            }

            if repo.is_empty or repo.head_is_unborn:
                result["message"] = "Repository is empty"
                return result

            # Check for merge conflicts in index
            if repo.index.conflicts:
                result["has_conflicts"] = True
                conflict_files = [c[0].path for c in repo.index.conflicts if c[0]]
                result["conflict_files"] = conflict_files[:10]
                result["message"] = f"{len(conflict_files)} file(s) have merge conflicts"
                return result

            # Check if tracking an upstream branch
            try:
                local_branch = repo.branches.get(repo.head.shorthand)
                if local_branch and local_branch.upstream:
                    result["has_upstream"] = True
                    result["upstream_branch"] = local_branch.upstream.shorthand

                    # Compare with upstream
                    local_oid = repo.head.target
                    upstream_oid = local_branch.upstream.target

                    ahead, behind = repo.ahead_behind(local_oid, upstream_oid)
                    result["ahead"] = ahead
                    result["behind"] = behind
                    result["diverged"] = ahead > 0 and behind > 0

                    if result["diverged"]:
                        result["message"] = f"Branch has diverged: {ahead} ahead, {behind} behind"
                    elif behind > 0:
                        result["message"] = f"Branch is {behind} commit(s) behind upstream"
                    elif ahead > 0:
                        result["message"] = f"Branch is {ahead} commit(s) ahead of upstream"
                    else:
                        result["message"] = "Up to date with upstream"
            except Exception as e:
                self._log.debug("No upstream tracking configured", error=str(e))
                result["message"] = "No upstream branch configured"

            return result

        try:
            return await asyncio.to_thread(_blocking_check_conflicts)
        except Exception as e:
            self._log.error("Failed to check upstream conflicts", error=str(e))
            return {"has_conflicts": False, "message": f"Error: {e}"}

    def analyze_files_for_warnings(
        self, working_dir: Path, large_threshold: int = 1_000_000, binary_warn: bool = True
    ) -> list[dict[str, Any]]:
        """Analyze changed files for large/binary warnings (synchronous for use in staging)."""
        warnings: list[dict[str, Any]] = []
        repo = self.get_repo(working_dir)

        for filepath, flags in repo.status().items():
            if flags == pygit2.GIT_STATUS_CURRENT:
                continue
            if flags & pygit2.GIT_STATUS_WT_DELETED:
                continue  # Skip deleted files

            full_path = Path(repo.workdir) / filepath

            if not full_path.exists():
                continue

            try:
                file_size = full_path.stat().st_size

                # Check for large files
                if file_size > large_threshold:
                    warnings.append(
                        {
                            "type": "large_file",
                            "path": filepath,
                            "size": file_size,
                            "message": f"Large file ({file_size / 1_000_000:.1f}MB): {filepath}",
                        }
                    )

                # Check for binary files
                if binary_warn:
                    with open(full_path, "rb") as f:
                        chunk = f.read(8192)
                        if b"\x00" in chunk:
                            warnings.append(
                                {
                                    "type": "binary_file",
                                    "path": filepath,
                                    "size": file_size,
                                    "message": f"Binary file detected: {filepath}",
                                }
                            )

            except (OSError, PermissionError) as e:
                self._log.debug("Could not analyze file", path=filepath, error=str(e))

        return warnings


# 🔼⚙️🔚
