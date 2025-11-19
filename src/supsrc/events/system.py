#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""System and rule events."""

from __future__ import annotations

import attrs

from supsrc.events.base import BaseEvent


@attrs.define(frozen=True)
class RuleTriggeredEvent(BaseEvent):
    """Event emitted when a rule triggers an action."""

    source: str = attrs.field(default="rules", init=False)
    rule_name: str = attrs.field(kw_only=True)
    repo_id: str = attrs.field(kw_only=True)
    action: str = attrs.field(kw_only=True)  # 'commit', 'push', etc.

    def format(self) -> str:
        """Format rule trigger event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] ⚡ [{self.repo_id}] Rule '{self.rule_name}' triggered {self.action}"  # LIGHTNING


@attrs.define(frozen=True)
class ConfigReloadEvent(BaseEvent):
    """Event emitted when configuration is reloaded."""

    source: str = attrs.field(default="system", init=False)
    config_path: str | None = attrs.field(default=None, kw_only=True)

    def format(self) -> str:
        """Format config reload event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        path_info = f" from {self.config_path}" if self.config_path else ""
        return f"[{time_str}] 🔄 Configuration reloaded{path_info}"  # COUNTERCLOCKWISE ARROWS


@attrs.define(frozen=True)
class UserActionEvent(BaseEvent):
    """Event emitted from user interaction in TUI."""

    source: str = attrs.field(default="tui", init=False)
    action: str = attrs.field(kw_only=True)  # 'pause', 'resume', 'refresh', etc.
    target: str | None = attrs.field(default=None, kw_only=True)  # repo_id or None for global

    def format(self) -> str:
        """Format user action event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        target_str = f" [{self.target}]" if self.target else ""
        return f"[{time_str}] 👤{target_str} User action: {self.action}"  # BUST IN SILHOUETTE


@attrs.define(frozen=True)
class ErrorEvent(BaseEvent):
    """Event emitted when an error occurs."""

    source: str = attrs.field(kw_only=True)  # Source component where error occurred
    error_type: str = attrs.field(kw_only=True)
    repo_id: str | None = attrs.field(default=None, kw_only=True)

    def format(self) -> str:
        """Format error event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        repo_str = f" [{self.repo_id}]" if self.repo_id else ""
        return f"[{time_str}] ❌ [{self.source}]{repo_str} {self.error_type}: {self.description}"  # CROSS MARK


@attrs.define(frozen=True)
class ExternalCommitEvent(BaseEvent):
    """Event emitted when changes were committed externally (outside supsrc)."""

    source: str = attrs.field(default="git", init=False)
    repo_id: str = attrs.field(kw_only=True)
    commit_hash: str | None = attrs.field(default=None, kw_only=True)

    def format(self) -> str:
        """Format external commit event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        hash_str = f" ({self.commit_hash[:7]})" if self.commit_hash else ""
        return f"[{time_str}] 🤔 [{self.repo_id}] Changes committed externally{hash_str}"


@attrs.define(frozen=True)
class ConflictDetectedEvent(BaseEvent):
    """Event emitted when merge conflicts are detected."""

    source: str = attrs.field(default="git", init=False)
    repo_id: str = attrs.field(kw_only=True)
    conflict_files: list[str] = attrs.field(factory=list, kw_only=True)

    def format(self) -> str:
        """Format conflict detected event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        file_count = len(self.conflict_files)
        files_str = f" in {file_count} file{'s' if file_count != 1 else ''}" if file_count > 0 else ""
        return f"[{time_str}] ⚠️ [{self.repo_id}] Merge conflicts detected{files_str}"


@attrs.define(frozen=True)
class RepositoryFrozenEvent(BaseEvent):
    """Event emitted when repository is frozen due to issues."""

    source: str = attrs.field(default="system", init=False)
    repo_id: str = attrs.field(kw_only=True)
    reason: str = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format repository frozen event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] 🧊 [{self.repo_id}] Repository frozen: {self.reason}"


@attrs.define(frozen=True)
class TestFailureEvent(BaseEvent):
    """Event emitted when tests fail during auto-commit."""

    source: str = attrs.field(default="testing", init=False)
    repo_id: str = attrs.field(kw_only=True)
    test_output: str | None = attrs.field(default=None, kw_only=True)

    def format(self) -> str:
        """Format test failure event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        output_suffix = f": {self.test_output}" if self.test_output else ""
        return f"[{time_str}] ❗ [{self.repo_id}] Tests failed{output_suffix}"


@attrs.define(frozen=True)
class LLMVetoEvent(BaseEvent):
    """Event emitted when LLM review blocks a commit."""

    source: str = attrs.field(default="llm", init=False)
    repo_id: str = attrs.field(kw_only=True)
    reason: str = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format LLM veto event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] 🧠 [{self.repo_id}] LLM review blocked: {self.reason}"


@attrs.define(frozen=True)
class GitSpecialStateDetectedEvent(BaseEvent):
    """Event emitted when a special Git state is detected (merge, rebase, cherry-pick, revert)."""

    source: str = attrs.field(default="git", init=False)
    repo_id: str = attrs.field(kw_only=True)
    state_type: str = attrs.field(kw_only=True)  # "merge", "rebase", "cherry-pick", "revert"

    def format(self) -> str:
        """Format special state detected event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        emoji_map = {
            "merge": "🔀",
            "rebase": "🔄",
            "cherry-pick": "🍒",
            "revert": "↩️",
        }
        emoji = emoji_map.get(self.state_type, "⚠️")
        return f"[{time_str}] {emoji} [{self.repo_id}] {self.state_type.capitalize()} in progress - auto-commit paused"


# 🔼⚙️🔚
