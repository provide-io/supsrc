#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for EventBuffer core functionality."""

from __future__ import annotations

import asyncio
from pathlib import Path

from provide.testkit.mocking import Mock
import pytest

from supsrc.events.buffer import EventBuffer
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


class TestEventBufferCore:
    """Test cases for EventBuffer core functionality."""

    def test_init_with_defaults(self, mock_emit_callback):
        """Test EventBuffer initialization with default parameters."""
        buffer = EventBuffer(emit_callback=mock_emit_callback)

        assert buffer.window_ms == 100  # Updated to match DEFAULT_BUFFER_WINDOW_MS
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
        """Test handling of empty events list - now tested via grouping module."""
        from supsrc.events.buffer.grouping import group_events_simple

        EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        # Test grouping function directly
        grouped = group_events_simple([])
        assert grouped == []

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

    def test_multiple_repos_isolation(self, mock_emit_callback):
        """Test that events from different repos are handled separately."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        # Add events from different repos
        buffer.add_event(
            FileChangeEvent(
                description="Repo 1 event",
                repo_id="repo1",
                file_path=Path("/test/file.py"),
                change_type="modified",
            )
        )

        buffer.add_event(
            FileChangeEvent(
                description="Repo 2 event",
                repo_id="repo2",
                file_path=Path("/test/file.py"),
                change_type="modified",
            )
        )

        # Should have separate buffers
        assert len(buffer._buffers) == 2
        assert "repo1" in buffer._buffers
        assert "repo2" in buffer._buffers


# 🔼⚙️🔚
