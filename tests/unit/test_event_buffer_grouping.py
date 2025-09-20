# tests/unit/test_event_buffer_grouping.py

"""
Unit tests for EventBuffer grouping functionality.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from supsrc.events.buffer import BufferedFileChangeEvent, EventBuffer
from supsrc.events.monitor import FileChangeEvent


@pytest.fixture
def mock_emit_callback():
    """Mock callback for event emission."""
    return Mock()


@pytest.fixture
def batch_operation_events():
    """Sample events that simulate a batch operation."""
    base_path = Path("/test")
    return [
        FileChangeEvent(
            description="File 1 modified",
            repo_id="test_repo",
            file_path=base_path / "file1.py",
            change_type="modified",
        ),
        FileChangeEvent(
            description="File 2 modified",
            repo_id="test_repo",
            file_path=base_path / "file2.py",
            change_type="modified",
        ),
        FileChangeEvent(
            description="File 3 modified",
            repo_id="test_repo",
            file_path=base_path / "file3.py",
            change_type="modified",
        ),
        FileChangeEvent(
            description="File 4 modified",
            repo_id="test_repo",
            file_path=base_path / "file4.py",
            change_type="modified",
        ),
    ]


class TestEventBufferGrouping:
    """Test cases for EventBuffer grouping algorithms."""

    def test_simple_grouping_single_file(self, mock_emit_callback):
        """Test simple grouping with multiple events on same file."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        file_path = Path("/test/file.py")
        events = [
            FileChangeEvent(
                description="First change",
                repo_id="test_repo",
                file_path=file_path,
                change_type="created",
            ),
            FileChangeEvent(
                description="Second change",
                repo_id="test_repo",
                file_path=file_path,
                change_type="modified",
            ),
        ]

        # Process events directly through grouping
        grouped = buffer._group_events_simple(events)

        assert len(grouped) == 1
        buffered_event = grouped[0]
        assert isinstance(buffered_event, BufferedFileChangeEvent)
        assert buffered_event.repo_id == "test_repo"
        assert buffered_event.file_paths == [file_path]
        assert buffered_event.operation_type == "single_file"
        assert buffered_event.event_count == 2
        assert buffered_event.primary_change_type == "modified"  # Most recent

    def test_simple_grouping_multiple_files(self, mock_emit_callback):
        """Test simple grouping with events on different files."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        events = [
            FileChangeEvent(
                description="File 1 change",
                repo_id="test_repo",
                file_path=Path("/test/file1.py"),
                change_type="modified",
            ),
            FileChangeEvent(
                description="File 2 change",
                repo_id="test_repo",
                file_path=Path("/test/file2.py"),
                change_type="created",
            ),
        ]

        grouped = buffer._group_events_simple(events)

        assert len(grouped) == 2
        # Should create individual groups for each file
        for buffered_event in grouped:
            assert buffered_event.operation_type == "single_file"
            assert buffered_event.event_count == 1

    def test_smart_grouping_single_event(self, mock_emit_callback):
        """Test smart grouping with single event."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        event = FileChangeEvent(
            description="Single event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        grouped = buffer._group_events_smart([event])

        assert len(grouped) == 1
        buffered_event = grouped[0]
        assert buffered_event.operation_type == "single_file"
        assert buffered_event.event_count == 1

    def test_smart_grouping_batch_operation(self, mock_emit_callback, batch_operation_events):
        """Test smart grouping detects batch operations."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        grouped = buffer._group_events_smart(batch_operation_events)

        assert len(grouped) == 1
        buffered_event = grouped[0]
        assert buffered_event.operation_type == "batch_operation"
        assert buffered_event.event_count == 4
        assert len(buffered_event.file_paths) == 4

    def test_most_common_change_type(self, mock_emit_callback):
        """Test getting most common change type from events."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        events = [
            FileChangeEvent(
                description="Modified 1",
                repo_id="test_repo",
                file_path=Path("/test/file1.py"),
                change_type="modified",
            ),
            FileChangeEvent(
                description="Modified 2",
                repo_id="test_repo",
                file_path=Path("/test/file2.py"),
                change_type="modified",
            ),
            FileChangeEvent(
                description="Created",
                repo_id="test_repo",
                file_path=Path("/test/file3.py"),
                change_type="created",
            ),
        ]

        most_common = buffer._get_most_common_change_type(events)
        assert most_common == "modified"

    def test_create_single_event_group(self, mock_emit_callback):
        """Test creating a single event group."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        event = FileChangeEvent(
            description="Test event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        grouped_event = buffer._create_single_event_group(event)

        assert grouped_event.repo_id == "test_repo"
        assert grouped_event.file_paths == [Path("/test/file.py")]
        assert grouped_event.operation_type == "single_file"
        assert grouped_event.event_count == 1
        assert grouped_event.primary_change_type == "modified"

    def test_create_batch_operation_group(self, mock_emit_callback, batch_operation_events):
        """Test creating a batch operation group."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        grouped_event = buffer._create_batch_operation_group(batch_operation_events)

        assert grouped_event.repo_id == "test_repo"
        assert len(grouped_event.file_paths) == 4
        assert grouped_event.operation_type == "batch_operation"
        assert grouped_event.event_count == 4
        assert grouped_event.primary_change_type == "modified"

    def test_buffered_event_formatting(self):
        """Test formatting of buffered events."""
        # Test single file event
        single_event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/test/file.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="modified",
        )

        formatted = single_event.format()
        assert "test_repo" in formatted
        assert "file.py" in formatted
        assert "✏️" in formatted  # Modified emoji

        # Test atomic rewrite event
        atomic_event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/test/file.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
        )

        formatted = atomic_event.format()
        assert "atomic rewrite" in formatted
        assert "🔄" in formatted  # Atomic rewrite emoji

        # Test batch operation event
        batch_event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/test/file1.py"), Path("/test/file2.py")],
            operation_type="batch_operation",
            event_count=5,
            primary_change_type="modified",
        )

        formatted = batch_event.format()
        assert "Batch operation" in formatted
        assert "2 files" in formatted
        assert "📦" in formatted  # Batch operation emoji
