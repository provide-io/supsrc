#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for system events."""

from supsrc.events.system import ConfigReloadEvent, ErrorEvent, RuleTriggeredEvent, UserActionEvent


def test_rule_triggered_event_creation() -> None:
    """Test creating a RuleTriggeredEvent."""
    event = RuleTriggeredEvent(
        description="Rule fired",
        rule_name="inactivity-5min",
        repo_id="web-app",
        action="commit",
    )

    assert event.source == "rules"
    assert event.rule_name == "inactivity-5min"
    assert event.repo_id == "web-app"
    assert event.action == "commit"


def test_rule_triggered_event_format() -> None:
    """Test RuleTriggeredEvent formatting."""
    event = RuleTriggeredEvent(
        description="Auto-commit rule triggered",
        rule_name="save-count-10",
        repo_id="my-project",
        action="push",
    )

    formatted = event.format()
    assert "\u26a1" in formatted  # LIGHTNING
    assert "[my-project]" in formatted
    assert "save-count-10" in formatted
    assert "triggered push" in formatted


def test_config_reload_event_creation() -> None:
    """Test creating a ConfigReloadEvent."""
    event = ConfigReloadEvent(
        description="Configuration reloaded",
        config_path="/etc/supsrc.conf",
    )

    assert event.source == "system"
    assert event.config_path == "/etc/supsrc.conf"


def test_config_reload_event_format_with_path() -> None:
    """Test ConfigReloadEvent formatting with config path."""
    event = ConfigReloadEvent(
        description="Config updated",
        config_path="/home/user/.supsrc.toml",
    )

    formatted = event.format()
    assert "\U0001f504" in formatted  # COUNTERCLOCKWISE ARROWS
    assert "Configuration reloaded" in formatted
    assert "/home/user/.supsrc.toml" in formatted


def test_config_reload_event_format_no_path() -> None:
    """Test ConfigReloadEvent formatting without config path."""
    event = ConfigReloadEvent(description="Config reloaded")

    formatted = event.format()
    assert "\U0001f504" in formatted  # COUNTERCLOCKWISE ARROWS
    assert "Configuration reloaded" in formatted
    assert "from " not in formatted  # No path info


def test_user_action_event_creation() -> None:
    """Test creating a UserActionEvent."""
    event = UserActionEvent(
        description="User paused monitoring",
        action="pause",
        target="specific-repo",
    )

    assert event.source == "tui"
    assert event.action == "pause"
    assert event.target == "specific-repo"


def test_user_action_event_format_with_target() -> None:
    """Test UserActionEvent formatting with target repo."""
    event = UserActionEvent(
        description="User action",
        action="refresh",
        target="my-app",
    )

    formatted = event.format()
    assert "\U0001f464" in formatted  # BUST IN SILHOUETTE
    assert "[my-app]" in formatted
    assert "User action: refresh" in formatted


def test_user_action_event_format_no_target() -> None:
    """Test UserActionEvent formatting without target (global action)."""
    event = UserActionEvent(
        description="Global action",
        action="reload-config",
    )

    formatted = event.format()
    assert "\U0001f464" in formatted  # BUST IN SILHOUETTE
    assert "User action: reload-config" in formatted
    assert "] [" not in formatted  # No target repo


def test_error_event_creation() -> None:
    """Test creating an ErrorEvent."""
    event = ErrorEvent(
        description="Connection failed",
        source="git",
        error_type="NetworkError",
        repo_id="remote-repo",
    )

    assert event.source == "git"
    assert event.error_type == "NetworkError"
    assert event.repo_id == "remote-repo"
    assert event.description == "Connection failed"


def test_error_event_format_with_repo() -> None:
    """Test ErrorEvent formatting with repo ID."""
    event = ErrorEvent(
        description="Failed to commit",
        source="git",
        error_type="CommitError",
        repo_id="project-x",
    )

    formatted = event.format()
    assert "\u274c" in formatted  # CROSS MARK
    assert "[git]" in formatted
    assert "[project-x]" in formatted
    assert "CommitError: Failed to commit" in formatted


def test_error_event_format_no_repo() -> None:
    """Test ErrorEvent formatting without repo ID."""
    event = ErrorEvent(
        description="System error occurred",
        source="monitor",
        error_type="FileSystemError",
    )

    formatted = event.format()
    assert "\u274c" in formatted  # CROSS MARK
    assert "[monitor]" in formatted
    assert "FileSystemError: System error occurred" in formatted
    assert "] [" not in formatted  # No repo ID


def test_event_sources() -> None:
    """Test that events have correct sources."""
    rule_event = RuleTriggeredEvent(
        description="Test",
        rule_name="test",
        repo_id="test",
        action="test",
    )

    config_event = ConfigReloadEvent(description="Test")

    user_event = UserActionEvent(description="Test", action="test")

    error_event = ErrorEvent(
        description="Test",
        source="custom",
        error_type="TestError",
    )

    assert rule_event.source == "rules"
    assert config_event.source == "system"
    assert user_event.source == "tui"
    assert error_event.source == "custom"  # Source is customizable for errors


# 🔼⚙️🔚
