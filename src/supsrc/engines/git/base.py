#
# engines/git/base.py
#
"""
Main GitEngine class implementing the RepositoryEngine protocol using pygit2.
"""

from pathlib import Path
from typing import Any, Optional
import pygit2 # type: ignore[import-untyped]
import attrs # For potential future engine state if needed
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

# Consider adding @attrs.define if the engine needs its own state later
class GitEngine(RepositoryEngine):
    """
    RepositoryEngine implementation using pygit2 for Git operations.
    """

    def __init__(self):
        # Engines are typically stateless, configuration is passed per call.
        # Initialization could validate pygit2 availability if desired.
        log.debug("GitEngine initialized")
        pass

    async def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to safely open the pygit2 repository object."""
        try:
            # Use discover_repository to find .git dir upwards if needed,
            # or assume working_dir is the root.
            # repo_path = await run_pygit2_async(pygit2.discover_repository, str(working_dir))
            # if repo_path is None:
            #     raise GitEngineError(f"Not a git repository (or any of the parent directories)", repo_path=str(working_dir))
            # For now, assume working_dir IS the repo root containing .git
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
        repo_config = config # Specific config for this engine instance
        try:
            repo = await self._get_repo(working_dir)
            return await get_git_status(repo, working_dir)
        except GitEngineError as e:
            # Catch errors from _get_repo or get_git_status
            return RepoStatusResult(success=False, message=str(e), is_clean=None, has_staged_changes=None, has_unstaged_changes=None)
        except Exception as e:
            log.critical("Unexpected error in get_status", error=str(e), exc_info=True)
            return RepoStatusResult(success=False, message=f"Unexpected error: {e}", is_clean=None, has_staged_changes=None, has_unstaged_changes=None)


    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        repo_config = config
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
        repo_config = config
        # Get template from config, provide default if missing
        template = repo_config.get("commit_message_template", "supsrc auto-commit: {{timestamp}}")
        try:
            repo = await self._get_repo(working_dir)
            return await perform_git_commit(repo, working_dir, template, state, repo_config)
        except GitEngineError as e:
            return CommitResult(success=False, message=str(e), commit_hash=None)
        except Exception as e:
            log.critical("Unexpected error in perform_commit", error=str(e), exc_info=True)
            return CommitResult(success=False, message=f"Unexpected error: {e}", commit_hash=None)


    async def perform_push(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> PushResult:
        """Perform the push action."""
        repo_config = config
        remote_name = repo_config.get("remote", "origin") # Get from config or default
        # Determine branch - try current branch, then config, then default
        branch_name: Optional[str] = None
        try:
            repo = await self._get_repo(working_dir)
            try:
                 branch_name = await run_pygit2_async(lambda: repo.head.shorthand) # Get current branch name
                 log.debug("Determined current branch for push", branch=branch_name)
            except pygit2.GitError:
                 log.warning("Could not determine current branch from HEAD, checking config.")
                 branch_name = repo_config.get("branch") # Check config
                 if not branch_name:
                      log.warning("Branch not specified in config, defaulting to 'main'.")
                      branch_name = "main" # Fallback default

            if not branch_name: # Should not happen with default, but check
                 raise GitRemoteError("Could not determine branch to push.", repo_path=str(working_dir))

            return await perform_git_push(repo, working_dir, remote_name, branch_name, repo_config)

        except GitEngineError as e:
            return PushResult(success=False, message=str(e))
        except Exception as e:
            log.critical("Unexpected error in perform_push", error=str(e), exc_info=True)
            return PushResult(success=False, message=f"Unexpected error: {e}")

# 🔼⚙️
