# file: src/supsrc/engines/git/info.py
"""
Provides functions to get status and summary information from a Git repository.
"""

from pathlib import Path
from typing import Optional, Any, Mapping
from datetime import datetime, timezone, timedelta # <<< Ensure timedelta is imported

import pygit2
import structlog
from attrs import define, field

# --- FIX: Ensure RepoStatusResult is imported directly ---
# from supsrc.protocols import RepoStatusResult
# Instead, let's define the protocol result structure here or import PluginResult base
from supsrc.protocols import PluginResult # Base protocol result
# ------------------------------------------------------

from supsrc.engines.git.runner import run_pygit2_func
from supsrc.engines.git.exceptions import GitCommandError

log = structlog.get_logger("engines.git.info")

@define(frozen=True, slots=True)
class GitRepoSummary:
    """Structured summary of a Git repository's HEAD state."""
    head_ref_name: Optional[str] = None
    head_commit_hash: Optional[str] = None
    head_commit_message_summary: Optional[str] = None
    head_commit_time: Optional[datetime] = None
    is_empty: bool = False

# --- FIX: Define GitRepoStatus directly, inheriting from PluginResult ---
@define(frozen=True, slots=True)
class GitRepoStatus(PluginResult): # Inherit from base result type
    """Git-specific implementation of RepoStatusResult."""
    # Inherits success, message, details from PluginResult
    is_clean: bool = False
    has_staged_changes: bool = False
    has_unstaged_changes: bool = False
    has_untracked_files: bool = False # Git specific
    is_conflicted: bool = False      # Git specific
    is_unborn: bool = False          # Git specific
    is_detached: bool = False        # Git specific
    current_branch: Optional[str] = None
# ---------------------------------------------------------------------

async def get_git_summary(repo_path: Path) -> GitRepoSummary:
    """Retrieves a summary of the Git repository's HEAD."""
    repo_info_log = log.bind(repo_path=str(repo_path))
    repo_info_log.debug("Getting repository summary")
    try:
        repo = await run_pygit2_func(pygit2.Repository, str(repo_path))

        is_empty = await run_pygit2_func(getattr, repo, 'is_empty') # Use getattr for properties
        if is_empty:
            repo_info_log.debug("Repository is empty.")
            return GitRepoSummary(is_empty=True)

        head_is_unborn = await run_pygit2_func(getattr, repo, 'head_is_unborn')
        if head_is_unborn:
            repo_info_log.debug("Repository has unborn HEAD.")
            # Return UNBORN here or let caller interpret None values
            return GitRepoSummary(head_ref_name="UNBORN")

        head_ref = await run_pygit2_func(getattr, repo, 'head')
        head_ref_name = getattr(head_ref, 'shorthand', None) or getattr(head_ref, 'name', None)
        head_commit = await run_pygit2_func(repo.revparse_single, 'HEAD')

        if not head_commit or not isinstance(head_commit, pygit2.Commit): # Check type
             repo_info_log.warning("Could not resolve HEAD commit.")
             return GitRepoSummary(head_ref_name=head_ref_name) # Return what we have

        head_commit_hash = str(head_commit.id)
        head_commit_msg_summary = (head_commit.message or "").split('\n', 1)[0]
        # pygit2 commit time is Unix timestamp, offset is minutes offset from UTC
        commit_time_utc = datetime.fromtimestamp(head_commit.commit_time, timezone.utc)
        # Adjust for timezone offset stored in commit
        tz_offset = timedelta(minutes=head_commit.commit_time_offset)
        commit_time_local = commit_time_utc + tz_offset


        repo_info_log.debug("Found HEAD reference", ref=head_ref_name)
        repo_info_log.debug("Found HEAD commit", hash=head_commit_hash, summary=head_commit_msg_summary)

        return GitRepoSummary(
            head_ref_name=head_ref_name,
            head_commit_hash=head_commit_hash,
            head_commit_message_summary=head_commit_msg_summary,
            head_commit_time=commit_time_local, # Store local time? or UTC? Decide convention
            is_empty=False,
        )

    except (GitCommandError, pygit2.GitError, ValueError, TypeError) as e:
        repo_info_log.error("Failed to get repository summary", error=str(e), exc_info=False)
        # Return a minimal summary indicating failure state if needed, or re-raise
        raise # Let the orchestrator handle this failure during init

async def get_git_status(repo: pygit2.Repository, repo_path: Path) -> GitRepoStatus:
    """Checks the status of the Git working directory and index."""
    status_log = log.bind(repo_path=str(repo_path))
    status_log.debug("Checking Git status")
    try:
        # Check special states first
        is_unborn = await run_pygit2_func(getattr, repo, 'head_is_unborn')
        is_detached = await run_pygit2_func(getattr, repo, 'head_is_detached')
        current_branch = None
        if not is_detached and not is_unborn:
             head_ref = await run_pygit2_func(getattr, repo, 'head')
             current_branch = getattr(head_ref, 'shorthand', None)

        # Get detailed status flags
        # Note: pygit2 status might show conflicts, untracked, etc.
        status_dict: Mapping[str, int] = await run_pygit2_func(repo.status)

        if not status_dict:
            status_log.debug("Repository is clean.")
            return GitRepoStatus(success=True, is_clean=True, current_branch=current_branch, is_unborn=is_unborn, is_detached=is_detached)

        # Analyze flags
        has_staged = False
        has_unstaged = False
        has_untracked = False
        is_conflicted = False

        for file_path, flags in status_dict.items():
            # Staged changes (Index vs HEAD)
            if flags & (pygit2.GIT_STATUS_INDEX_NEW |
                        pygit2.GIT_STATUS_INDEX_MODIFIED |
                        pygit2.GIT_STATUS_INDEX_DELETED |
                        pygit2.GIT_STATUS_INDEX_RENAMED |
                        pygit2.GIT_STATUS_INDEX_TYPECHANGE):
                has_staged = True

            # Unstaged changes (Workdir vs Index)
            if flags & (pygit2.GIT_STATUS_WT_MODIFIED |
                        pygit2.GIT_STATUS_WT_DELETED |
                        pygit2.GIT_STATUS_WT_TYPECHANGE |
                        pygit2.GIT_STATUS_WT_RENAMED):
                has_unstaged = True

            # Untracked files (Workdir only)
            if flags & pygit2.GIT_STATUS_WT_NEW:
                has_untracked = True
                # Consider if untracked should always imply unstaged changes
                # has_unstaged = True

            # Conflicts (Workdir)
            if flags & pygit2.GIT_STATUS_CONFLICTED:
                is_conflicted = True

        status_log.debug(
            "Git status determined",
            staged=has_staged, unstaged=has_unstaged, untracked=has_untracked,
            conflicted=is_conflicted, unborn=is_unborn, detached=is_detached
        )

        return GitRepoStatus(
            success=True,
            is_clean=False, # Since status_dict was not empty
            has_staged_changes=has_staged,
            has_unstaged_changes=has_unstaged,
            has_untracked_files=has_untracked,
            is_conflicted=is_conflicted,
            is_unborn=is_unborn,
            is_detached=is_detached,
            current_branch=current_branch,
        )

    except (GitCommandError, pygit2.GitError) as e:
        status_log.error("Failed to get repository status", error=str(e))
        return GitRepoStatus(success=False, message=f"Failed to get status: {e}", is_clean=False) # <<< Ensure success=False is passed
    except Exception as e: # Catch broader exceptions
        status_log.exception("Unexpected error getting status")
        return GitRepoStatus(success=False, message=f"Unexpected status error: {e}", is_clean=False) # <<< Ensure success=False is passed

# 🔼⚙️
