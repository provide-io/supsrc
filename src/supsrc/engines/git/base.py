# src/supsrc/engines/git/base.py

"""
Implementation of the RepositoryEngine protocol using pygit2.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygit2
import structlog

# Add Foundation resilience patterns for Git operations
from provide.foundation.resilience import BackoffStrategy, RetryPolicy, retry

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

log = structlog.get_logger("engines.git.base")


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
            return GitRepoSummary(
                head_ref_name="ERROR", head_commit_message_summary=f"Unexpected: {e}"
            )

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
                    elif (flags & pygit2.GIT_STATUS_WT_DELETED) or (
                        flags & pygit2.GIT_STATUS_INDEX_DELETED
                    ):
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
                    total_files = len(repo.index)
            except Exception as e:
                status_log.error(f"Error counting files: {e}")

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
            }

        try:
            status_dict = await asyncio.to_thread(_blocking_get_status)
            return RepoStatusResult(**status_dict)  # type: ignore[misc]
        except pygit2.GitError as e:
            self._log.error("Failed to get Git status", error=str(e), repo_id=state.repo_id)
            return RepoStatusResult(success=False, message=f"Git status error: {e}")
        except Exception as e:
            self._log.exception("Unexpected status error getting Git status", repo_id=state.repo_id)
            return RepoStatusResult(success=False, message=f"Unexpected status error: {e}")

    @retry(
        pygit2.GitError,
        OSError,
        policy=RetryPolicy(
            max_attempts=3, backoff=BackoffStrategy.EXPONENTIAL, base_delay=0.5, max_delay=5.0
        ),
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
                    filepath
                    for filepath, flags in repo.status().items()
                    if flags != pygit2.GIT_STATUS_CURRENT
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
            return StageResult(**result_dict)  # type: ignore[misc]
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
            max_attempts=3, backoff=BackoffStrategy.EXPONENTIAL, base_delay=1.0, max_delay=10.0
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

            commit_oid = repo.create_commit(
                "HEAD", signature, signature, commit_message, tree, parents
            )
            return {"success": True, "commit_hash": str(commit_oid)}

        try:
            result_dict = await asyncio.to_thread(_blocking_perform_commit)
            return CommitResult(**result_dict)  # type: ignore[misc]
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
            return PushResult(**result_dict)  # type: ignore[misc]
        except (ValueError, KeyError):
            message = f"Remote '{remote_name}' not found."
            self._log.warning(
                "Push failed: remote not found.", remote_name=remote_name, repo_id=state.repo_id
            )
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


# 🔼⚙️
