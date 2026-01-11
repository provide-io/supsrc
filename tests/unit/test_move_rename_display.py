#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Comprehensive tests for move/rename event display.

Tests cover:
- Simple moves (single file renamed)
- Move chains (multiple sequential renames)
- Edge cases (missing dest_path, empty history)
- Integration with buffering system"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent


class TestFileChangeEventDisplay:
    """Test FileChangeEvent formatting with dest_path."""

    def test_created_event_format(self):
        """Created events should not show destination."""
        event = FileChangeEvent(
            description="File created",
            repo_id="test_repo",
            file_path=Path("/repo/new_file.py"),
            change_type="created",
        )
        formatted = event.format()

        assert "new_file.py" in formatted
        assert "created" in formatted
        assert "→" not in formatted

    def test_modified_event_format(self):
        """Modified events should not show destination."""
        event = FileChangeEvent(
            description="File modified",
            repo_id="test_repo",
            file_path=Path("/repo/file.py"),
            change_type="modified",
        )
        formatted = event.format()

        assert "file.py" in formatted
        assert "modified" in formatted
        assert "→" not in formatted

    def test_deleted_event_format(self):
        """Deleted events should not show destination."""
        event = FileChangeEvent(
            description="File deleted",
            repo_id="test_repo",
            file_path=Path("/repo/old_file.py"),
            change_type="deleted",
        )
        formatted = event.format()

        assert "old_file.py" in formatted
        assert "deleted" in formatted
        assert "→" not in formatted

    def test_simple_move_event_format(self):
        """Move events should show source → destination."""
        event = FileChangeEvent(
            description="File moved",
            repo_id="test_repo",
            file_path=Path("/repo/bar.py"),
            change_type="moved",
            dest_path=Path("/repo/foo.py"),
        )
        formatted = event.format()

        assert "bar.py → foo.py" in formatted
        assert "→" in formatted

    def test_move_without_dest_path(self):
        """Move events without dest_path should fall back to simple format."""
        event = FileChangeEvent(
            description="File moved",
            repo_id="test_repo",
            file_path=Path("/repo/bar.py"),
            change_type="moved",
            dest_path=None,
        )
        formatted = event.format()

        assert "bar.py" in formatted
        assert "moved" in formatted


