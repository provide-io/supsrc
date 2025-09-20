# tests/unit/test_event_feed_table.py

"""Test EventFeedTable widget functionality."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from supsrc.events.buffer import BufferedFileChangeEvent
from supsrc.events.feed_table import EventFeedTable
from supsrc.events.system import UserActionEvent


class TestEventFeedTable:
    """Test EventFeedTable widget."""

    @pytest.mark.asyncio
    async def test_event_feed_table_initialization(self):
        """Test that EventFeedTable initializes properly."""
        table = EventFeedTable()

        # Test in a textual app context
        from textual.app import App

        class TestApp(App[None]):
            def compose(self):
                yield table

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Should have columns set up - check via columns property
            assert len(table.columns) == 5  # Time, Repo, Type, Count, Files

            # Should have initial messages
            assert table.row_count >= 2  # Ready message + mounted message

    @pytest.mark.asyncio
    async def test_add_simple_event(self):
        """Test adding a simple event to the table."""
        table = EventFeedTable()

        from textual.app import App

        class TestApp(App[None]):
            def compose(self):
                yield table

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Create a simple event
            event = UserActionEvent(
                description="Test event description",
                action="test",
                target="test_target",
            )

            # Add the event
            table.add_event(event)

            # Should have added a new row
            assert table.row_count >= 3  # 2 initial + 1 new event

    @pytest.mark.asyncio
    async def test_add_buffered_file_change_event(self):
        """Test adding a BufferedFileChangeEvent to the table."""
        table = EventFeedTable()

        from textual.app import App

        class TestApp(App[None]):
            def compose(self):
                yield table

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Create a buffered file change event
            event = BufferedFileChangeEvent(
                repo_id="test-repo",
                file_paths=[Path("src/test.py"), Path("src/other.py")],
                operation_type="batch_operation",
                event_count=5,
                primary_change_type="modified",
            )

            # Add the event
            table.add_event(event)

            # Should have added a new row
            assert table.row_count >= 3  # 2 initial + 1 new event

    def test_extract_repo_id(self):
        """Test repository ID extraction."""
        table = EventFeedTable()

        # Test with BufferedFileChangeEvent
        buffered_event = BufferedFileChangeEvent(
            repo_id="my-repo",
            file_paths=[Path("test.py")],
            operation_type="single_file",
            event_count=1,
        )
        assert table._extract_repo_id(buffered_event) == "my-repo"

        # Test with description containing [repo]
        mock_event = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event.description = "[13:45:30] [git] [my-repo] Commit successful"
        mock_event.source = "git"
        assert table._extract_repo_id(mock_event) == "my-repo"

        # Test fallback to source
        mock_event2 = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event2.description = "Simple description"
        mock_event2.source = "git"
        assert table._extract_repo_id(mock_event2) == "git"

    def test_get_event_emoji(self):
        """Test emoji selection for different event types."""
        table = EventFeedTable()

        # Test BufferedFileChangeEvent emojis
        atomic_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="atomic_rewrite",
            event_count=1,
        )
        assert table._get_event_emoji(atomic_event) == "🔄"

        batch_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="batch_operation",
            event_count=3,
        )
        assert table._get_event_emoji(batch_event) == "📦"

        # Test primary_change_type emojis
        created_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="created",
        )
        assert table._get_event_emoji(created_event) == "➕"

        # Test source-based emojis
        mock_event = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event.source = "git"
        assert table._get_event_emoji(mock_event) == "🔧"

    def test_format_event_details(self):
        """Test event details formatting."""
        table = EventFeedTable()

        # Test BufferedFileChangeEvent with single file
        single_file_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("src/test.py")],
            operation_type="single_file",
            event_count=1,
        )
        count, files = table._format_event_details(single_file_event)
        assert count == "1"
        assert files == "test.py"

        # Test BufferedFileChangeEvent with multiple files
        multi_file_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("src/test1.py"), Path("src/test2.py")],
            operation_type="batch_operation",
            event_count=3,
        )
        count, files = table._format_event_details(multi_file_event)
        assert count == "3"
        assert "test1.py, test2.py" in files

        # Test other event types
        mock_event = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event.description = "[13:45:30] [git] File committed successfully"
        count, files = table._format_event_details(mock_event)
        assert count == "1"
        assert "File committed successfully" in files

    def test_get_files_summary(self):
        """Test file summary generation."""
        table = EventFeedTable()

        # Test single file
        single_file = [Path("test.py")]
        summary = table._get_files_summary(single_file)
        assert summary == "test.py"

        # Test multiple files with common directory
        multi_files = [
            Path("src/components/header.py"),
            Path("src/components/footer.py"),
            Path("src/components/sidebar.py"),
        ]
        summary = table._get_files_summary(multi_files)
        assert "header.py, footer.py, sidebar.py" in summary

        # Test many files
        many_files = [Path(f"src/file{i}.py") for i in range(10)]
        summary = table._get_files_summary(many_files)
        assert "10 files" in summary

    @pytest.mark.asyncio
    async def test_clear_functionality(self):
        """Test clearing the event feed table."""
        table = EventFeedTable()

        from textual.app import App

        class TestApp(App[None]):
            def compose(self):
                yield table

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Add some events
            event1 = UserActionEvent(description="Event 1", action="test", target="test")
            event2 = UserActionEvent(description="Event 2", action="test", target="test")

            table.add_event(event1)
            table.add_event(event2)

            initial_count = table.row_count
            assert initial_count >= 4  # 2 initial + 2 events

            # Clear the table
            table.clear()

            # Should only have the "cleared" message
            assert table.row_count == 1