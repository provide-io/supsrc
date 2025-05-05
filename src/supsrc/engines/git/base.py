#
# filename: src/supsrc/engines/git/base.py
#
"""
Base implementation for the Git RepositoryEngine using pygit2.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import attrs
import pygit2  # type: ignore
import structlog

from ...config.models import GlobalConfig  # Use for type hint
from ...protocols import (
    CommitResult,
    PushResult,
    RepositoryEngine,
    RepoStatusResult,  # Keep protocol for type hints
    StageResult,
)
from ...state import RepositoryState


# Import specific exceptions if defined, otherwise use base
# from .exceptions import GitEngineError, GitCommandError
class GitEngineError(Exception): # Basic definition if not in exceptions.py
    def __init__(self, message: str, path: str | None = None):
        self.path = path; super().__init__(message)

from .info import (  # Import concrete status class and getter
    GitRepoStatus,
    get_git_status,
)
from .runner import run_pygit2_async

# Import utils if they exist, define basics otherwise
try: from .utils import get_default_commit_message, get_default_signature, get_commit_message
except ImportError:
    def get_default_commit_message(config, global_config): return "supsrc auto-commit"
    def get_default_signature(repo): return pygit2.Signature("supsrc", "supsrc@example.com")
    def get_commit_message(config, global_config): return config.get("commit_message_template", get_default_commit_message(config, global_config))


@attrs.define(slots=True, auto_attribs=True)
class SimpleResult:
    """Generic success/failure result object for Stage/Push."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None

