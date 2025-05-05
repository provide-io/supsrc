#
# engines/git/base.py
#
"""
Implementation of the RepositoryEngine protocol using pygit2.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

import pygit2
import structlog

# Use absolute imports
from supsrc.protocols import (
    RepositoryEngine, RepoStatusResult, StageResult, CommitResult, PushResult
)
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.config.models import GlobalConfig
from supsrc.engines.git.info import GitRepoSummary

log = structlog.get_logger("engines.git.base")

class GitEngine(RepositoryEngine):
    """Implements RepositoryEngine using pygit2."""

    def __init__(self) -> None:
        self._log = log.bind(engine_id=id(self))
        self._log.debug("GitEngine initialized")

    def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to get the pygit2 Repository object."""
        try:
            # Discover the repository path from the working directory
            repo_path = pygit2.discover_repository(str(working_dir))
            if not repo_path:
                raise pygit2.GitError(f"Not a Git repository (or any of the parent directories): {working_dir}")
            # Open the repository
            repo = pygit2.Repository(repo_path)
            return repo
        except pygit2.GitError as e:
            self._log.error("Failed to open Git repository", path=str(working_dir), error=str(e))
            raise # Re-raise to be caught by the calling method

    def _get_config_value(self, key: str, config: dict[str, Any], default: Any = None) -> Any:
        """Safely gets a value from the engine-specific config dict."""
        return config.get(key, default)

    async def get_summary(self, working_dir: Path) -> GitRepoSummary:
        """Gets a summary of the repository's HEAD state."""
        try:
            repo = self._get_repo(working_dir)
            if repo.is_empty:
                return GitRepoSummary(is_empty=True)
            if repo.head_is_unborn:
                return GitRepoSummary(head_ref_name="UNBORN")

            head_ref = repo.head
            head_commit = head_ref.peel() # Peel to get the commit object
            commit_msg_summary = (head_commit.message or "").split('\n', 1)[0]

            return GitRepoSummary(
                head_ref_name=head_ref.shorthand,
                head_commit_hash=str(head_commit.id),
                head_commit_message_summary=commit_msg_summary
            )
        except pygit2.GitError as e:
            self._log.error("Failed to get Git summary", path=str(working_dir), error=str(e))
            # Return a summary indicating an error state or re-raise?
            # For now, let's return a minimal summary indicating failure.
            return GitRepoSummary(head_ref_name="ERROR", head_commit_message_summary=str(e))
        except Exception as e:
            self._log.exception("Unexpected error getting Git summary", path=str(working_dir))
            return GitRepoSummary(head_ref_name="ERROR", head_commit_message_summary=f"Unexpected: {e}")


    async def get_status(
        self, state: RepositoryState, config: dict[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> RepoStatusResult:
        status_log = self._log.bind(repo_id=state.repo_id, path=str(working_dir))
        status_log.debug("Getting repository status...")
        try:
            repo = self._get_repo(working_dir)
            if repo.head_is_unborn:
                status_log.info("Repository has unborn HEAD.")
                # Check for staged/unstaged changes even if unborn
                pygit2_status = repo.status()
                has_staged = any(
                    s & pygit2.GIT_STATUS_INDEX_NEW or
                    s & pygit2.GIT_STATUS_INDEX_MODIFIED or
                    s & pygit2.GIT_STATUS_INDEX_DELETED or
                    s & pygit2.GIT_STATUS_INDEX_RENAMED or
                    s & pygit2.GIT_STATUS_INDEX_TYPECHANGE
                    for s in pygit2_status.values()
                )
                has_unstaged = any(
                    s & pygit2.GIT_STATUS_WT_MODIFIED or
                    s & pygit2.GIT_STATUS_WT_DELETED or
                    s & pygit2.GIT_STATUS_WT_TYPECHANGE or
                    s & pygit2.GIT_STATUS_WT_RENAMED
                    for s in pygit2_status.values()
                )
                has_untracked = any(s & pygit2.GIT_STATUS_WT_NEW for s in pygit2_status.values())
                is_clean = not (has_staged or has_unstaged or has_untracked)

                return RepoStatusResult(
                    success=True,
                    is_unborn=True,
                    is_clean=is_clean,
                    has_staged_changes=has_staged,
                    has_unstaged_changes=has_unstaged,
                    has_untracked_changes=has_untracked,
                    current_branch="UNBORN"
                )

            if repo.is_bare:
                 status_log.warning("Cannot get status for bare repository.")
                 return RepoStatusResult(success=False, message="Cannot get status for bare repository")

            # Check for conflicts
            if repo.index.conflicts:
                 status_log.warning("Repository has merge conflicts.")
                 return RepoStatusResult(success=True, is_conflicted=True, current_branch=repo.head.shorthand)

            pygit2_status = repo.status()
            if not pygit2_status:
                 status_log.debug("Repository is clean.")
                 return RepoStatusResult(success=True, is_clean=True, current_branch=repo.head.shorthand)

            # Check specific statuses
            has_staged = any(
                s & pygit2.GIT_STATUS_INDEX_NEW or
                s & pygit2.GIT_STATUS_INDEX_MODIFIED or
                s & pygit2.GIT_STATUS_INDEX_DELETED or
                s & pygit2.GIT_STATUS_INDEX_RENAMED or
                s & pygit2.GIT_STATUS_INDEX_TYPECHANGE
                for s in pygit2_status.values()
            )
            has_unstaged = any(
                s & pygit2.GIT_STATUS_WT_MODIFIED or
                s & pygit2.GIT_STATUS_WT_DELETED or
                s & pygit2.GIT_STATUS_WT_TYPECHANGE or
                s & pygit2.GIT_STATUS_WT_RENAMED
                for s in pygit2_status.values()
            )
            has_untracked = any(s & pygit2.GIT_STATUS_WT_NEW for s in pygit2_status.values())

            status_log.debug("Repository has changes", staged=has_staged, unstaged=has_unstaged, untracked=has_untracked)
            return RepoStatusResult(
                success=True,
                is_clean=False,
                has_staged_changes=has_staged,
                has_unstaged_changes=has_unstaged,
                has_untracked_changes=has_untracked,
                current_branch=repo.head.shorthand
            )

        except pygit2.GitError as e:
            status_log.error("Failed to get Git status", error=str(e))
            return RepoStatusResult(success=False, message=f"Git status error: {e}")
        except Exception as e:
            status_log.exception("Unexpected error getting Git status")
            return RepoStatusResult(success=False, message=f"Unexpected status error: {e}")

    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: dict[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> StageResult:
        stage_log = self._log.bind(repo_id=state.repo_id, path=str(working_dir))
        stage_log.info("Staging changes...")
        try:
            repo = self._get_repo(working_dir)
            index = repo.index
            staged_list = []

            if files: # Stage specific files (relative paths needed)
                repo_root = Path(repo.workdir)
                relative_files = []
                for f in files:
                    try:
                        rel_path = str(f.relative_to(repo_root))
                        relative_files.append(rel_path)
                        index.add(rel_path)
                        staged_list.append(rel_path)
                    except ValueError:
                         stage_log.warning("File path not relative to repo root, cannot stage individually", file=str(f))
                    except KeyError:
                         stage_log.warning("File not found in repository index, skipping staging", file=str(f)) # File might have been deleted
            else: # Stage all changes
                # Get status to determine what to add/remove
                status = repo.status()
                files_to_add = []
                files_to_remove = []
                for filepath, flags in status.items():
                    if flags & pygit2.GIT_STATUS_WT_DELETED or flags & pygit2.GIT_STATUS_INDEX_DELETED:
                        files_to_remove.append(filepath)
                    elif flags & pygit2.GIT_STATUS_WT_NEW or flags & pygit2.GIT_STATUS_INDEX_NEW \
                      or flags & pygit2.GIT_STATUS_WT_MODIFIED or flags & pygit2.GIT_STATUS_INDEX_MODIFIED \
                      or flags & pygit2.GIT_STATUS_WT_RENAMED or flags & pygit2.GIT_STATUS_INDEX_RENAMED \
                      or flags & pygit2.GIT_STATUS_WT_TYPECHANGE or flags & pygit2.GIT_STATUS_INDEX_TYPECHANGE:
                        files_to_add.append(filepath)

                if files_to_add:
                     stage_log.debug("Adding files to index", files=files_to_add)
                     index.add_all(files_to_add)
                     staged_list.extend(files_to_add)
                if files_to_remove:
                     stage_log.debug("Removing files from index", files=files_to_remove)
                     index.remove_all(files_to_remove)
                     # Note: removed files aren't typically listed as "staged" in the result

            index.write()
            stage_log.info("Staging successful", files_staged=staged_list)
            return StageResult(success=True, message="Changes staged successfully.", files_staged=staged_list)

        except pygit2.GitError as e:
            stage_log.error("Failed to stage changes", error=str(e))
            return StageResult(success=False, message=f"Git staging error: {e}")
        except Exception as e:
            stage_log.exception("Unexpected error staging changes")
            return StageResult(success=False, message=f"Unexpected staging error: {e}")

    async def perform_commit(
        self, message_template: str, state: RepositoryState, config: dict[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> CommitResult:
        commit_log = self._log.bind(repo_id=state.repo_id, path=str(working_dir))
        commit_log.info("Performing commit...")
        try:
            repo = self._get_repo(working_dir)
            index = repo.index

            # Check for changes between HEAD tree and index
            try:
                 if repo.head_is_unborn:
                      diff = index.diff_to_tree(None) # Diff index against empty tree
                 else:
                      head_commit = repo.head.peel()
                      diff = index.diff_to_tree(head_commit.tree)
            except pygit2.GitError as diff_err:
                 commit_log.warning("Could not diff index to HEAD tree, assuming changes exist", error=str(diff_err))
                 diff = True # Assume changes if diff fails

            if not diff:
                commit_log.info("Commit skipped: No changes staged.")
                return CommitResult(success=True, message="Commit skipped: No changes staged.", commit_hash=None)

            # Determine author/committer
            try:
                 signature = repo.default_signature # Use configured Git name/email
            except pygit2.GitError:
                 commit_log.warning("Git user name/email not configured, using fallback.")
                 # Fallback - consider making this configurable
                 fallback_name = "Supsrc Automation"
                 fallback_email = "supsrc@example.com"
                 timestamp = int(datetime.now(timezone.utc).timestamp())
                 offset = 0 # UTC
                 signature = pygit2.Signature(fallback_name, fallback_email, timestamp, offset)

            # Build commit message
            commit_message_template = self._get_config_value(
                "commit_message_template", config, "supsrc auto-commit: {{timestamp}}"
            )
            timestamp_str = datetime.now(timezone.utc).isoformat()
            # Basic templating - consider a more robust library if needed
            commit_message = commit_message_template.replace("{{timestamp}}", timestamp_str)
            commit_message = commit_message.replace("{{repo_id}}", state.repo_id)
            commit_message = commit_message.replace("{{save_count}}", str(state.save_count))

            # Determine parents
            parents = []
            if not repo.head_is_unborn:
                parents.append(repo.head.target)

            # Create tree and commit
            tree_oid = index.write_tree()
            commit_oid = repo.create_commit(
                "HEAD",          # Update reference
                signature,       # Author
                signature,       # Committer
                commit_message,
                tree_oid,
                parents
            )
            commit_hash = str(commit_oid)
            commit_log.info("Commit successful", hash=commit_hash, message=commit_message.split('\n',1)[0])
            return CommitResult(success=True, message=f"Commit successful: {commit_hash[:7]}", commit_hash=commit_hash)

        except pygit2.GitError as e:
            commit_log.error("Failed to perform commit", error=str(e))
            return CommitResult(success=False, message=f"Git commit error: {e}")
        except Exception as e:
            commit_log.exception("Unexpected error performing commit")
            return CommitResult(success=False, message=f"Unexpected commit error: {e}")

    async def perform_push(
        self, state: RepositoryState, config: dict[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> PushResult:
        push_log = self._log.bind(repo_id=state.repo_id, path=str(working_dir))

        auto_push = self._get_config_value("auto_push", config, False) # Default to False if not specified
        if not auto_push:
            push_log.info("Push skipped (disabled by configuration).")
            return PushResult(success=True, message="Push skipped (disabled).", skipped=True)

        remote_name = self._get_config_value("remote", config, "origin")
        branch_name = self._get_config_value("branch", config, None) # Get configured branch

        push_log.info(f"Performing push to remote '{remote_name}'...")
        try:
            repo = self._get_repo(working_dir)
            if repo.head_is_unborn:
                 push_log.warning("Cannot push unborn HEAD.")
                 return PushResult(success=False, message="Cannot push unborn HEAD.", remote_name=remote_name)

            # Determine branch to push if not explicitly configured
            if not branch_name:
                try:
                     branch_name = repo.head.shorthand
                     push_log.debug(f"Using current branch '{branch_name}' for push.")
                except pygit2.GitError:
                     push_log.error("Could not determine current branch name for push.")
                     return PushResult(success=False, message="Could not determine current branch name.", remote_name=remote_name)

            remote = repo.remotes[remote_name]
            refspec = f"refs/heads/{branch_name}"

            # --- TODO: Add Credentials Callback Handling ---
            # credentials_callback = ... # Implement callback based on config/env vars
            # remote.push([refspec], callbacks=pygit2.RemoteCallbacks(credentials=credentials_callback))
            # ---------------------------------------------

            # Simple push without credentials for now
            remote.push([refspec])

            push_log.info(f"Push successful to {remote_name}/{branch_name}.")
            return PushResult(success=True, message=f"Push successful to {remote_name}/{branch_name}.", remote_name=remote_name, branch_name=branch_name)

        except KeyError:
            push_log.error(f"Remote '{remote_name}' not found.")
            return PushResult(success=False, message=f"Remote '{remote_name}' not found.", remote_name=remote_name)
        except pygit2.GitError as e:
            push_log.error("Failed to perform push", error=str(e))
            # Provide more specific messages for common errors if possible
            if "authentication required" in str(e).lower():
                 msg = "Git push error: Authentication failed."
            elif "could not resolve host" in str(e).lower():
                 msg = "Git push error: Network error or invalid remote."
            elif "rejected" in str(e).lower():
                 msg = "Git push error: Push rejected (likely non-fast-forward)."
            else:
                 msg = f"Git push error: {e}"
            return PushResult(success=False, message=msg, remote_name=remote_name, branch_name=branch_name)
        except Exception as e:
            push_log.exception("Unexpected error performing push")
            return PushResult(success=False, message=f"Unexpected push error: {e}", remote_name=remote_name, branch_name=branch_name)

# 🔼⚙️
