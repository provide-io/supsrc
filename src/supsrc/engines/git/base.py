#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Implementation of the RepositoryEngine protocol using pygit2."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from provide.foundation.logger import get_logger

# Add Foundation resilience patterns for Git operations
from provide.foundation.resilience import BackoffStrategy, RetryPolicy, retry
import pygit2

from supsrc.config import GlobalConfig
from supsrc.engines.git.auth import GitAuthHandler
from supsrc.engines.git.info import GitRepoSummary
from supsrc.engines.git.operations import GitOperationsHelper

# Use absolute imports
from supsrc.protocols import (
    CommitResult,
    PushResult,
    RepositoryEngine,
    RepoStatusResult,
    StageResult,
)
from supsrc.state import RepositoryState

log = get_logger(__name__)


class GitEngine(RepositoryEngine):
    """Implements RepositoryEngine using pygit2."""

    def __init__(self) -> None:
        self._log = log.bind(engine_id=id(self))
        self._log.debug("GitEngine initialized")
        self.operations = GitOperationsHelper()
        self.auth_handler = GitAuthHandler()
        self._credentials_callback = self.auth_handler.create_credentials_callback()

    async def get_summary(self, working_dir: Path) -> GitRepoSummary:
        """Gets a summary of the repository's HEAD state."""

        def _blocking_get_summary():
            repo = self.operations.get_repo(working_dir)
            if repo.is_empty:
                return {"is_empty": True}
            if repo.head_is_unborn:
                return {"head_ref_name": "UNBORN"}

            head_ref = repo.head
            head_commit = head_ref.peel()
            commit_msg_summary = (head_commit.message or "").split("\n", 1)[0]

            commit_timestamp = datetime.fromtimestamp(head_commit.commit_time, tz=UTC)

            return {
                "head_ref_name": head_ref.shorthand,
                "head_commit_hash": str(head_commit.id),
                "head_commit_message_summary": commit_msg_summary,
                "head_commit_timestamp": commit_timestamp,
            }

        try:
            summary_dict = await asyncio.to_thread(_blocking_get_summary)
            return GitRepoSummary(**summary_dict)
        except pygit2.GitError as e:
            self._log.error("Failed to get Git summary", path=str(working_dir), error=str(e))
            return GitRepoSummary(head_ref_name="ERROR", head_commit_message_summary=str(e))
        except Exception as e:
            self._log.exception("Unexpected error getting Git summary", path=str(working_dir))
            return GitRepoSummary(head_ref_name="ERROR", head_commit_message_summary=f"Unexpected: {e}")

    async def get_status(
        self,
        state: RepositoryState,
        config: dict[str, Any],
        global_config: GlobalConfig,
        working_dir: Path,
    ) -> RepoStatusResult:
        def _blocking_get_status():
            status_log = self._log.bind(repo_id=state.repo_id, path=str(working_dir))
            repo = self.operations.get_repo(working_dir)
            current_branch = "UNBORN" if repo.head_is_unborn else repo.head.shorthand

            if repo.is_bare:
                return {"success": False, "message": "Cannot get status for bare repository"}
            if repo.index.conflicts:
                return {"success": True, "is_conflicted": True, "current_branch": current_branch}

            # Check for special Git states (merge, rebase, cherry-pick, revert)
            git_dir = Path(repo.path)
            is_merge_in_progress = (git_dir / "MERGE_HEAD").exists()
            is_rebase_in_progress = (git_dir / "REBASE_MERGE").exists() or (git_dir / "rebase-apply").exists()
            is_cherry_pick_in_progress = (git_dir / "CHERRY_PICK_HEAD").exists()
            is_revert_in_progress = (git_dir / "REVERT_HEAD").exists()

            # If any special state is detected, return early to prevent auto-commits
            if (
                is_merge_in_progress
                or is_rebase_in_progress
                or is_cherry_pick_in_progress
                or is_revert_in_progress
            ):
                return {
                    "success": True,
                    "current_branch": current_branch,
                    "is_merge_in_progress": is_merge_in_progress,
                    "is_rebase_in_progress": is_rebase_in_progress,
                    "is_cherry_pick_in_progress": is_cherry_pick_in_progress,
                    "is_revert_in_progress": is_revert_in_progress,
                }

            pygit2_status = repo.status()
            has_staged = any(
                s & pygit2.GIT_STATUS_INDEX_NEW
                or s & pygit2.GIT_STATUS_INDEX_MODIFIED
                or s & pygit2.GIT_STATUS_INDEX_DELETED
                or s & pygit2.GIT_STATUS_INDEX_RENAMED
                or s & pygit2.GIT_STATUS_INDEX_TYPECHANGE
                for s in pygit2_status.values()
            )
            has_unstaged = any(
                s & pygit2.GIT_STATUS_WT_MODIFIED
                or s & pygit2.GIT_STATUS_WT_DELETED
                or s & pygit2.GIT_STATUS_WT_TYPECHANGE
                or s & pygit2.GIT_STATUS_WT_RENAMED
                for s in pygit2_status.values()
            )
            has_untracked = any(s & pygit2.GIT_STATUS_WT_NEW for s in pygit2_status.values())
            is_clean = not (has_staged or has_unstaged or has_untracked) and not repo.head_is_unborn

            added_files, deleted_files, modified_files = 0, 0, 0
            if not is_clean:
                for flags in pygit2_status.values():
                    if (flags & pygit2.GIT_STATUS_WT_NEW) or (flags & pygit2.GIT_STATUS_INDEX_NEW):
                        added_files += 1
                    elif (flags & pygit2.GIT_STATUS_WT_DELETED) or (flags & pygit2.GIT_STATUS_INDEX_DELETED):
                        deleted_files += 1
                    elif (
                        (flags & pygit2.GIT_STATUS_WT_MODIFIED)
                        or (flags & pygit2.GIT_STATUS_INDEX_MODIFIED)
                        or (flags & pygit2.GIT_STATUS_WT_RENAMED)
                        or (flags & pygit2.GIT_STATUS_INDEX_RENAMED)
                        or (flags & pygit2.GIT_STATUS_WT_TYPECHANGE)
                        or (flags & pygit2.GIT_STATUS_INDEX_TYPECHANGE)
                    ):
                        modified_files += 1

            changed_files = added_files + deleted_files + modified_files
            total_files = 0
            try:
                if not repo.is_empty and not repo.head_is_unborn:
                    # Count only tracked files (exclude directories)
                    for entry in repo.index:
                        # Skip directories (GIT_FILEMODE_TREE = 0o040000)
                        if entry.mode != pygit2.GIT_FILEMODE_TREE:
                            total_files += 1
            except Exception as e:
                status_log.error(f"Error counting tracked files: {e}")

            # Get ahead/behind counts relative to upstream
            commits_ahead, commits_behind = 0, 0
            has_upstream = False
            upstream_branch = None
            try:
                if not repo.head_is_unborn and not repo.head_is_detached:
                    local_branch = repo.branches.get(current_branch)
                    if local_branch and local_branch.upstream:
                        has_upstream = True
                        upstream_branch = local_branch.upstream.shorthand
                        ahead, behind = repo.ahead_behind(local_branch.target, local_branch.upstream.target)
                        commits_ahead = ahead
                        commits_behind = behind
            except Exception as e:
                status_log.debug(f"Could not get ahead/behind counts: {e}")

            return {
                "success": True,
                "is_clean": is_clean,
                "is_unborn": repo.head_is_unborn,
                "has_staged_changes": has_staged,
                "has_unstaged_changes": has_unstaged,
                "has_untracked_changes": has_untracked,
                "current_branch": current_branch,
                "total_files": total_files,
                "changed_files": changed_files,
                "added_files": added_files,
                "deleted_files": deleted_files,
                "modified_files": modified_files,
                "commits_ahead": commits_ahead,
                "commits_behind": commits_behind,
                "has_upstream": has_upstream,
                "upstream_branch": upstream_branch,
            }

        try:
            status_dict = await asyncio.to_thread(_blocking_get_status)
            return RepoStatusResult(**status_dict)
        except pygit2.GitError as e:
            self._log.error("Failed to get Git status", error=str(e), repo_id=state.repo_id)
            return RepoStatusResult(success=False, message=f"Git status error: {e}")
        except Exception as e:
            self._log.exception("Unexpected status error getting Git status", repo_id=state.repo_id)
            return RepoStatusResult(success=False, message=f"Unexpected status error: {e}")

    async def get_last_commit_stats(
        self,
        state: RepositoryState,
        repository_config: dict[str, Any],
        global_config: dict[str, Any],
        repo_path: Path,
    ) -> dict[str, Any]:
        """Get statistics from the last commit for caching in state.

        Returns:
            Dict with success, commit_hash, added, deleted, modified
        """

        def _blocking_get_commit_stats() -> dict[str, Any]:
            try:
                repo = pygit2.Repository(str(repo_path))

                if repo.is_empty or repo.head_is_unborn:
                    return {
                        "success": True,
                        "commit_hash": None,
                        "added": 0,
                        "deleted": 0,
                        "modified": 0,
                    }

                # Get the last commit
                last_commit = repo.head.peel()
                commit_hash = str(last_commit.id)

                # Check if we need to update cached stats
                if state.cached_last_commit_stats_loaded and state.cached_last_commit_hash == commit_hash:
                    self._log.debug("Using cached commit stats", commit_hash=commit_hash)
                    return {
                        "success": True,
                        "commit_hash": commit_hash,
                        "added": state.last_committed_added,
                        "deleted": state.last_committed_deleted,
                        "modified": state.last_committed_modified,
                    }

                # Get parent commit for diff
                if len(last_commit.parents) == 0:
                    # Initial commit - everything is added
                    added_files = 0
                    try:
                        for entry in last_commit.tree:
                            if entry.type != "tree":  # Skip directories
                                added_files += 1
                    except Exception as e:
                        log.debug("Failed to count added files from commit tree", error=str(e))

                    stats = {
                        "success": True,
                        "commit_hash": commit_hash,
                        "added": added_files,
                        "deleted": 0,
                        "modified": 0,
                    }
                else:
                    # Compare with parent commit
                    parent_commit = last_commit.parents[0]
                    diff = repo.diff(parent_commit.tree, last_commit.tree)

                    added = 0
                    deleted = 0
                    modified = 0

                    for delta in diff.deltas:
                        if delta.status == pygit2.GIT_DELTA_ADDED:
                            added += 1
                        elif delta.status == pygit2.GIT_DELTA_DELETED:
                            deleted += 1
                        elif delta.status == pygit2.GIT_DELTA_MODIFIED:
                            modified += 1

                    stats = {
                        "success": True,
                        "commit_hash": commit_hash,
                        "added": added,
                        "deleted": deleted,
                        "modified": modified,
                    }

                # Cache the stats in state
                state.set_cached_commit_stats(commit_hash, stats["added"], stats["deleted"], stats["modified"])

                self._log.debug(
                    "Loaded commit stats from Git",
                    commit_hash=commit_hash,
                    added=stats["added"],
                    deleted=stats["deleted"],
                    modified=stats["modified"],
                )

                return stats

            except Exception as e:
                self._log.error(f"Unable to get last commit stats: {e}")
                return {"success": False, "error": str(e)}

        try:
            return await asyncio.to_thread(_blocking_get_commit_stats)
        except Exception as e:
            self._log.exception("Unexpected error getting commit stats", repo_id=state.repo_id)
            return {"success": False, "error": str(e)}

    @retry(
        pygit2.GitError,
        OSError,
        policy=RetryPolicy(max_attempts=3, backoff=BackoffStrategy.EXPONENTIAL, base_delay=0.5, max_delay=5.0),
    )
    async def stage_changes(
        self,
        files: list[Path] | None,
        state: RepositoryState,
        config: dict[str, Any],
        global_config: GlobalConfig,
        working_dir: Path,
    ) -> StageResult:
        def _blocking_stage_changes():
            repo = self.operations.get_repo(working_dir)
            index = repo.index
            staged_list = []

            if files:
                repo_root = Path(repo.workdir)
                for f in files:
                    try:
                        # Ensure f is a Path object if it's coming in as a string
                        rel_path = str(Path(f).relative_to(repo_root))
                        index.add(rel_path)
                        staged_list.append(rel_path)
                    except (ValueError, KeyError) as e:
                        # Log a warning if a specific file fails to be staged.
                        self._log.warning(
                            "Could not stage specified file, it may not exist or be outside the repository.",
                            file=str(f),
                            error=str(e),
                            repo_id=state.repo_id,
                        )
            else:
                index.add_all()
                staged_list = [
                    filepath for filepath, flags in repo.status().items() if flags != pygit2.GIT_STATUS_CURRENT
                ]

            index.write()
            return {
                "success": True,
                "files_staged": staged_list,
                "message": f"Successfully staged {len(staged_list)} files",
                "details": {"staged_files": staged_list},
            }

        try:
            result_dict = await asyncio.to_thread(_blocking_stage_changes)
            return StageResult(**result_dict)
        except OSError as e:
            # Handle git lock collisions specifically
            error_msg = str(e)
            if "failed to lock file" in error_msg and ".lock" in error_msg:
                self._log.warning(
                    "Git lock collision during staging - another process is accessing the repository. "
                    "The retry mechanism will handle this automatically.",
                    error=error_msg,
                    repo_id=state.repo_id,
                    working_dir=str(working_dir),
                )
                # Re-raise to trigger retry mechanism
                raise
            else:
                # Other OSError - log and return failure
                self._log.error("OS error during staging", error=error_msg, repo_id=state.repo_id)
                return StageResult(success=False, message=f"OS error: {e}")
        except pygit2.GitError as e:
            self._log.error("Failed to stage changes", error=str(e), repo_id=state.repo_id)
            return StageResult(success=False, message=f"Git staging error: {e}")
        except Exception as e:
            self._log.exception("Unexpected error staging changes", repo_id=state.repo_id)
            return StageResult(success=False, message=f"Unexpected staging error: {e}")

    @retry(
        pygit2.GitError,
        OSError,
        policy=RetryPolicy(
            max_attempts=5, backoff=BackoffStrategy.EXPONENTIAL, base_delay=0.5, max_delay=10.0
        ),
    )
    async def perform_commit(
        self,
        message_template: str,
        state: RepositoryState,
        config: dict[str, Any],
        global_config: GlobalConfig,
        working_dir: Path,
    ) -> CommitResult:
        def _blocking_perform_commit():
            repo = self.operations.get_repo(working_dir)
            repo.index.read(force=True)  # Ensure index is fresh from disk

            is_unborn = repo.head_is_unborn
            diff = None

            if is_unborn:
                # For an unborn repo, any staged file is a change for the initial commit.
                # We create a diff against an empty tree to represent this.
                if len(repo.index) > 0:
                    empty_tree_oid = repo.TreeBuilder().write()
                    diff = repo.index.diff_to_tree(repo[empty_tree_oid])
            else:
                # For an existing repo, diff against the parent commit's tree.
                parent_tree = repo.head.peel().tree
                diff = repo.index.diff_to_tree(parent_tree)

            if not diff:
                return {"success": True, "commit_hash": None, "message": "No changes to commit."}

            try:
                signature = repo.default_signature
            except pygit2.GitError:
                self._log.warning("Git user name/email not configured, using fallback.")
                fallback_name = "Supsrc Automation"
                fallback_email = "supsrc@example.com"
                timestamp = int(datetime.now(UTC).timestamp())
                offset = 0  # UTC
                signature = pygit2.Signature(fallback_name, fallback_email, timestamp, offset)

            change_summary = self.operations.generate_change_summary(diff)
            commit_message_template_str = message_template or self.operations.get_config_value(
                "commit_message_template", config, "🔼⚙️ [skip ci] auto-commit\n\n{{change_summary}}"
            )
            timestamp_str = datetime.now(UTC).isoformat()
            commit_message = (
                commit_message_template_str.replace("{{timestamp}}", timestamp_str)
                .replace("{{repo_id}}", state.repo_id)
                .replace("{{save_count}}", str(state.save_count))
                .replace("{{change_summary}}", change_summary)
                .rstrip()
            )

            parents = [] if is_unborn else [repo.head.target]
            tree = repo.index.write_tree()

            commit_oid = repo.create_commit("HEAD", signature, signature, commit_message, tree, parents)
            return {"success": True, "commit_hash": str(commit_oid)}

        try:
            result_dict = await asyncio.to_thread(_blocking_perform_commit)
            return CommitResult(**result_dict)
        except OSError as e:
            # Handle git lock collisions specifically
            error_msg = str(e)
            if "failed to lock file" in error_msg and ".lock" in error_msg:
                self._log.warning(
                    "Git lock collision - another process is accessing the repository. "
                    "This is typically caused by concurrent git operations. "
                    "The retry mechanism will handle this automatically.",
                    error=error_msg,
                    repo_id=state.repo_id,
                    working_dir=str(working_dir),
                )
                # Re-raise to trigger retry mechanism
                raise
            else:
                # Other OSError - log and return failure
                self._log.error("OS error during commit", error=error_msg, repo_id=state.repo_id)
                return CommitResult(success=False, message=f"OS error: {e}")
        except pygit2.GitError as e:
            self._log.error("Failed to perform commit", error=str(e), repo_id=state.repo_id)
            return CommitResult(success=False, message=f"Git commit error: {e}")
        except Exception as e:
            self._log.exception("Unexpected error performing commit", repo_id=state.repo_id)
            return CommitResult(success=False, message=f"Unexpected commit error: {e}")

    @retry(
        pygit2.GitError,
        OSError,
        ConnectionError,
        TimeoutError,
        policy=RetryPolicy(
            max_attempts=5,  # More retries for network operations
            backoff=BackoffStrategy.EXPONENTIAL,
            base_delay=2.0,
            max_delay=30.0,
        ),
    )
    async def perform_push(
        self,
        state: RepositoryState,
        config: dict[str, Any],
        global_config: GlobalConfig,
        working_dir: Path,
    ) -> PushResult:
        auto_push = self.operations.get_config_value("auto_push", config, False)
        if not auto_push:
            return PushResult(success=True, skipped=True, message="Push disabled by config.")

        remote_name = self.operations.get_config_value("remote", config, "origin")

        def _blocking_perform_push():
            repo = self.operations.get_repo(working_dir)

            if remote_name not in repo.remotes:
                raise ValueError(f"Remote '{remote_name}' not found in repository.")

            branch_name = self.operations.get_config_value("branch", config) or repo.head.shorthand
            remote = repo.remotes[remote_name]
            callbacks = pygit2.RemoteCallbacks(credentials=self._credentials_callback)
            remote.push([f"refs/heads/{branch_name}"], callbacks=callbacks)
            return {"success": True, "remote_name": remote_name, "branch_name": branch_name}

        try:
            result_dict = await asyncio.to_thread(_blocking_perform_push)
            return PushResult(**result_dict)
        except (ValueError, KeyError):
            message = f"Remote '{remote_name}' not found."
            self._log.warning("Push failed: remote not found.", remote_name=remote_name, repo_id=state.repo_id)
            return PushResult(success=False, message=message)
        except pygit2.GitError as e:
            self._log.error("Failed to perform push", error=str(e), repo_id=state.repo_id)
            return PushResult(success=False, message=f"Git push error: {e}")
        except Exception as e:
            self._log.exception("Unexpected error performing push", repo_id=state.repo_id)
            return PushResult(success=False, message=f"Unexpected push error: {e}")

    async def get_commit_history(self, working_dir: Path, limit: int = 10) -> list[str]:
        """Retrieves the last N commit messages from the repository asynchronously."""
        return await self.operations.get_commit_history(working_dir, limit)


# 🔼⚙️🔚
