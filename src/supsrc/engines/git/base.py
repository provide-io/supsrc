#
# engines/git/base.py
#
"""
Main GitEngine class implementing the RepositoryEngine protocol using pygit2.
"""

from pathlib import Path
from typing import Any, Optional, cast, TypeAlias, List # Use List for Python <3.9 compat if needed, else list
import pygit2 # type: ignore[import-untyped]
import attrs
import structlog

# Use relative imports within the engine package
from .runner import run_pygit2_async
from .errors import GitEngineError, GitRemoteError, GitCommitError, GitPushError, GitStageError, GitStatusError # Import all relevant errors
from .status import get_git_status
from .stage import stage_git_changes
from .commit import perform_git_commit
from .push import perform_git_push
from .info import get_git_summary, GitRepoSummary # Import new function and result type

# Use absolute imports for protocols and core types
from supsrc.protocols import (
    RepositoryEngine, # Implement this protocol
    RepoStatusResult, StageResult, CommitResult, PushResult, PluginResult
)
from supsrc.state import RepositoryState
from supsrc.telemetry import StructLogger # Assuming telemetry provides this type hint

log: StructLogger = structlog.get_logger("engines.git.base")

GitEngineConfig: TypeAlias = dict[str, Any]

@attrs.define(slots=True, auto_attribs=True) # Using attrs.define for potential future state
class GitEngine(RepositoryEngine):
    """
    RepositoryEngine implementation using pygit2 for Git operations.
    """

    # Add attributes if the engine needs state, otherwise keep it simple
    # Example: default_committer: Optional[pygit2.Signature] = None

    def __attrs_post_init__(self):
        # Post-initialization hook if needed
        log.debug("GitEngine initialized", engine_id=id(self))

    async def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to safely open the pygit2 repository object."""
        log.debug("Attempting to open repository", path=str(working_dir))
        try:
            # Ensure working_dir exists before passing to pygit2
            if not working_dir.is_dir():
                 raise GitEngineError(f"Working directory does not exist or is not a directory: {working_dir}")

            # pygit2.Repository expects the path to the .git dir or the worktree root
            repo = await run_pygit2_async(pygit2.Repository, str(working_dir))
            # Log details after successful opening
            repo_path = getattr(repo, 'path', 'N/A') # Path to .git dir
            repo_workdir = getattr(repo, 'workdir', 'N/A') # Path to worktree root
            log.debug("Opened repository object successfully", repo_path=repo_path, workdir=repo_workdir)
            return repo
        except pygit2.GitError as e:
            # More specific error for common case
            if "repository not found" in str(e).lower():
                 raise GitEngineError(f"Not a git repository (or unable to find .git): '{working_dir}'", repo_path=str(working_dir), details=e) from e
            raise GitEngineError(f"Failed to open repository at '{working_dir}': {e}", repo_path=str(working_dir), details=e) from e
        except Exception as e:
             # Catch other unexpected errors during repo opening
             log.error("Unexpected error opening repository", path=str(working_dir), error=str(e), exc_info=True)
             raise GitEngineError(f"Unexpected error opening repository at '{working_dir}': {e}", repo_path=str(working_dir), details=e) from e

    async def get_summary(
        self, working_dir: Path
    ) -> GitRepoSummary:
        """Retrieves summary information (HEAD commit/message) for the repository."""
        try:
            repo = await self._get_repo(working_dir)
            return await get_git_summary(repo, working_dir)
        except GitEngineError as e:
            # Log the error but return a summary indicating failure
            log.error("Failed to get repository summary", repo_path=str(working_dir), error=str(e))
            # Provide specific error details if possible
            return GitRepoSummary(is_empty=False, head_ref_name=f"ERROR: {e}")
        except Exception as e:
            log.critical("Unexpected error in get_summary", error=str(e), exc_info=True)
            return GitRepoSummary(is_empty=False, head_ref_name=f"UNEXPECTED_ERROR: {e}")

    async def get_status(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> RepoStatusResult:
        """Check the current status of the repository."""
        # repo_config = cast(GitEngineConfig, config) # If needed
        log.debug("Engine get_status called", repo_id=state.repo_id)
        try:
            repo = await self._get_repo(working_dir)
            return await get_git_status(repo, working_dir)
        except GitEngineError as e:
            # Catch errors from _get_repo or get_git_status
            log.error("get_status failed due to GitEngineError", repo_id=state.repo_id, error=str(e))
            return RepoStatusResult(success=False, message=str(e), is_clean=None, has_staged_changes=None, has_unstaged_changes=None)
        except Exception as e:
            log.critical("Unexpected error in get_status", repo_id=state.repo_id, error=str(e), exc_info=True)
            return RepoStatusResult(success=False, message=f"Unexpected error: {e}", is_clean=None, has_staged_changes=None, has_unstaged_changes=None)

    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        repo_config = cast(GitEngineConfig, config)
        log.debug("Engine stage_changes called", repo_id=state.repo_id, files_count=len(files) if files else 'all')
        try:
            repo = await self._get_repo(working_dir)
            return await stage_git_changes(repo, working_dir, files)
        except GitEngineError as e:
            log.error("stage_changes failed due to GitEngineError", repo_id=state.repo_id, error=str(e))
            return StageResult(success=False, message=str(e))
        except Exception as e:
            log.critical("Unexpected error in stage_changes", repo_id=state.repo_id, error=str(e), exc_info=True)
            return StageResult(success=False, message=f"Unexpected error: {e}")

    async def perform_commit(
        self, message_template: str, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with the given message."""
        repo_config = cast(GitEngineConfig, config)
        # Get template from engine config, provide a sensible default if missing
        template = repo_config.get("commit_message_template", "supsrc auto-commit: {{timestamp}}")
        log.debug("Engine perform_commit called", repo_id=state.repo_id, template=template)
        try:
            repo = await self._get_repo(working_dir)
            # Pass the specific repo_config dict to the commit function
            return await perform_git_commit(repo, working_dir, template, state, repo_config)
        except GitEngineError as e:
            log.error("perform_commit failed due to GitEngineError", repo_id=state.repo_id, error=str(e))
            return CommitResult(success=False, message=str(e), commit_hash=None)
        except Exception as e:
            log.critical("Unexpected error in perform_commit", repo_id=state.repo_id, error=str(e), exc_info=True)
            return CommitResult(success=False, message=f"Unexpected error: {e}", commit_hash=None)

    async def perform_push(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> PushResult:
        """Perform the push action, respecting the auto_push config."""
        repo_config = cast(GitEngineConfig, config)
        log.debug("Engine perform_push called", repo_id=state.repo_id)

        # Check auto_push setting from engine config
        should_push = repo_config.get("auto_push", False)
        if not isinstance(should_push, bool):
             log.warning("Invalid 'auto_push' value in config, expected boolean, defaulting to false.",
                         value=should_push, repo_id=state.repo_id)
             should_push = False

        if not should_push:
            log.info("Auto-push disabled in configuration, skipping push.", repo_id=state.repo_id)
            return PushResult(success=True, message="Auto-push disabled, push skipped.")

        # Proceed with push only if auto_push was true
        log.info("Auto-push enabled, proceeding with push.", repo_id=state.repo_id)
        remote_name = repo_config.get("remote", "origin")
        branch_name: Optional[str] = None

        try:
            repo = await self._get_repo(working_dir)
            try:
                 # Attempt to get current branch name from HEAD
                 branch_name = await run_pygit2_async(lambda: repo.head.shorthand)
                 log.debug("Determined current branch for push from HEAD", branch=branch_name, repo_id=state.repo_id)
            except pygit2.GitError as head_error:
                 log.warning("Could not determine current branch from HEAD, checking config.", repo_id=state.repo_id, error=str(head_error))
                 branch_name = repo_config.get("branch") # Check engine config
                 if not branch_name:
                      # Fallback if not in config either
                      default_branch = "main" # Common default
                      log.warning(f"Branch not specified in config, defaulting to '{default_branch}'.", repo_id=state.repo_id)
                      branch_name = default_branch

            if not branch_name: # Should be set by now, but safety check
                 raise GitRemoteError("Could not determine branch to push.", repo_path=str(working_dir))

            # Pass the specific repo_config dict to the push function for potential credential hints etc.
            return await perform_git_push(repo, working_dir, remote_name, branch_name, repo_config)

        except GitEngineError as e:
            # Catch errors from _get_repo or perform_git_push
            log.error("perform_push failed due to GitEngineError", repo_id=state.repo_id, error=str(e))
            return PushResult(success=False, message=str(e))
        except Exception as e:
            log.critical("Unexpected error in perform_push", repo_id=state.repo_id, error=str(e), exc_info=True)
            return PushResult(success=False, message=f"Unexpected error: {e}")

# 🔼⚙️
