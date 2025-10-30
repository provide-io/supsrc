#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for monitor events."""

from pathlib import Path

from supsrc.events.monitor import FileChangeEvent, MonitoringStartEvent, MonitoringStopEvent


def test_file_change_event_creation() -> None:
    """Test creating a FileChangeEvent."""
    path = Path("/test/file.py")
    event = FileChangeEvent(
        description="File modified",
        repo_id="test-repo",
        file_path=path,
        change_type="modified",
    )

    assert event.source == "monitor"
    assert event.repo_id == "test-repo"
    assert event.file_path == path
    assert event.change_type == "modified"


def test_file_change_event_format_created() -> None:
    """Test FileChangeEvent formatting for created files."""
    event = FileChangeEvent(
        description="New file",
        repo_id="my-project",
        file_path=Path("/src/new_module.py"),
        change_type="created",
    )

    formatted = event.format()
    assert "\u2795" in formatted  # HEAVY PLUS SIGN
    assert "[my-project]" in formatted
    assert "new_module.py" in formatted
    assert "created" in formatted


def test_file_change_event_format_modified() -> None:
    """Test FileChangeEvent formatting for modified files."""
    event = FileChangeEvent(
        description="File updated",
        repo_id="webapp",
        file_path=Path("/src/main.py"),
        change_type="modified",
    )

    formatted = event.format()
    assert "\u270f\ufe0f" in formatted  # PENCIL
    assert "[webapp]" in formatted
    assert "main.py" in formatted
    assert "modified" in formatted


def test_file_change_event_format_deleted() -> None:
    """Test FileChangeEvent formatting for deleted files."""
    event = FileChangeEvent(
        description="File removed",
        repo_id="cleanup",
        file_path=Path("/old/legacy.py"),
        change_type="deleted",
    )

    formatted = event.format()
    assert "\u2796" in formatted  # HEAVY MINUS SIGN
    assert "[cleanup]" in formatted
    assert "legacy.py" in formatted
    assert "deleted" in formatted


def test_file_change_event_format_moved() -> None:
    """Test FileChangeEvent formatting for moved files."""
    event = FileChangeEvent(
        description="File moved",
        repo_id="refactor",
        file_path=Path("/new/location.py"),
        change_type="moved",
    )

    formatted = event.format()
    assert "\U0001f504" in formatted  # COUNTERCLOCKWISE ARROWS BUTTON
    assert "[refactor]" in formatted
    assert "location.py" in formatted
    assert "moved" in formatted


def test_file_change_event_format_unknown() -> None:
    """Test FileChangeEvent formatting for unknown change type."""
    event = FileChangeEvent(
        description="Unknown change",
        repo_id="test",
        file_path=Path("/test.py"),
        change_type="unknown",
    )

    formatted = event.format()
    assert "\U0001f4c4" in formatted  # PAGE FACING UP (default)
    assert "[test]" in formatted
    assert "test.py" in formatted
    assert "unknown" in formatted


def test_monitoring_start_event_creation() -> None:
    """Test creating a MonitoringStartEvent."""
    path = Path("/projects/my-app")
    event = MonitoringStartEvent(
        description="Monitoring started",
        repo_id="my-app",
        path=path,
    )

    assert event.source == "monitor"
    assert event.repo_id == "my-app"
    assert event.path == path


def test_monitoring_start_event_format() -> None:
    """Test MonitoringStartEvent formatting."""
    event = MonitoringStartEvent(
        description="Started watching",
        repo_id="web-service",
        path=Path("/home/user/projects/web-service"),
    )

    formatted = event.format()
    assert "\U0001f441\ufe0f" in formatted  # EYE
    assert "Started monitoring" in formatted
    assert "[web-service]" in formatted
    assert "/home/user/projects/web-service" in formatted


def test_monitoring_stop_event_creation() -> None:
    """Test creating a MonitoringStopEvent."""
    event = MonitoringStopEvent(
        description="Monitoring stopped",
        repo_id="old-project",
    )

    assert event.source == "monitor"
    assert event.repo_id == "old-project"


def test_monitoring_stop_event_format() -> None:
    """Test MonitoringStopEvent formatting."""
    event = MonitoringStopEvent(
        description="Stopped watching",
        repo_id="archived-project",
    )

    formatted = event.format()
    assert "\U0001f6d1" in formatted  # STOP SIGN
    assert "Stopped monitoring" in formatted
    assert "[archived-project]" in formatted


def test_all_monitor_events_have_monitor_source() -> None:
    """Test that all monitor events have 'monitor' as source."""
    file_event = FileChangeEvent(
        description="Test",
        repo_id="test",
        file_path=Path("/test.py"),
        change_type="modified",
    )

    start_event = MonitoringStartEvent(
        description="Test",
        repo_id="test",
        path=Path("/test"),
    )

    stop_event = MonitoringStopEvent(
        description="Test",
        repo_id="test",
    )

    assert file_event.source == "monitor"
    assert start_event.source == "monitor"
    assert stop_event.source == "monitor"


# 🔼⚙️🔚
