#
# engines/git/info.py
#
"""
Logic for retrieving informational details about a Git repository using pygit2.
"""

from pathlib import Path
from typing import NamedTuple, Optional
import pygit2 # type: ignore[import-untyped]
import structlog

from .runner import run_pygit2_async
from .errors import GitEngineError

log = structlog.get_logger("engines.git.info")

class GitRepoSummary(NamedTuple):
    """Holds summary information about the repository's HEAD state."""
    is_empty: bool
    head_commit_hash: Optional[str] = None
    head_commit_message_summary: Optional[str] = None
    head_ref_name: Optional[str] = None # e.g., 'refs/heads/main' or None if detached/unborn

async def get_git_summary(repo: pygit2.Repository, working_dir: Path) -> GitRepoSummary:
    """
    Retrieves summary information about the repository's current HEAD state.

    Args:
        repo: An initialized pygit2.Repository object.
        working_dir: The repository's working directory path (for context).

    Returns:
        A GitRepoSummary object.
    """
    log.debug("Getting repository summary", repo_path=str(working_dir))
    try:
        is_empty = await run_pygit2_async(lambda: repo.is_empty)
        if is_empty:
            log.debug("Repository is empty (no commits yet).", repo_path=str(working_dir))
            return GitRepoSummary(is_empty=True)

        head_ref: Optional[pygit2.Reference] = None
        head_commit: Optional[pygit2.Commit] = None
        head_ref_name: Optional[str] = None
        head_commit_hash: Optional[str] = None
        message_summary: Optional[str] = None

        try:
            # Check if HEAD is detached or unborn first
            if await run_pygit2_async(lambda: repo.head_is_unborn):
                 log.debug("HEAD is unborn.", repo_path=str(working_dir))
                 # Still technically not empty if index has content, but no *commit* info
                 return GitRepoSummary(is_empty=False, head_ref_name="UNBORN") # Indicate unborn state

            elif await run_pygit2_async(lambda: repo.head_is_detached):
                 log.debug("HEAD is detached.", repo_path=str(working_dir))
                 head_commit_oid = await run_pygit2_async(lambda: repo.head.target)
                 head_commit = await run_pygit2_async(repo.get, head_commit_oid)
                 head_ref_name = "DETACHED"
            else:
                 # HEAD is a symbolic ref (points to a branch)
                 head_ref = await run_pygit2_async(lambda: repo.head)
                 head_ref_name = head_ref.name
                 head_commit = await run_pygit2_async(lambda: head_ref.peel(pygit2.Commit)) # Peel to the commit object
                 log.debug("Found HEAD reference", ref=head_ref_name)

            if head_commit:
                head_commit_hash = str(head_commit.id)
                # Get the first line of the commit message
                full_message = head_commit.message or ""
                message_summary = full_message.split('\n', 1)[0].strip()
                log.debug("Found HEAD commit", hash=head_commit_hash, summary=message_summary)

            return GitRepoSummary(
                is_empty=False,
                head_commit_hash=head_commit_hash,
                head_commit_message_summary=message_summary,
                head_ref_name=head_ref_name,
            )

        except pygit2.GitError as e:
             # Catch errors during HEAD resolution or commit lookup
             log.warning("Could not get full HEAD details", error=str(e), repo_path=str(working_dir))
             # Return potentially partial info
             return GitRepoSummary(
                 is_empty=False, # Assume not empty if we got here
                 head_commit_hash=head_commit_hash, # Might be None
                 head_commit_message_summary=message_summary, # Might be None
                 head_ref_name=head_ref_name or "ERROR", # Indicate error if ref wasn't resolved
             )

    except Exception as e:
        log.error("Failed to get repository summary", repo_path=str(working_dir), error=str(e), exc_info=True)
        raise GitEngineError(f"Failed to get repository summary: {e}", repo_path=str(working_dir), details=e) from e

# 🔼⚙️
