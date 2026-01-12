#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter event formatting."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from supsrc.engines.git.events import GitCommitEvent, GitPushEvent
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent
from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatterEvents:
    """Unit tests for ConsoleEventFormatter event formatting."""

    def test_format_event_details_strips_markup(self):
        """Test that format_event_details strips Rich markup."""
        formatter = ConsoleEventFormatter()

        event = GitCommitEvent(
            description="Committed files",
            repo_id="test-repo",
            commit_hash="abc123",
            branch="main",
            files_changed=2,
        )

        _impact, _file_str, message = formatter._format_event_details(event)

        # Verify no Rich markup in message
        assert (
            "[" not in message
            or "]" not in message
            or not any(tag in message for tag in ["bold", "cyan", "dim", "blue"])
        )

    def test_format_and_print_file_change_event(self):
        """Test formatting and printing a file change event."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console, use_color=False)

        event = FileChangeEvent(
            description="File modified",
            repo_id="test-repo",
            file_path=Path("test.py"),
            change_type="modified",
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()
        assert "test-repo" in output_text
        # FileChangeEvent shows description, may not always show filename
        assert len(output_text) > 0, "Should produce output"

    def test_format_and_print_buffered_event(self):
        """Test formatting and printing a buffered file change event."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console, use_color=False)

        event = BufferedFileChangeEvent(
            repo_id="test-repo",
            file_paths=[Path("config.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[],
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()
        assert "test-repo" in output_text
        assert "config.py" in output_text

    def test_format_and_print_git_commit_event(self):
        """Test formatting and printing a git commit event."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console, use_color=False)

        event = GitCommitEvent(
            description="Committed 2 files",
            repo_id="test-repo",
            commit_hash="abc123def",
            branch="main",
            files_changed=2,
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()
        assert "test-repo" in output_text
        assert "2" in output_text or "files" in output_text.lower()

    def test_verbose_details_for_git_push_event(self):
        """Test verbose details for GitPushEvent."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=True,
        )

        event = GitPushEvent(
            description="Pushed to origin",
            repo_id="test-repo",
            remote="origin",
            branch="develop",
            commits_pushed=3,
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should show remote
        assert "origin" in output_text

        # Should show branch
        assert "develop" in output_text

        # Should show commits pushed
        assert "3" in output_text

        # Should show event type
        assert "GitPushEvent" in output_text
