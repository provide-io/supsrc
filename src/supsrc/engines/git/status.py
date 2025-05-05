#
# engines/git/status.py
#
"""
Git status checking logic using pygit2.
"""

from pathlib import Path
import pygit2 # type: ignore[import-untyped]
import structlog

from supsrc.protocols import RepoStatusResult # Use the protocol definition
from .runner import run_pygit2_async
from .errors import GitStatusError

log = structlog.get_logger("engines.git.status")

# Mapping from pygit2 status flags to our understanding
# See: https://github.com/libgit2/libgit2/blob/main/include/git2/status.h
PYGIT2_STATUS_MAP = {
    pygit2.GIT_STATUS_INDEX_NEW: "staged",
    pygit2.GIT_STATUS_INDEX_MODIFIED: "staged",
    pygit2.GIT_STATUS_INDEX_DELETED: "staged",
    pygit2.GIT_STATUS_INDEX_RENAMED: "staged",
    pygit2.GIT_STATUS_INDEX_TYPECHANGE: "staged",
    pygit2.GIT_STATUS_WT_NEW: "unstaged",
    pygit2.GIT_STATUS_WT_MODIFIED: "unstaged",
    pygit2.GIT_STATUS_WT_DELETED: "unstaged",
    pygit2.GIT_STATUS_WT_TYPECHANGE: "unstaged",
    pygit2.GIT_STATUS_WT_RENAMED: "unstaged",
    pygit2.GIT_STATUS_IGNORED: "ignored",
    pygit2.GIT_STATUS_CONFLICTED: "conflicted",
}

async def get_git_status(repo: pygit2.Repository, working_dir: Path) -> RepoStatusResult:
    """
    Checks the Git status using pygit2 asynchronously.

    Args:
        repo: An initialized pygit2.Repository object.
        working_dir: The repository's working directory path (for context).

    Returns:
        RepoStatusResult indicating the repository status.
    """
    log.debug("Checking git status", repo_path=str(working_dir))
    try:
        # Run the blocking repo.status() call in a thread
        status_dict = await run_pygit2_async(repo.status)

        has_staged = False
        has_unstaged = False
        is_clean = True
        has_conflicts = False
        status_details: dict[str, list[str]] = {
             "staged": [], "unstaged": [], "conflicted": [], "ignored": []
        }

        if not status_dict:
            log.debug("Status dictionary is empty, repo is clean.")
            is_clean = True
        else:
            for filepath, flags in status_dict.items():
                # Check flags based on our map
                if flags & pygit2.GIT_STATUS_CONFLICTED:
                    has_conflicts = True
                    is_clean = False
                    status_details["conflicted"].append(filepath)
                    # Don't check other flags if conflicted
                    continue

                is_staged = flags & (
                    pygit2.GIT_STATUS_INDEX_NEW |
                    pygit2.GIT_STATUS_INDEX_MODIFIED |
                    pygit2.GIT_STATUS_INDEX_DELETED |
                    pygit2.GIT_STATUS_INDEX_RENAMED |
                    pygit2.GIT_STATUS_INDEX_TYPECHANGE
                )
                is_unstaged = flags & (
                    pygit2.GIT_STATUS_WT_NEW |
                    pygit2.GIT_STATUS_WT_MODIFIED |
                    pygit2.GIT_STATUS_WT_DELETED |
                    pygit2.GIT_STATUS_WT_TYPECHANGE |
                    pygit2.GIT_STATUS_WT_RENAMED
                )

                if is_staged:
                    has_staged = True
                    is_clean = False
                    status_details["staged"].append(filepath)

                if is_unstaged:
                    has_unstaged = True
                    is_clean = False
                    status_details["unstaged"].append(filepath)

                # Note: We generally don't care about ignored files for commit status
                # if flags & pygit2.GIT_STATUS_IGNORED:
                #     status_details["ignored"].append(filepath)

            # If we found conflicts, override clean status
            if has_conflicts:
                is_clean = False

        log.debug("Status check complete", is_clean=is_clean, has_staged=has_staged, has_unstaged=has_unstaged, has_conflicts=has_conflicts)
        return RepoStatusResult(
            success=True,
            is_clean=is_clean,
            has_staged_changes=has_staged,
            has_unstaged_changes=has_unstaged,
            details={"conflicts": status_details["conflicted"]} if has_conflicts else None,
            message="Status retrieved successfully."
        )

    except Exception as e:
        # Catch potential errors during status check and wrap them
        log.error("Failed to get git status", repo_path=str(working_dir), error=str(e), exc_info=True)
        # Raise specific error if needed, or use the wrapped error from run_pygit2_async
        if isinstance(e, GitStatusError): raise # Re-raise if already specific
        raise GitStatusError(f"Failed to get status: {e}", repo_path=str(working_dir), details=e) from e

# 🔼⚙️
