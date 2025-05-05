#
# supsrc/engines/git/info.py
#
"""
Provides functions to query information from a Git repository using pygit2,
returning structured data using attrs classes.
Handles running blocking pygit2 calls asynchronously.
"""

from pathlib import Path
from typing import Any

import attrs
import pygit2  # type: ignore
import structlog

# Use relative imports within the git engine package
from .runner import run_pygit2_async

log = structlog.get_logger("engines.git.info")

# --- Data Classes for Results ---

@attrs.define(frozen=True, slots=True)
class GitRepoSummary:
    """Structured summary of a Git repository's HEAD state."""
    is_empty: bool = False
    is_unborn: bool = False
    head_ref_name: str | None = None
    head_commit_hash: str | None = None
    head_commit_message_summary: str | None = None


@attrs.define(frozen=True, slots=True)
class GitRepoStatus:
    """
    Concrete implementation holding Git status details.
    This class structurally conforms to the RepoStatusResult protocol.
    """
    # Fields from PluginResult protocol
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None

    # Fields specific to RepoStatusResult protocol
    is_clean: bool | None = None
    has_staged_changes: bool | None = None
    has_unstaged_changes: bool | None = None
    has_untracked_changes: bool | None = None
    is_conflicted: bool | None = None
    is_unborn: bool | None = None # Keep the field, but calculate it correctly


# --- Helper to Check Unborn Status ---

async def _check_is_unborn(repo: pygit2.Repository) -> bool:
    """Helper function to check if the repository head is unborn."""
    try:
        # Attempt to resolve the reference pointed to by HEAD.
        # If it fails with specific errors, it's likely unborn.
        _ = await run_pygit2_async(repo.head.resolve)() # type: ignore
        # If the above succeeds, HEAD points to a valid commit, so not unborn.
        return False
    except pygit2.GitError as e:
        # Check common error codes indicating unborn HEAD or missing reference
        # pygit2.ErrorCode.UNBORNBRANCH or pygit2.ErrorCode.NOTFOUND are typical
        if e.errno in (pygit2.ErrorCode.UNBORNBRANCH, pygit2.ErrorCode.NOTFOUND): # type: ignore
            return True
        # Re-raise other GitErrors
        raise
    except AttributeError:
         # If repo.head itself doesn't exist (shouldn't happen in valid repo)
         # Treat as unborn or an error state depending on desired strictness.
         # Let's consider it unborn for this check.
         return True


# --- Async Information Functions ---

async def get_git_summary(repo_path: Path) -> GitRepoSummary:
    """
    Asynchronously retrieves a summary of the repository's HEAD state.
    """
    summary_log = log.bind(repo_path=str(repo_path))
    summary_log.debug("Getting repository summary")
    try:
        # Run pygit2 calls in thread pool
        repo: pygit2.Repository = await run_pygit2_async(pygit2.Repository)(str(repo_path)) # type: ignore

        is_empty = await run_pygit2_async(getattr)(repo, "is_empty")
        if is_empty:
            summary_log.debug("Repository is empty")
            # If empty, it's effectively unborn as well
            return GitRepoSummary(is_empty=True, is_unborn=True)

        # Use the corrected check for unborn HEAD
        is_unborn = await _check_is_unborn(repo)
        if is_unborn:
            summary_log.debug("Repository HEAD is unborn")
            # is_empty might be False if .git dir exists but no commits
            return GitRepoSummary(is_empty=is_empty, is_unborn=True)

        # If not empty and not unborn, proceed to get HEAD details
        head_ref_name: str | None = None
        head_commit_hash: str | None = None
        head_commit_message_summary: str | None = None

        # We know repo.head exists and resolves if we reach here
        head_ref: pygit2.Reference = await run_pygit2_async(getattr)(repo, "head") # type: ignore
        if isinstance(head_ref, pygit2.Reference):
            head_ref_name = head_ref.shorthand
            summary_log.debug("Found HEAD reference", ref=head_ref_name)
            # Use the resolved reference's target OID directly
            head_commit: pygit2.Commit = await run_pygit2_async(repo.get)(head_ref.target) # type: ignore
            if isinstance(head_commit, pygit2.Commit):
                 head_commit_hash = head_commit.hex
                 head_commit_message_summary = (head_commit.message or "").split("\n", 1)[0]
                 summary_log.debug("Found HEAD commit", hash=head_commit_hash, summary=head_commit_message_summary)

        return GitRepoSummary(
            is_empty=is_empty,
            is_unborn=is_unborn, # Should be False here
            head_ref_name=head_ref_name,
            head_commit_hash=head_commit_hash,
            head_commit_message_summary=head_commit_message_summary,
        )

    except pygit2.GitError as e:
        summary_log.error("GitError getting repository summary", error=str(e))
        # Return a summary indicating an error state
        return GitRepoSummary() # Default flags (False) might be misleading, consider adding error field
    except Exception:
        summary_log.exception("Unexpected error getting repository summary")
        return GitRepoSummary()


