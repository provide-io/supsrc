# file: src/supsrc/engines/git/base.py
"""
Implementation of the RepositoryEngine protocol using pygit2.
"""

import os
from pathlib import Path
from typing import Optional, Any, Mapping
from datetime import datetime, timezone

import pygit2
import structlog

from supsrc.protocols import (
    RepositoryEngine, RepoStatusResult, StageResult, CommitResult, PushResult
)
from supsrc.state import RepositoryState
from supsrc.config.models import GlobalConfig # For global defaults

# Import Git specific info/runner/exceptions
# --- FIX: Correct the imported function name ---
from .runner import run_pygit2_func
# ---------------------------------------------
from .info import get_git_status, GitRepoStatus, get_git_summary, GitRepoSummary
from .exceptions import (
    GitEngineError, GitCommandError, ConflictError, NoRemoteError,
    PushRejectedError, AuthenticationError, NetworkError
)


log = structlog.get_logger("engines.git.base")

class GitEngine(RepositoryEngine):
    """Implements RepositoryEngine using pygit2."""

    def __init__(self):
        self._log = log.bind(engine_id=id(self))
        self._log.debug("GitEngine initialized")

    async def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to open the repository object."""
        try:
            # Discover upwards from working_dir if needed, or use direct path
            # pygit2.Repository(str(working_dir)) expects working_dir to be repo root or subdir
            repo = await run_pygit2_func(pygit2.Repository, str(working_dir))
            # Verify it's not bare
            if await run_pygit2_func(getattr, repo, 'is_bare'):
                 raise GitEngineError("Repository is bare, cannot perform working directory operations.", repo_path=str(working_dir))
            return repo
        except GitCommandError as e:
            # Intercept error during repo opening specifically
             self._log.error("Failed to open repository", path=str(working_dir), error=str(e.details))
             raise GitEngineError(f"Cannot open Git repository at '{working_dir}'", details=e.details) from e

    # --- Protocol Method Implementations ---

    async def get_status(
        self, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> RepoStatusResult:
        """Check the current status of the Git repository."""
        status_log = self._log.bind(repo_id=state.repo_id)
        try:
            repo = await self._get_repo(working_dir)
            git_status: GitRepoStatus = await get_git_status(repo, working_dir)
            # Optionally enhance the message based on combined status
            if git_status.is_conflicted:
                git_status = attrs.evolve(git_status, message="Repository has merge conflicts.")
            elif not git_status.success:
                 git_status = attrs.evolve(git_status, message=git_status.message or "Failed to get status")
            elif git_status.is_clean:
                 git_status = attrs.evolve(git_status, message="Repository clean.")
            else:
                 parts = []
                 if git_status.has_staged_changes: parts.append("staged")
                 if git_status.has_unstaged_changes: parts.append("unstaged")
                 if git_status.has_untracked_files: parts.append("untracked")
                 git_status = attrs.evolve(git_status, message=f"Changes detected: {', '.join(parts)}.")

            return git_status # Return the specific GitRepoStatus instance

        except GitEngineError as e: # Catch errors from _get_repo
            status_log.error("get_status failed (repo open)", error=str(e))
            return RepoStatusResult(success=False, message=str(e))
        except Exception as e:
            status_log.exception("Unexpected error in get_status")
            return RepoStatusResult(success=False, message=f"Unexpected error: {e}")

    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> StageResult:
        """Stage all changes, equivalent to 'git add .'"""
        stage_log = self._log.bind(repo_id=state.repo_id)
        if files is not None:
            # Current implementation only supports staging all
            stage_log.warning("Specific file staging not implemented, staging all changes.")

        try:
            repo = await self._get_repo(working_dir)
            status_dict: Mapping[str, int] = await run_pygit2_func(repo.status)

            if not status_dict:
                stage_log.info("No changes detected to stage.")
                return StageResult(success=True, message="No changes to stage.")

            repo_index = await run_pygit2_func(getattr, repo, 'index')
            paths_to_add = []
            paths_to_remove = []

            for file_path_rel, flags in status_dict.items():
                 # Stage files that are new, modified, renamed, typechanged in WT
                 if flags & (pygit2.GIT_STATUS_WT_NEW |
                             pygit2.GIT_STATUS_WT_MODIFIED |
                             pygit2.GIT_STATUS_WT_RENAMED | # Stage the new name
                             pygit2.GIT_STATUS_WT_TYPECHANGE):
                      paths_to_add.append(file_path_rel)
                 # Remove files that are deleted in WT
                 elif flags & pygit2.GIT_STATUS_WT_DELETED:
                     paths_to_remove.append(file_path_rel)
                 # Explicitly ignore conflicts here - commit will fail later if still conflicted
                 # Ignore ignored files (should be filtered by status already if gitignored)

            if paths_to_add:
                 stage_log.debug("Adding paths to index", paths=paths_to_add)
                 # Using add_all might fail if some paths are directories; consider iterating
                 # await run_pygit2_func(repo_index.add_all, paths_to_add)
                 for path_to_add in paths_to_add:
                      await run_pygit2_func(repo_index.add, path_to_add)

            if paths_to_remove:
                 stage_log.debug("Removing paths from index", paths=paths_to_remove)
                 # Removing needs iteration
                 for path_to_rm in paths_to_remove:
                     await run_pygit2_func(repo_index.remove, path_to_rm)

            stage_log.debug("Writing index")
            await run_pygit2_func(repo_index.write)
            stage_log.info("Staging successful.")
            return StageResult(success=True, message="Changes staged.")

        except (GitEngineError, GitCommandError) as e:
            stage_log.error("Staging failed", error=str(e))
            return StageResult(success=False, message=f"Staging failed: {e}")
        except Exception as e:
            stage_log.exception("Unexpected error during staging")
            return StageResult(success=False, message=f"Unexpected staging error: {e}")

    async def perform_commit(
        self, message_template: str, # Template lookup now responsibility of engine
        state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with templating."""
        commit_log = self._log.bind(repo_id=state.repo_id)
        try:
            repo = await self._get_repo(working_dir)

            # --- Pre-Checks ---
            status_result = await get_git_status(repo, working_dir)
            if not status_result.success:
                return CommitResult(success=False, message=f"Cannot commit, status check failed: {status_result.message}")
            if status_result.is_conflicted:
                commit_log.warning("Commit skipped: Repository has conflicts.")
                # Raise specific error? Or return failure? Returning failure is safer.
                return CommitResult(success=False, message="Repository has merge conflicts.", details={"conflict": True})
            # Check if there are staged changes? status_result.has_staged_changes

            # --- Determine Parents, Author, Committer ---
            if await run_pygit2_func(getattr, repo, 'head_is_unborn'):
                parents = []
                parent_tree_id = None
                commit_log.debug("Performing initial commit (no parents).")
            else:
                head_commit_oid = await run_pygit2_func(getattr, repo.head, 'target')
                parents = [head_commit_oid]
                parent_commit = await run_pygit2_func(repo.get, head_commit_oid)
                parent_tree_id = await run_pygit2_func(getattr, parent_commit, 'tree_id')
                commit_log.debug("Found parent commit", hash=str(head_commit_oid))

            # Use default signature or create specific ones
            # For simplicity, using default signature associated with repo/global config
            signature = await run_pygit2_func(getattr, repo, 'default_signature')
            if not signature:
                 # Fallback if git config user.name/email isn't set
                 # Using placeholder - ideally raise config error earlier
                 commit_log.warning("Git user.name/email not configured, using placeholder.")
                 signature = pygit2.Signature("supsrc", "supsrc@localhost", int(datetime.now(timezone.utc).timestamp()), 0)

            author = committer = signature

            # --- Process Commit Message Template ---
            final_commit_message: str
            template = config.get('commit_message_template') # Engine config is already specific
            if template is None: # Check explicitly for None, as "" is a valid message
                 template = global_config.default_commit_message
            if not template: template = "supsrc auto-commit: changes detected" # Final fallback

            try:
                # Gather context data
                context = {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    "save_count": state.save_count,
                    "repo_id": state.repo_id,
                    "trigger_type": config.get('rule',{}).get('type', 'unknown') # Access nested dict safely
                    # Add hostname, etc. if needed
                    # "hostname": os.uname().nodename
                }
                # Basic templating - replace with more robust engine if needed (e.g., Jinja2)
                final_commit_message = template
                for key, value in context.items():
                     final_commit_message = final_commit_message.replace(f"{{{{{key}}}}}", str(value))

            except Exception as tmpl_exc:
                 commit_log.error("Failed to render commit message template", template=template, error=str(tmpl_exc))
                 final_commit_message = f"supsrc auto-commit: Error rendering template - {tmpl_exc}"


            # --- Create Tree and Check for Empty Commit ---
            repo_index = await run_pygit2_func(getattr, repo, 'index')
            # Must read index state *after* staging changes
            await run_pygit2_func(repo_index.read)
            current_tree_id = await run_pygit2_func(repo_index.write_tree)

            if parent_tree_id is not None and current_tree_id == parent_tree_id:
                commit_log.info("Commit skipped: No effective changes staged.")
                return CommitResult(success=True, commit_hash=None, message="No changes to commit.")

            # --- Create Commit ---
            commit_log.debug("Creating commit object", tree=str(current_tree_id), parents=[str(p) for p in parents])
            commit_oid = await run_pygit2_func(
                repo.create_commit,
                'HEAD',          # Reference to update (HEAD)
                author,          # Author signature
                committer,       # Committer signature
                final_commit_message, # The commit message
                current_tree_id, # The tree OID
                parents          # List of parent commit OIDs
            )
            commit_log.info("Commit successful", hash=str(commit_oid))
            return CommitResult(success=True, commit_hash=str(commit_oid))

        except (GitEngineError, GitCommandError, ConflictError) as e:
            commit_log.error("Commit failed", error=str(e))
            return CommitResult(success=False, message=f"Commit failed: {e}", details=getattr(e,'details', None))
        except Exception as e:
            commit_log.exception("Unexpected error during commit")
            return CommitResult(success=False, message=f"Unexpected commit error: {e}")

    async def perform_push(
        self, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> PushResult:
        """Perform the push action to the configured remote."""
        push_log = self._log.bind(repo_id=state.repo_id)

        # --- Check if push is enabled ---
        # Precedence: repo config -> global config -> default (True in GlobalConfig model)
        auto_push = config.get('auto_push', global_config.default_auto_push)
        if not auto_push:
            push_log.info("Push skipped by configuration.")
            return PushResult(success=True, message="Push skipped by configuration")

        try:
            repo = await self._get_repo(working_dir)

            # --- Get Remote ---
            remote_name = config.get('remote', 'origin') # Default to origin
            push_log.debug("Attempting push", remote=remote_name)
            try:
                remote = await run_pygit2_func(repo.remotes.__getitem__, remote_name) # Use getitem for lookup
            except KeyError:
                raise NoRemoteError(f"Remote '{remote_name}' not found in repository.", repo_path=str(working_dir))
            except GitCommandError as e: # Catch errors getting remote list etc.
                 raise GitEngineError(f"Failed to access remotes: {e.details}", repo_path=str(working_dir), details=e.details) from e

            # --- Get Refspec (Current Branch) ---
            if await run_pygit2_func(getattr, repo, 'head_is_unborn'):
                 return PushResult(success=False, message="Cannot push: Repository has no commits yet.")
            if await run_pygit2_func(getattr, repo, 'head_is_detached'):
                 return PushResult(success=False, message="Cannot push: HEAD is detached.")

            head_ref = await run_pygit2_func(getattr, repo, 'head')
            ref_name = getattr(head_ref, 'name', None) # Get full ref name e.g., 'refs/heads/main'
            if not ref_name or not ref_name.startswith('refs/heads/'):
                return PushResult(success=False, message=f"Cannot push: HEAD is not on a local branch ('{ref_name}').")

            refspec = f"{ref_name}:{ref_name}" # Push current branch to remote branch of same name

            # --- Perform Push (Simplified - No Callbacks for Preview) ---
            push_log.info(f"Pushing {refspec} to {remote_name}...")
            # For a preview, rely on existing credential helpers (SSH keys, OS store)
            # Providing callbacks for auth is complex and often environment specific.
            await run_pygit2_func(remote.push, [refspec], callbacks=None)

            push_log.info("Push successful.")
            return PushResult(success=True, message="Push successful.")

        except (GitEngineError, GitCommandError, NoRemoteError) as e:
            push_log.error("Push failed", error=str(e), remote=config.get('remote', 'origin'))
            # Try to categorize common GitErrors from push
            details = getattr(e, 'details', None)
            detail_msg = str(details).lower() if details else ""
            if isinstance(e, NoRemoteError): pass # Already specific
            elif "authentication required" in detail_msg or "auth" in detail_msg:
                e = AuthenticationError("Authentication failed during push.", repo_path=str(working_dir), details=details)
            elif "failed to connect" in detail_msg or "could not resolve host" in detail_msg or "network is unreachable" in detail_msg:
                 e = NetworkError("Network error during push.", repo_path=str(working_dir), details=details)
            elif "rejected" in detail_msg or "non-fast-forward" in detail_msg:
                e = PushRejectedError("Push rejected by remote (likely requires pull/rebase).", repo_path=str(working_dir), details=details)

            return PushResult(success=False, message=f"Push failed: {e}")
        except Exception as e:
            push_log.exception("Unexpected error during push")
            return PushResult(success=False, message=f"Unexpected push error: {e}")

    # --- Optional: Add get_summary if Orchestrator needs it directly ---
    async def get_summary(self, working_dir: Path) -> GitRepoSummary:
        """ Convenience method to call get_git_summary. """
        return await get_git_summary(working_dir)
# 🔼⚙️
