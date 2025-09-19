# tests/unit/test_event_buffer.py

"""
Unit tests for the EventBuffer class.
"""

from __future__ import annotations

import asyncio
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
def sample_file_change_event():
    """Sample FileChangeEvent for testing."""
    return FileChangeEvent(
        description="Test file change",
        repo_id="test_repo",
        file_path=Path("/test/file.py"),
        change_type="modified",
    )


@pytest.fixture
def atomic_rewrite_events():
    """Sample events that simulate an atomic file rewrite."""
    base_path = Path("/test")
    return [
        FileChangeEvent(
            description="Create temp file",
            repo_id="test_repo",
            file_path=base_path / ".file.py.tmp",
            change_type="created",
        ),
        FileChangeEvent(
            description="Modify original",
            repo_id="test_repo",
            file_path=base_path / "file.py",
            change_type="modified",
        ),
        FileChangeEvent(
            description="Delete original",
            repo_id="test_repo",
            file_path=base_path / "file.py",
            change_type="deleted",
        ),
        FileChangeEvent(
            description="Move temp to original",
            repo_id="test_repo",
            file_path=base_path / "file.py",
            change_type="moved",
        ),
    ]


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


class TestEventBuffer:
    """Test cases for EventBuffer class."""

    def test_init_with_defaults(self, mock_emit_callback):
        """Test EventBuffer initialization with default parameters."""
        buffer = EventBuffer(emit_callback=mock_emit_callback)

        assert buffer.window_ms == 200
        assert buffer.grouping_mode == "smart"
        assert buffer.emit_callback == mock_emit_callback
        assert buffer._buffers == {}
        assert buffer._timers == {}

    def test_init_with_custom_params(self, mock_emit_callback):
        """Test EventBuffer initialization with custom parameters."""
        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        assert buffer.window_ms == 500
        assert buffer.grouping_mode == "simple"
        assert buffer.emit_callback == mock_emit_callback

    def test_passthrough_mode(self, mock_emit_callback, sample_file_change_event):
        """Test that 'off' mode passes events through immediately."""
        buffer = EventBuffer(
            grouping_mode="off",
            emit_callback=mock_emit_callback,
        )

        buffer.add_event(sample_file_change_event)

        # Should emit immediately
        mock_emit_callback.assert_called_once_with(sample_file_change_event)
        assert len(buffer._buffers) == 0

    @pytest.mark.asyncio
    async def test_basic_buffering(self, mock_emit_callback, sample_file_change_event):
        """Test basic event buffering with timer."""
        buffer = EventBuffer(
            window_ms=50,  # Short window for testing
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        # Add event to buffer
        buffer.add_event(sample_file_change_event)

        # Should not emit immediately
        mock_emit_callback.assert_not_called()
        assert len(buffer._buffers["test_repo"]) == 1

        # Wait for timer to fire
        await asyncio.sleep(0.1)

        # Should have emitted after timer
        mock_emit_callback.assert_called_once()
        assert len(buffer._buffers) == 0  # Buffer should be cleared

    def test_timer_reset_on_multiple_events(self, mock_emit_callback):
        """Test that timer resets when multiple events are added quickly."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        event1 = FileChangeEvent(
            description="First event",
            repo_id="test_repo",
            file_path=Path("/test/file1.py"),
            change_type="modified",
        )
        event2 = FileChangeEvent(
            description="Second event",
            repo_id="test_repo",
            file_path=Path("/test/file2.py"),
            change_type="modified",
        )

        # Add first event
        buffer.add_event(event1)
        assert len(buffer._buffers["test_repo"]) == 1

        # Add second event quickly
        buffer.add_event(event2)
        assert len(buffer._buffers["test_repo"]) == 2

        # Should have one active timer
        assert "test_repo" in buffer._timers

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

    def test_smart_grouping_single_event(self, mock_emit_callback, sample_file_change_event):
        """Test smart grouping with single event."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        grouped = buffer._group_events_smart([sample_file_change_event])

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

    def test_atomic_rewrite_pattern_detection(self, mock_emit_callback):
        """Test detection of atomic rewrite patterns."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create temp",
                repo_id="test_repo",
                file_path=base_path / "file.py.tmp",
                change_type="created",
            ),
            FileChangeEvent(
                description="Delete original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="deleted",
            ),
        ]

        # Test temp file pattern detection
        temp_patterns = buffer._find_temp_file_patterns(events)

        # Should detect the pattern
        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / "file.py.tmp" in temp_patterns[original_path]

    def test_temp_file_pattern_detection_tilde(self, mock_emit_callback):
        """Test detection of temp files with tilde suffix."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create backup",
                repo_id="test_repo",
                file_path=base_path / "file.py~",
                change_type="created",
            ),
            FileChangeEvent(
                description="Modify original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="modified",
            ),
        ]

        temp_patterns = buffer._find_temp_file_patterns(events)

        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / "file.py~" in temp_patterns[original_path]

    def test_temp_file_pattern_detection_hidden(self, mock_emit_callback):
        """Test detection of hidden temp files."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create hidden temp",
                repo_id="test_repo",
                file_path=base_path / ".file.py.abcd1234",
                change_type="created",
            ),
            FileChangeEvent(
                description="Modify original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="modified",
            ),
        ]

        temp_patterns = buffer._find_temp_file_patterns(events)

        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / ".file.py.abcd1234" in temp_patterns[original_path]

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

    def test_flush_all(self, mock_emit_callback):
        """Test flushing all pending buffers."""
        buffer = EventBuffer(
            window_ms=1000,  # Long window to prevent automatic flushing
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        # Add events to multiple repos
        buffer.add_event(
            FileChangeEvent(
                description="Repo 1 event",
                repo_id="repo1",
                file_path=Path("/test/file1.py"),
                change_type="modified",
            )
        )
        buffer.add_event(
            FileChangeEvent(
                description="Repo 2 event",
                repo_id="repo2",
                file_path=Path("/test/file2.py"),
                change_type="modified",
            )
        )

        assert len(buffer._buffers) == 2
        assert len(buffer._timers) == 2

        # Flush all
        buffer.flush_all()

        # Should have emitted events for both repos
        assert mock_emit_callback.call_count == 2
        assert len(buffer._buffers) == 0
        assert len(buffer._timers) == 0

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

    @pytest.mark.asyncio
    async def test_event_loop_integration(self, mock_emit_callback):
        """Test EventBuffer integration with asyncio event loop."""
        buffer = EventBuffer(
            window_ms=50,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        event = FileChangeEvent(
            description="Test event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        # Ensure we're in an event loop
        loop = asyncio.get_running_loop()
        assert loop is not None

        # Add event
        buffer.add_event(event)

        # Should not emit immediately
        mock_emit_callback.assert_not_called()

        # Wait for timer
        await asyncio.sleep(0.1)

        # Should have emitted
        mock_emit_callback.assert_called_once()

    def test_empty_events_list(self, mock_emit_callback):
        """Test handling of empty events list."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        # Test with empty list
        grouped = buffer._group_events_simple([])
        assert grouped == []

        grouped = buffer._group_events_smart([])
        assert grouped == []

        # Test _get_most_common_change_type with empty list
        most_common = buffer._get_most_common_change_type([])
        assert most_common == "modified"  # Default fallback

    def test_no_callback_handling(self):
        """Test EventBuffer behavior when no callback is provided."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="off",
            emit_callback=None,
        )

        event = FileChangeEvent(
            description="Test event",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        # Should not raise an exception
        buffer.add_event(event)