class TestBufferedFileChangeEventMoveChains:
    """Test BufferedFileChangeEvent move chain reconstruction."""

    def test_simple_move_display(self):
        """Single move should show source → dest."""
        operation_history = [
            {
                "path": Path("/repo/bar.py"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": Path("/repo/foo.py"),
            }
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/foo.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        formatted = event.format()
        assert "bar.py → foo.py" in formatted
        # Simple move should NOT show count
        assert "moves)" not in formatted

    def test_move_chain_display(self):
        """Multiple sequential moves should show full chain."""
        # Simulate: bar → bar.2 → foo → foo2
        operation_history = [
            {
                "path": Path("/repo/bar"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 12, 0, 0),
                "is_primary": False,
                "dest_path": Path("/repo/bar.2"),
            },
            {
                "path": Path("/repo/bar.2"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 12, 0, 1),
                "is_primary": False,
                "dest_path": Path("/repo/foo"),
            },
            {
                "path": Path("/repo/foo"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 12, 0, 2),
                "is_primary": True,
                "dest_path": Path("/repo/foo2"),
            },
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/foo2")],
            operation_type="single_file",
            event_count=3,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        formatted = event.format()
        assert "bar → bar.2 → foo → foo2" in formatted
        assert "(3 moves)" in formatted

    def test_move_chain_reconstruction_helper(self):
        """Test _reconstruct_move_chain helper method."""
        operation_history = [
            {
                "path": Path("/repo/a"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": False,
                "dest_path": Path("/repo/b"),
            },
            {
                "path": Path("/repo/b"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": Path("/repo/c"),
            },
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/c")],
            operation_type="single_file",
            event_count=2,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        chain = event._reconstruct_move_chain()
        assert chain == ["a", "b", "c"]

    def test_move_chain_empty_history(self):
        """Empty history should return empty chain."""
        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/foo")],
            operation_type="single_file",
            event_count=0,
            primary_change_type="moved",
            operation_history=[],
        )

        chain = event._reconstruct_move_chain()
        assert chain == []

    def test_move_chain_missing_dest_paths(self):
        """Move events without dest_path should be skipped."""
        operation_history = [
            {
                "path": Path("/repo/bar"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": None,  # Missing destination
            }
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/bar")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        chain = event._reconstruct_move_chain()
        assert chain == []

    def test_non_move_events_ignored(self):
        """Non-move events should not be included in chain."""
        operation_history = [
            {
                "path": Path("/repo/bar"),
                "change_type": "modified",  # Not a move
                "timestamp": datetime.now(),
                "is_primary": False,
                "dest_path": None,
            },
            {
                "path": Path("/repo/bar"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": Path("/repo/foo"),
            },
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/foo")],
            operation_type="single_file",
            event_count=2,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        chain = event._reconstruct_move_chain()
        # Only the move should be included
        assert chain == ["bar", "foo"]


class TestMoveOperationHistoryStorage:
    """Test that dest_path is properly stored in operation_history."""

    def test_operation_history_includes_dest_path(self):
        """Verify dest_path is stored in operation history."""
        operation_history = [
            {
                "path": Path("/repo/source.py"),
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": Path("/repo/dest.py"),
            }
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/dest.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        history = event.get_operation_history()
        assert len(history) == 1
        assert history[0]["dest_path"] == Path("/repo/dest.py")
        assert history[0]["change_type"] == "moved"

    def test_non_move_events_have_none_dest_path(self):
        """Non-move events should have None for dest_path."""
        operation_history = [
            {
                "path": Path("/repo/file.py"),
                "change_type": "modified",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": None,
            }
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/file.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="modified",
            operation_history=operation_history,
        )

        history = event.get_operation_history()
        assert history[0]["dest_path"] is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_atomic_rewrite_shows_files(self):
        """Atomic rewrite should show which files were updated."""
        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/file.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[],
        )

        formatted = event.format()
        assert "file.py" in formatted
        assert "modified" in formatted
        assert "→" not in formatted  # Should not show move arrow

    def test_batch_operation_shows_file_list(self):
        """Batch operations should show which files changed, not just 'Batch operation'."""
        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/file1.py"), Path("/repo/file2.py")],
            operation_type="batch_operation",
            event_count=2,
            primary_change_type="modified",
            operation_history=[],
        )

        formatted = event.format()
        # Should show file names
        assert "file1.py" in formatted
        assert "file2.py" in formatted
        assert "modified" in formatted
        # Should NOT say "Batch operation" (event count column shows that)
        assert "Batch" not in formatted
        assert "→" not in formatted

    def test_multiple_files_display(self):
        """Multiple files should be shown as comma-separated list."""
        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[
                Path("/repo/a.py"),
                Path("/repo/b.py"),
                Path("/repo/c.py"),
            ],
            operation_type="single_file",
            event_count=3,
            primary_change_type="modified",
            operation_history=[],
        )

        formatted = event.format()
        assert "a.py, b.py, c.py" in formatted
        assert "modified" in formatted

    def test_many_files_truncated(self):
        """When too many files, should truncate with '+N more'."""
        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[
                Path("/repo/file1.py"),
                Path("/repo/file2.py"),
                Path("/repo/file3.py"),
                Path("/repo/file4.py"),
                Path("/repo/file5.py"),
            ],
            operation_type="single_file",
            event_count=5,
            primary_change_type="modified",
            operation_history=[],
        )

        formatted = event.format()
        # Should show first 3 files
        assert "file1.py" in formatted
        assert "file2.py" in formatted
        assert "file3.py" in formatted
        # Should indicate there are more
        assert "+2 more" in formatted
        assert "modified" in formatted

    def test_path_as_string_in_history(self):
        """Handle paths stored as strings instead of Path objects."""
        operation_history = [
            {
                "path": "/repo/source.py",  # String instead of Path
                "change_type": "moved",
                "timestamp": datetime.now(),
                "is_primary": True,
                "dest_path": "/repo/dest.py",  # String instead of Path
            }
        ]

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("/repo/dest.py")],
            operation_type="single_file",
            event_count=1,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        chain = event._reconstruct_move_chain()
        assert chain == ["/repo/source.py", "/repo/dest.py"]


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_user_scenario_bar_to_foo2(self):
        """Test the exact user scenario: mv bar bar.2; mv bar.2 foo; mv foo foo2"""
        # Simulate the exact sequence from the user's example
        operation_history = [
            {
                "path": Path("/repo/bar"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 21, 37, 19, 0),
                "is_primary": False,
                "dest_path": Path("/repo/bar.2"),
            },
            {
                "path": Path("/repo/bar.2"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 21, 37, 19, 100000),
                "is_primary": False,
                "dest_path": Path("/repo/foo"),
            },
            {
                "path": Path("/repo/foo"),
                "change_type": "moved",
                "timestamp": datetime(2025, 1, 1, 21, 37, 19, 200000),
                "is_primary": True,
                "dest_path": Path("/repo/foo2"),
            },
        ]

        event = BufferedFileChangeEvent(
            repo_id="provide-foundation",
            file_paths=[Path("/repo/foo2")],
            operation_type="single_file",
            event_count=3,
            primary_change_type="moved",
            operation_history=operation_history,
        )

        formatted = event.format()

        # Should show the complete chain
        assert "bar → bar.2 → foo → foo2" in formatted
        # Should indicate it's a multi-move operation
        assert "(3 moves)" in formatted
        # Should have the repo_id
        assert "provide-foundation" in formatted


# 🔼⚙️🔚
