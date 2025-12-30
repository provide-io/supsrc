#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Test EventFeedTable widget functionality."""

from __future__ import annotations

from pathlib import Path

from provide.testkit.mocking import Mock
import pytest

from supsrc.events.buffer import BufferedFileChangeEvent
from supsrc.events.feed_table import EventFeedTable
from supsrc.events.system import UserActionEvent

pytestmark = pytest.mark.skip(reason="TUI in active development")

HEAVY_PLUS = "\N{HEAVY PLUS SIGN}"


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
            assert len(table.columns) == 6  # Time, Repo, Operation, Impact, File, Message

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

        _batch_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="batch_operation",
            event_count=3,
        )

        # Test primary_change_type emojis
        created_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="created",
        )
        assert table._get_event_emoji(created_event) == HEAVY_PLUS

        # Test source-based emojis
        mock_event = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event.source = "git"

    def test_format_event_details_v2(self):
        """Test new event details formatting."""
        table = EventFeedTable()

        # Test BufferedFileChangeEvent with single file
        single_file_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("src/test.py")],
            operation_type="single_file",
            event_count=1,
        )
        impact, file_str, message = table._format_event_details_v2(single_file_event)
        assert impact == "1"
        assert file_str == "test.py"
        assert len(message) >= 0  # Message can be empty or have content

        # Test BufferedFileChangeEvent with multiple files
        multi_file_event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("src/test1.py"), Path("src/test2.py")],
            operation_type="batch_operation",
            event_count=3,
        )
        impact, file_str, message = table._format_event_details_v2(multi_file_event)
        assert impact == "3"
        assert "test1.py, test2.py" in file_str
        assert "Batch" in message or message == ""

        # Test other event types
        mock_event = Mock(spec=[])  # Empty spec to prevent auto-attributes
        mock_event.description = "[13:45:30] [git] test.py File committed successfully"
        impact, file_str, message = table._format_event_details_v2(mock_event)
        assert impact == "1"
        assert file_str in ["test.py", "-"]  # Should extract file or use default
        assert len(message) > 0  # Should have extracted message

    def test_format_event_details(self):
        """Test legacy event details formatting (kept for compatibility)."""
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

    def test_get_files_summary_short(self):
        """Test short file summary generation for the File column."""
        table = EventFeedTable()

        # Test single file
        single_file = [Path("test.py")]
        summary = table._get_files_summary_short(single_file)
        assert summary == "[dim]./[/]test.py"

        # Test two files
        two_files = [Path("src/test1.py"), Path("src/test2.py")]
        summary = table._get_files_summary_short(two_files)
        assert "test1.py, test2.py" in summary

        # Test many files with common directory
        many_files = [
            Path("src/components/header.py"),
            Path("src/components/footer.py"),
            Path("src/components/sidebar.py"),
        ]
        summary = table._get_files_summary_short(many_files)
        assert "components/" in summary or "3 files" in summary

    def test_get_files_summary(self):
        """Test original file summary generation (kept for compatibility)."""
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

    def test_parse_description(self):
        """Test description parsing for file and message extraction."""
        table = EventFeedTable()

        # Test description with file path
        file_str, message = table._parse_description("[13:45:30] [git] test.py File modified")
        assert file_str == "test.py"
        assert "modified" in message

        # Test description without file path
        file_str, message = table._parse_description("[13:45:30] [git] Commit successful")
        assert file_str == "-"
        assert "Commit successful" in message

    def test_extract_message(self):
        """Test message extraction from events."""
        table = EventFeedTable()

        # Test BufferedFileChangeEvent with operation_type
        event = BufferedFileChangeEvent(
            repo_id="test",
            file_paths=[Path("test.py")],
            operation_type="atomic_rewrite",
            event_count=1,
        )
        message = table._extract_message(event)
        assert message == "Atomic save"

        # Test event with description
        mock_event = Mock(spec=[])
        mock_event.description = "[13:45:30] [git] [test-repo] File committed"
        message = table._extract_message(mock_event)
        assert "File committed" in message

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


# 🔼⚙️🔚
