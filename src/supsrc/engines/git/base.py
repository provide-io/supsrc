#
# engines/git/base.py
#
"""
Main GitEngine class implementing the RepositoryEngine protocol using pygit2.
"""

from pathlib import Path
from typing import Any, Optional, cast # Added cast for type hinting clarity
import pygit2 # type: ignore[import-untyped]
import attrs
import structlog

from supsrc.protocols import (
    RepositoryEngine, # Implement this protocol
    RepoStatusResult, StageResult, CommitResult, PushResult, PluginResult
)
from supsrc.state import RepositoryState
from .runner import run_pygit2_async
from .errors import GitEngineError, GitRemoteError # Import custom errors
from .status import get_git_status
from .stage import stage_git_changes
from .commit import perform_git_commit
from .push import perform_git_push

log = structlog.get_logger("engines.git.base")

# Define a type alias for the engine-specific config dictionary for clarity
GitEngineConfig: TypeAlias = dict[str, Any]

# Consider adding @attrs.define if the engine needs its own state later
class GitEngine(RepositoryEngine):
    """
    RepositoryEngine implementation using pygit2 for Git operations.
    """

    def __init__(self):
        log.debug("GitEngine initialized")
        pass

    async def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to safely open the pygit2 repository object."""
        try:
            repo = await run_pygit2_async(pygit2.Repository, str(working_dir))
            log.debug("Opened repository object", path=repo.path, workdir=repo.workdir)
            return repo
        except pygit2.GitError as e:
            raise GitEngineError(f"Failed to open repository at '{working_dir}': {e}", repo_path=str(working_dir), details=e) from e
        except Exception as e:
             raise GitEngineError(f"Unexpected error opening repository at '{working_dir}': {e}", repo_path=str(working_dir), details=e) from e


    async def get_status(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> RepoStatusResult:
        """Check the current status of the repository."""
        # repo_config = cast(GitEngineConfig, config) # Cast for type checking if needed
        try:
            repo = await self._get_repo(working_dir)
            return await get_git_status(repo, working_dir)
        except GitEngineError as e:
            return RepoStatusResult(success=False, message=str(e), is_clean=None, has_staged_changes=None, has_unstaged_changes=None)
        except Exception as e:
            log.critical("Unexpected error in get_status", error=str(e), exc_info=True)
            return RepoStatusResult(success=False, message=f"Unexpected error: {e}", is_clean=None, has_staged_changes=None, has_unstaged_changes=None)


    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        # repo_config = cast(GitEngineConfig, config)
        try:
            repo = await self._get_repo(working_dir)
            return await stage_git_changes(repo, working_dir, files)
        except GitEngineError as e:
            return StageResult(success=False, message=str(e))
        except Exception as e:
            log.critical("Unexpected error in stage_changes", error=str(e), exc_info=True)
            return StageResult(success=False, message=f"Unexpected error: {e}")

    async def perform_commit(
        self, message_template: str, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with the given message."""
        repo_config = cast(GitEngineConfig, config) # Cast config to dict for easier access
        # Get template from config, provide default if missing
        template = repo_config.get("commit_message_template", "supsrc auto-commit: {{timestamp}}")
        try:
            repo = await self._get_repo(working_dir)
            # Pass the specific repo_config dict to the commit function
            return await perform_git_commit(repo, working_dir, template, state, repo_config)
        except GitEngineError as e:
            return CommitResult(success=False, message=str(e), commit_hash=None)
        except Exception as e:
            log.critical("Unexpected error in perform_commit", error=str(e), exc_info=True)
            return CommitResult(success=False, message=f"Unexpected error: {e}", commit_hash=None)


    async def perform_push(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> PushResult:
        """Perform the push action, respecting the auto_push config."""
        repo_config = cast(GitEngineConfig, config) # Cast config to dict

        # --- Check auto_push setting from config ---
        # Default to False if not specified
        should_push = repo_config.get("auto_push", False)
        if not isinstance(should_push, bool):
             log.warning("Invalid 'auto_push' value in config, expected boolean, defaulting to false.",
                         value=should_push, repo_path=str(working_dir))
             should_push = False

        if not should_push:
            log.info("Auto-push disabled in configuration, skipping push.", repo_path=str(working_dir))
            # Return success because skipping push isn't an error in this context
            return PushResult(success=True, message="Auto-push disabled, push skipped.")
        # --- End check ---

        # Proceed with push only if auto_push was true
        log.info("Auto-push enabled, proceeding with push.", repo_path=str(working_dir))
        remote_name = repo_config.get("remote", "origin") # Get from config or default
        branch_name: Optional[str] = None

        try:
            repo = await self._get_repo(working_dir)
            try:
                 branch_name = await run_pygit2_async(lambda: repo.head.shorthand)
                 log.debug("Determined current branch for push", branch=branch_name)
            except pygit2.GitError:
                 log.warning("Could not determine current branch from HEAD, checking config.")
                 branch_name = repo_config.get("branch")
                 if not branch_name:
                      log.warning("Branch not specified in config, defaulting to 'main'.")
                      branch_name = "main"

            if not branch_name:
                 raise GitRemoteError("Could not determine branch to push.", repo_path=str(working_dir))

            # Pass the specific repo_config dict to the push function
            return await perform_git_push(repo, working_dir, remote_name, branch_name, repo_config)

        except GitEngineError as e:
            # Catch errors from _get_repo or perform_git_push
            return PushResult(success=False, message=str(e))
        except Exception as e:
            log.critical("Unexpected error in perform_push", error=str(e), exc_info=True)
            return PushResult(success=False, message=f"Unexpected error: {e}")

# 🔼⚙️
