# src/supsrc/engines/git/events.py

"""
Git-specific events for repository operations.
"""

from __future__ import annotations

import attrs

from supsrc.events.base import BaseEvent


@attrs.define
class GitCommitEvent(BaseEvent):
    """Event emitted when a git commit is performed."""

    source: str = attrs.field(default="git", init=False)
    commit_hash: str = attrs.field(kw_only=True)
    branch: str = attrs.field(kw_only=True)
    files_changed: int = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format commit event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] 📝 Committed {self.files_changed} files [{self.commit_hash[:7]}] on {self.branch}"


@attrs.define
class GitPushEvent(BaseEvent):
    """Event emitted when a git push is performed."""

    source: str = attrs.field(default="git", init=False)
    remote: str = attrs.field(kw_only=True)
    branch: str = attrs.field(kw_only=True)
    commits_pushed: int = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format push event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return (
            f"[{time_str}] 🚀 Pushed {self.commits_pushed} commits to {self.remote}/{self.branch}"
        )


@attrs.define
class GitStageEvent(BaseEvent):
    """Event emitted when files are staged."""

    source: str = attrs.field(default="git", init=False)
    files_staged: list[str] = attrs.field(factory=list, kw_only=True)

    def format(self) -> str:
        """Format stage event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        file_count = len(self.files_staged)
        return f"[{time_str}] 📋 Staged {file_count} files"


@attrs.define
class GitBranchEvent(BaseEvent):
    """Event emitted when branch changes."""

    source: str = attrs.field(default="git", init=False)
    old_branch: str | None = attrs.field(kw_only=True)
    new_branch: str = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format branch change event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        if self.old_branch:
            return f"[{time_str}] 🌿 Switched from {self.old_branch} to {self.new_branch}"
        else:
            return f"[{time_str}] 🌿 On branch {self.new_branch}"
