#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for EventBuffer grouping functionality."""

from __future__ import annotations

from pathlib import Path

from provide.testkit.mocking import Mock
import pytest

from supsrc.events.buffer import BufferedFileChangeEvent
from supsrc.events.buffer.converters import create_single_event_group
from supsrc.events.buffer.grouping import group_events_simple
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

        # Process events directly through grouping module
        grouped = group_events_simple(events)

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

        grouped = group_events_simple(events)

        assert len(grouped) == 2
        # Should create individual groups for each file
        for buffered_event in grouped:
            assert buffered_event.operation_type == "single_file"
            assert buffered_event.event_count == 1

    def test_smart_grouping_single_event(self, mock_emit_callback):
        """Test smart grouping with single event - now uses streaming handler."""
        # Smart mode uses streaming detection, not batch grouping
        # Test the converter function instead
        event = FileChangeEvent(
            description="Single event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        buffered_event = create_single_event_group(event)

        assert buffered_event.operation_type == "single_file"
        assert buffered_event.event_count == 1

    def test_smart_grouping_batch_operation(self, mock_emit_callback, batch_operation_events):
        """Test smart grouping via simple grouping fallback."""
        # Smart mode uses streaming detection via Foundation
        # Test simple grouping as a representative of the non-streaming path
        grouped = group_events_simple(batch_operation_events)

        # Simple grouping creates one event per file
        assert len(grouped) == 4

        # Verify all files are represented
        all_paths = []
        for event in grouped:
            all_paths.extend(event.file_paths)

        expected_paths = [
            Path("/test/file1.py"),
            Path("/test/file2.py"),
            Path("/test/file3.py"),
            Path("/test/file4.py"),
        ]
        for expected_path in expected_paths:
            assert expected_path in all_paths

    # test_most_common_change_type removed - _get_most_common_change_type no longer exists
    # This helper was moved to foundation's operation detector

    def test_create_single_event_group(self, mock_emit_callback):
        """Test creating a single event group via converter."""
        event = FileChangeEvent(
            description="Test event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        grouped_event = create_single_event_group(event)

        assert grouped_event.repo_id == "test_repo"
        assert grouped_event.file_paths == [Path("/test/file.py")]
        assert grouped_event.operation_type == "single_file"
        assert grouped_event.event_count == 1
        assert grouped_event.primary_change_type == "modified"

    # test_create_batch_operation_group removed - _create_batch_operation_group no longer exists
    # Batch operation grouping is now handled by foundation's OperationDetector

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
        # Atomic rewrite now shows the actual operation (modified) not "Updated"
        assert "modified" in formatted
        assert "file.py" in formatted
        assert "✏️" in formatted  # Uses the primary_change_type emoji

        # Test batch operation event
        batch_event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/test/file1.py"), Path("/test/file2.py")],
            operation_type="batch_operation",
            event_count=5,
            primary_change_type="modified",
        )

        formatted = batch_event.format()
        # Batch operations now show actual file list, not "Batch operation"
        assert "file1.py" in formatted
        assert "file2.py" in formatted
        assert "modified" in formatted
        assert "✏️" in formatted  # Uses operation emoji, not batch emoji


# 🔼⚙️🔚
