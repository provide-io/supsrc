#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for verbose output formatters."""

from __future__ import annotations

from pathlib import Path

from supsrc.engines.git.events import GitCommitEvent, GitPushEvent
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent
from supsrc.events.timer import TimerUpdateEvent
from supsrc.output.verbose_formats.compact import CompactVerboseFormatter
from supsrc.output.verbose_formats.table import TableVerboseFormatter


class TestTableVerboseFormatter:
    """Test table-style verbose formatter."""

    def test_buffered_event_formatting(self):
        """Test formatting of BufferedFileChangeEvent with table format."""
        formatter = TableVerboseFormatter(use_ascii=True, max_width=80)

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("test.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".test.py.tmp")},
                {"change_type": "modified", "src_path": Path(".test.py.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".test.py.tmp"),
                    "dest_path": Path("test.py"),
                },
            ],
        )

        lines = formatter.format_verbose_details(event)

        # Should produce table with box drawing
        assert len(lines) > 0
        assert "+" in lines[0]  # ASCII box character (top border)
        assert "BufferedFileChangeEvent" in "".join(lines)
        assert "atomic_rewrite" in "".join(lines)
        assert "3 raw events" in "".join(lines)

    def test_git_commit_formatting(self):
        """Test formatting of GitCommitEvent with table format."""
        formatter = TableVerboseFormatter(use_ascii=True, max_width=80)

        event = GitCommitEvent(
            description="Committed changes",
            repo_id="test_repo",
            commit_hash="abc123def456789",
            branch="main",
            files_changed=5,
        )

        lines = formatter.format_verbose_details(event)

        # Should show commit details
        assert len(lines) > 0
        assert "GitCommitEvent" in "".join(lines)
        assert "abc123def456" in "".join(lines)  # First 12 chars of hash
        assert "main" in "".join(lines)
        assert "5" in "".join(lines)

    def test_timer_update_formatting(self):
        """Test formatting of TimerUpdateEvent with table format."""
        formatter = TableVerboseFormatter(use_ascii=True, max_width=80)

        event = TimerUpdateEvent(
            description="Timer update",
            repo_id="test_repo",
            seconds_remaining=30,
            total_seconds=60,
            rule_name="inactivity",
        )

        lines = formatter.format_verbose_details(event)

        # Should show timer details and progress
        assert len(lines) > 0
        assert "30s" in "".join(lines)
        assert "60s" in "".join(lines)
        assert "50.0%" in "".join(lines)  # Progress calculation
        assert "inactivity" in "".join(lines)


class TestCompactVerboseFormatter:
    """Test compact key=value verbose formatter."""

    def test_buffered_event_formatting(self):
        """Test formatting of BufferedFileChangeEvent with compact format."""
        formatter = CompactVerboseFormatter(indent="  ")

        event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("test.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".test.py.tmp")},
                {"change_type": "modified", "src_path": Path(".test.py.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".test.py.tmp"),
                    "dest_path": Path("test.py"),
                },
            ],
        )

        lines = formatter.format_verbose_details(event)

        # Should produce compact key=value format
        assert len(lines) > 0
        full_output = "\n".join(lines)
        assert "type=BufferedFileChangeEvent" in full_output
        assert "op=atomic_rewrite" in full_output
        assert "change=modified" in full_output
        assert "count=3→1" in full_output
        assert "files: test.py" in full_output
        assert "seq:" in full_output

    def test_git_commit_formatting(self):
        """Test formatting of GitCommitEvent with compact format."""
        formatter = CompactVerboseFormatter(indent="  ")

        event = GitCommitEvent(
            description="Committed changes",
            repo_id="test_repo",
            commit_hash="abc123def456789",
            branch="main",
            files_changed=5,
        )

        lines = formatter.format_verbose_details(event)

        # Should show commit details in compact format
        assert len(lines) > 0
        full_output = "\n".join(lines)
        assert "type=GitCommitEvent" in full_output
        assert "hash=abc123def456" in full_output
        assert "branch=main" in full_output
        assert "files=5" in full_output

    def test_git_push_formatting(self):
        """Test formatting of GitPushEvent with compact format."""
        formatter = CompactVerboseFormatter(indent="  ")

        event = GitPushEvent(
            description="Pushed changes",
            repo_id="test_repo",
            remote="origin",
            branch="main",
            commits_pushed=2,
        )

        lines = formatter.format_verbose_details(event)

        # Should show push details in compact format
        assert len(lines) > 0
        full_output = "\n".join(lines)
        assert "type=GitPushEvent" in full_output
        assert "remote=origin" in full_output
        assert "branch=main" in full_output
        assert "commits=2" in full_output

    def test_file_change_formatting(self):
        """Test formatting of FileChangeEvent with compact format."""
        formatter = CompactVerboseFormatter(indent="  ")

        event = FileChangeEvent(
            description="File modified",
            repo_id="test_repo",
            file_path=Path("/test/file.py"),
            change_type="modified",
        )

        lines = formatter.format_verbose_details(event)

        # Should show basic file change info
        assert len(lines) > 0
        full_output = "\n".join(lines)
        assert "type=FileChangeEvent" in full_output
        assert "change=modified" in full_output


# 🔼⚙️🔚