@attrs.define(frozen=True, slots=True)
class GitCommitResult:
    """Concrete result for commit operations."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None
    commit_hash: str | None = None

class GitEngine(RepositoryEngine):
    """
    RepositoryEngine implementation for Git using pygit2.
    """
    def __init__(self) -> None:
        self._log = structlog.get_logger("engines.git.base").bind(engine_id=id(self))
        self._log.debug("GitEngine initialized")

    async def _get_repo(self, working_dir: Path) -> pygit2.Repository:
        """Helper to asynchronously get a pygit2 Repository object."""
        self._log.debug("Getting repository object", path=str(working_dir))
        try:
            # Discover upwards from working_dir if needed, or use direct path
            # pygit2.Repository(str(working_dir)) expects working_dir to be repo root or .git dir
            # CORRECTED WRAPPER CALL:
            repo: pygit2.Repository = await run_pygit2_async(pygit2.Repository)(str(working_dir)) # type: ignore
            # Verify it's not bare
            # CORRECTED WRAPPER CALL:
            is_bare = await run_pygit2_async(getattr)(repo, "is_bare")
            if is_bare:
                raise GitEngineError("Repository is bare, cannot perform working directory operations.", path=str(working_dir))
            return repo
        except pygit2.GitError as e:
            self._log.error("Failed to open repository", path=str(working_dir), error=str(e))
            raise GitEngineError(f"Not a valid Git repository or unable to access: {e}", path=str(working_dir)) from e
        except Exception as e:
            self._log.exception("Unexpected error getting repository object", path=str(working_dir))
            raise GitEngineError(f"Unexpected error opening repository: {e}", path=str(working_dir)) from e

    async def get_status(
        self, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> RepoStatusResult: # Return type hint remains the protocol
        """Check the current status of the Git repository."""
        status_log = self._log.bind(repo_id=state.repo_id)
        try:
            repo = await self._get_repo(working_dir)
            # Call the corrected info function which returns a GitRepoStatus object
            git_status: GitRepoStatus = await get_git_status(repo, working_dir)
            # Optionally enhance the message based on combined status
            if git_status.is_conflicted:
                 git_status = attrs.evolve(git_status, message="Repository has conflicts!")

            return git_status # Return the concrete object which conforms to the protocol
        except GitEngineError as e:
            status_log.error("Engine error getting status", error=str(e))
            # CORRECTED: Return concrete GitRepoStatus on error
            return GitRepoStatus(success=False, message=str(e))
        except Exception as e:
            status_log.exception("Unexpected error in get_status")
            # CORRECTED: Return concrete GitRepoStatus on error
            return GitRepoStatus(success=False, message=f"Unexpected error: {e}", is_clean=None)


    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        stage_log = self._log.bind(repo_id=state.repo_id)
        stage_log.info("Staging changes", files=files or "ALL")
        try:
            repo = await self._get_repo(working_dir)
            index: pygit2.Index = await run_pygit2_async(getattr)(repo, "index") # type: ignore

            if files:
                rel_files = [str(f.relative_to(working_dir)) for f in files]
                stage_log.debug("Staging specific files", rel_files=rel_files)
                for f_rel in rel_files:
                    await run_pygit2_async(index.add)(f_rel)
            else:
                stage_log.debug("Staging all tracked changes (add/update/remove)")
                await run_pygit2_async(index.add_all)()

            await run_pygit2_async(index.write)()
            stage_log.info("Staging successful")
            # SimpleResult conforms to StageResult protocol
            return SimpleResult(success=True, message="Changes staged successfully.")

        except GitEngineError as e:
             stage_log.error("Engine error staging changes", error=str(e))
             return SimpleResult(success=False, message=str(e))
        except pygit2.GitError as e:
            stage_log.error("Git error staging changes", error=str(e))
            return SimpleResult(success=False, message=f"Git staging failed: {e}")
        except Exception as e:
            stage_log.exception("Unexpected error staging changes")
            return SimpleResult(success=False, message=f"Unexpected staging error: {e}")

    async def perform_commit(
        self, message_template: str, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with the given message template."""
        commit_log = self._log.bind(repo_id=state.repo_id)
        try:
            repo = await self._get_repo(working_dir)

            status_result = await self.get_status(state, config, global_config, working_dir)
            if not status_result.success or status_result.has_staged_changes is False:
                 commit_log.info("No staged changes found, skipping commit.", status_checked=status_result.success)
                 return GitCommitResult(success=True, message="Commit skipped: No staged changes.", commit_hash=None)

            signature = await run_pygit2_async(get_default_signature)(repo)
            if not signature:
                 raise GitEngineError("Could not determine Git user signature (check config).")

            commit_message = get_commit_message(config, global_config)

            index: pygit2.Index = await run_pygit2_async(getattr)(repo, "index") # type: ignore
            tree_oid = await run_pygit2_async(index.write_tree)()
            parents = []
            try:
                # Use head.target directly as it's the OID
                head_target = await run_pygit2_async(getattr)(repo.head, "target")
                parents.append(head_target)
            except (pygit2.GitError, AttributeError): # Handles unborn HEAD or detached HEAD errors
                commit_log.info("No parent commit found (likely first commit or detached HEAD).")

            commit_oid = await run_pygit2_async(repo.create_commit)(
                "HEAD", signature, signature, commit_message, tree_oid, parents
            )
            commit_hash = str(commit_oid)
            commit_log.info("Commit successful", commit_hash=commit_hash)
            # GitCommitResult conforms to CommitResult protocol
            return GitCommitResult(success=True, message="Commit successful.", commit_hash=commit_hash)

        except GitEngineError as e:
             commit_log.error("Engine error performing commit", error=str(e))
             return GitCommitResult(success=False, message=str(e), commit_hash=None)
        except pygit2.GitError as e:
            commit_log.error("Git error performing commit", error=str(e))
            return GitCommitResult(success=False, message=f"Git commit failed: {e}", commit_hash=None)
        except Exception as e:
            commit_log.exception("Unexpected error performing commit")
            return GitCommitResult(success=False, message=f"Unexpected commit error: {e}", commit_hash=None)

    async def perform_push(
        self, state: RepositoryState, config: Mapping[str, Any], global_config: GlobalConfig, working_dir: Path
    ) -> PushResult:
        """Perform the push action."""
        push_log = self._log.bind(repo_id=state.repo_id)

        auto_push = config.get("auto_push", False)
        if not auto_push:
             push_log.info("Push skipped: 'auto_push' is false in configuration.")
             return SimpleResult(success=True, message="Push skipped: Disabled by configuration.")

        remote_name = config.get("remote", "origin")
        try:
            repo = await self._get_repo(working_dir)
            remote: pygit2.Remote = await run_pygit2_async(repo.remotes.__getitem__)(remote_name) # type: ignore
            push_log.info("Attempting push", remote=remote_name, url=remote.url)

            current_ref_name = await run_pygit2_async(repo.head.name)
            if not current_ref_name:
                 raise GitEngineError("Cannot determine current branch reference for push.")

            # Note: Push callbacks for credentials are not implemented here
            push_result = await run_pygit2_async(remote.push)([current_ref_name])

            push_log.info("Push successful", remote=remote_name)
            # SimpleResult conforms to PushResult protocol
            return SimpleResult(success=True, message="Push successful.")

        except GitEngineError as e:
             push_log.error("Engine error performing push", error=str(e))
             return SimpleResult(success=False, message=str(e))
        except pygit2.GitError as e:
             push_log.error("Git error performing push", remote=remote_name, error=str(e))
             return SimpleResult(success=False, message=f"Git push to '{remote_name}' failed: {e}")
        except KeyError:
             push_log.error("Git remote not found", remote=remote_name)
             return SimpleResult(success=False, message=f"Remote '{remote_name}' not found.")
        except Exception as e:
            push_log.exception("Unexpected error performing push")
            return SimpleResult(success=False, message=f"Unexpected push error: {e}")

# 🔼⚙️