async def get_git_status(repo: pygit2.Repository, repo_path: Path) -> GitRepoStatus:
    """
    Asynchronously retrieves the status of the Git working directory.

    Args:
        repo: The pygit2 Repository object.
        repo_path: The path to the repository (for logging).

    Returns:
        A GitRepoStatus object detailing the repository status.
    """
    status_log = log.bind(repo_path=str(repo_path))
    status_log.debug("Checking Git status")

    try:
        # Check basic repository states first using corrected logic
        is_empty = await run_pygit2_async(getattr)(repo, "is_empty")
        is_unborn = await _check_is_unborn(repo) if not is_empty else True
        # is_detached check might still be useful for context, but uses head
        is_detached = False
        if not is_unborn: # Can only check detached if head exists
             is_detached = await run_pygit2_async(getattr)(repo, "is_head_detached")

        # Get the detailed status dictionary
        status_dict: dict[str, pygit2.FileStatus] = await run_pygit2_async(repo.status)() # type: ignore

        if not status_dict and not is_unborn:
             status_log.debug("Git status determined: Clean")
             return GitRepoStatus(
                 success=True,
                 message="Repository clean",
                 is_clean=True,
                 has_staged_changes=False,
                 has_unstaged_changes=False,
                 has_untracked_changes=False,
                 is_conflicted=False,
                 is_unborn=False, # Known not unborn if clean
             )

        # Analyze the status flags
        has_staged = False
        has_unstaged = False
        has_untracked = False
        is_conflicted = False

        for file_path, flags in status_dict.items():
            # Staging checks
            if flags & (pygit2.GIT_STATUS_INDEX_NEW |
                        pygit2.GIT_STATUS_INDEX_MODIFIED |
                        pygit2.GIT_STATUS_INDEX_DELETED |
                        pygit2.GIT_STATUS_INDEX_RENAMED |
                        pygit2.GIT_STATUS_INDEX_TYPECHANGE):
                has_staged = True

            # Working directory checks (unstaged changes)
            if flags & (pygit2.GIT_STATUS_WT_MODIFIED |
                        pygit2.GIT_STATUS_WT_DELETED |
                        pygit2.GIT_STATUS_WT_TYPECHANGE |
                        pygit2.GIT_STATUS_WT_RENAMED): # Renamed in WT usually implies unstaged
                has_unstaged = True

            # Untracked check
            if flags & pygit2.GIT_STATUS_WT_NEW:
                has_untracked = True

            # Conflict check
            if flags & pygit2.GIT_STATUS_CONFLICTED:
                is_conflicted = True

            # Optimization: break early if all relevant flags are True
            if has_staged and has_unstaged and has_untracked and is_conflicted:
                break

        status_log.debug(
            "Git status determined",
            staged=has_staged, unstaged=has_unstaged, untracked=has_untracked,
            conflicted=is_conflicted, unborn=is_unborn, detached=is_detached
        )

        # Determine overall message and clean status
        if is_unborn and not status_dict:
             message = "Repository is unborn (no commits yet)"
             is_clean_flag = True # Unborn with no files is considered clean for commit purposes
        elif not status_dict and not is_unborn: # Should have been caught above, but double check
             message = "Repository clean"
             is_clean_flag = True
        else:
             message = "Repository has changes"
             is_clean_flag = False


        return GitRepoStatus(
            success=True,
            message=message,
            is_clean=is_clean_flag,
            has_staged_changes=has_staged,
            has_unstaged_changes=has_unstaged,
            has_untracked_changes=has_untracked,
            is_conflicted=is_conflicted,
            is_unborn=is_unborn,
            details={"raw_status": {k: v.name for k, v in status_dict.items()}},
        )

    except pygit2.GitError as e:
        status_log.error("GitError getting status", error=str(e))
        return GitRepoStatus(success=False, message=f"Failed to get status: {e}", is_clean=None)
    except Exception as e:
        # Catch broader exceptions during status check
        status_log.exception("Unexpected error getting status")
        return GitRepoStatus(success=False, message=f"Unexpected status error: {e}", is_clean=None)

# 🔼⚙️
