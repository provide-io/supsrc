# src/supsrc/events/system.py

"""
System and rule events.
"""

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
        return f"[{time_str}] \u26a1 [{self.repo_id}] Rule '{self.rule_name}' triggered {self.action}"  # LIGHTNING


@attrs.define(frozen=True)
class ConfigReloadEvent(BaseEvent):
    """Event emitted when configuration is reloaded."""

    source: str = attrs.field(default="system", init=False)
    config_path: str | None = attrs.field(default=None, kw_only=True)

    def format(self) -> str:
        """Format config reload event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        path_info = f" from {self.config_path}" if self.config_path else ""
        return (
            f"[{time_str}] \U0001f504 Configuration reloaded{path_info}"  # COUNTERCLOCKWISE ARROWS
        )


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
        return (
            f"[{time_str}] \U0001f464{target_str} User action: {self.action}"  # BUST IN SILHOUETTE
        )


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
        return f"[{time_str}] \u274c [{self.source}]{repo_str} {self.error_type}: {self.description}"  # CROSS MARK
