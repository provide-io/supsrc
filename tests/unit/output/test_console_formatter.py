#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from pathlib import Path

from provide.testkit.mocking import Mock
from rich.console import Console

from supsrc.engines.git.events import GitCommitEvent, GitPushEvent
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent
from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatter:
    """Unit tests for ConsoleEventFormatter class."""

    def test_init_with_defaults(self):
        """Test formatter initialization with default parameters."""
        formatter = ConsoleEventFormatter()

        assert formatter.console is not None
        assert formatter.use_color is True
        assert formatter.use_ascii is False
        assert formatter.verbose is False
        assert formatter.terminal_width > 0

    def test_init_with_custom_console(self):
        """Test formatter initialization with custom console."""
        custom_console = Console(file=StringIO())
        formatter = ConsoleEventFormatter(console=custom_console)

        assert formatter.console is custom_console

    def test_init_with_custom_flags(self):
        """Test formatter initialization with custom flags."""
        formatter = ConsoleEventFormatter(
            use_color=False,
            use_ascii=True,
            verbose=True,
        )

        assert formatter.use_color is False
        assert formatter.use_ascii is True
        assert formatter.verbose is True

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        formatter = ConsoleEventFormatter()
        timestamp = datetime(2025, 10, 9, 14, 30, 45)

        result = formatter._format_timestamp(timestamp)

        assert result == "14:30:45"

    def test_strip_rich_markup_simple(self):
        """Test Rich markup stripping with simple tags."""
        formatter = ConsoleEventFormatter()

        text = "[bold]Hello[/bold] [cyan]World[/cyan]"
        result = formatter._strip_rich_markup(text)

        assert result == "Hello World"

    def test_strip_rich_markup_complex(self):
        """Test Rich markup stripping with complex tags."""
        formatter = ConsoleEventFormatter()

        text = "[bold cyan]2 files[/] modified in [dim]test.py[/dim]"
        result = formatter._strip_rich_markup(text)

        assert result == "2 files modified in test.py"

    def test_strip_rich_markup_nested(self):
        """Test Rich markup stripping with nested tags."""
        formatter = ConsoleEventFormatter()

        text = "[bold][cyan]Text[/cyan][/bold]"
        result = formatter._strip_rich_markup(text)

        assert result == "Text"

    def test_strip_rich_markup_no_markup(self):
        """Test Rich markup stripping with plain text."""
        formatter = ConsoleEventFormatter()

        text = "Plain text without markup"
        result = formatter._strip_rich_markup(text)

        assert result == text

    def test_truncate_short_text(self):
        """Test truncation with text shorter than max width."""
        formatter = ConsoleEventFormatter()

        result = formatter._truncate("short", 10)

        assert result == "short"

    def test_truncate_exact_length(self):
        """Test truncation with text exactly at max width."""
        formatter = ConsoleEventFormatter()

        result = formatter._truncate("exactly10!", 10)

        assert result == "exactly10!"

    def test_truncate_long_text(self):
        """Test truncation with text longer than max width."""
        formatter = ConsoleEventFormatter()

        result = formatter._truncate("this is a very long text", 10)

        assert result == "this is..."
        assert len(result) == 10

    def test_truncate_very_short_width(self):
        """Test truncation with very small max width."""
        formatter = ConsoleEventFormatter()

        result = formatter._truncate("test", 3)

        assert result == "..."

    def test_truncate_zero_width(self):
        """Test truncation with zero width."""
        formatter = ConsoleEventFormatter()

        result = formatter._truncate("test", 0)

        assert result == ""

    def test_extract_repo_id(self):
        """Test repository ID extraction from event."""
        formatter = ConsoleEventFormatter()

        event = FileChangeEvent(
            description="Test event",
            repo_id="test-repo",
            file_path=Path("test.py"),
            change_type="modified",
        )

        result = formatter._extract_repo_id(event)

        assert result == "test-repo"

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

        impact, file_str, message = formatter._format_event_details(event)

        # Verify no Rich markup in message
        assert (
            "[" not in message
            or "]" not in message
            or not any(tag in message for tag in ["bold", "cyan", "dim", "blue"])
        )

    def test_build_output_line_standard_layout(self):
        """Test output line building with standard terminal width."""
        output = StringIO()
        console = Console(file=output, width=120)
        formatter = ConsoleEventFormatter(console=console)

        result = formatter._build_output_line(
            timestamp="14:30:45",
            repo_id="test-repo",
            emoji="📝",
            impact="2",
            file_str="test.py",
            message="File modified",
        )

        # Should be a Rich Text object
        from rich.text import Text

        assert isinstance(result, Text)

        # Convert to string and verify content
        text_str = result.plain
        assert "14:30:45" in text_str
        assert "test-repo" in text_str
        assert "📝" in text_str
        assert "2" in text_str
        assert "test.py" in text_str
        assert "File modified" in text_str

    def test_build_output_line_narrow_layout(self):
        """Test output line building with narrow terminal width."""
        output = StringIO()
        console = Console(file=output, width=60)
        formatter = ConsoleEventFormatter(console=console)

        result = formatter._build_output_line(
            timestamp="14:30:45",
            repo_id="test-repo",
            emoji="📝",
            impact="2",
            file_str="test.py",
            message="File modified",
        )

        # Should still contain core elements
        text_str = result.plain
        assert "14:30:45" in text_str
        assert "test-repo" in text_str
        assert "📝" in text_str

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

    def test_format_and_print_with_verbose_disabled(self):
        """Test that verbose details are not shown when verbose=False."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=False,  # Verbose disabled
        )

        event = BufferedFileChangeEvent(
            repo_id="test-repo",
            file_paths=[Path("config.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".config.py.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".config.py.tmp"),
                    "dest_path": Path("config.py"),
                },
            ],
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should NOT show verbose details
        assert "Sequence" not in output_text
        assert "Operation:" not in output_text

    def test_format_and_print_with_verbose_enabled(self):
        """Test that verbose details are shown when verbose=True."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=True,  # Verbose enabled
        )

        event = BufferedFileChangeEvent(
            repo_id="test-repo",
            file_paths=[Path("config.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".config.py.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".config.py.tmp"),
                    "dest_path": Path("config.py"),
                },
            ],
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should show verbose details
        assert "atomic_rewrite" in output_text
        assert "Sequence" in output_text or "Operation" in output_text

    def test_format_and_print_handles_exceptions_gracefully(self):
        """Test that format_and_print handles errors without crashing."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console)

        # Create a mock event that will cause an error
        event = Mock()
        event.timestamp = None  # Will cause error in _format_timestamp

        # Should not raise an exception
        formatter.format_and_print(event)

        # Should log debug message, but not crash

    def test_print_startup_banner_basic(self):
        """Test printing startup banner with basic info."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console, use_color=False)

        formatter.print_startup_banner(
            repo_count=3,
            event_log_path=None,
            app_log_path=None,
        )

        output_text = output.getvalue()

        assert "3 repositories" in output_text or "3" in output_text
        assert "Supsrc Watch" in output_text or "supsrc" in output_text.lower()

    def test_print_startup_banner_with_log_paths(self):
        """Test printing startup banner with log paths."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(console=console, use_color=False)

        formatter.print_startup_banner(
            repo_count=5,
            event_log_path=Path("/tmp/events.jsonl"),
            app_log_path=Path("/tmp/app.log"),
        )

        output_text = output.getvalue()

        assert "5 repositories" in output_text or "5" in output_text
        assert "events.jsonl" in output_text
        assert "app.log" in output_text

    def test_print_startup_banner_verbose_mode(self):
        """Test startup banner shows verbose mode indicator."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=True,
        )

        formatter.print_startup_banner(
            repo_count=1,
            event_log_path=None,
            app_log_path=None,
        )

        output_text = output.getvalue()

        assert "Verbose" in output_text or "verbose" in output_text.lower()

    def test_get_terminal_width_fallback(self):
        """Test that terminal width detection has a fallback."""
        formatter = ConsoleEventFormatter()

        width = formatter._get_terminal_width()

        assert width > 0
        assert isinstance(width, int)

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

    def test_verbose_details_shows_operation_history(self):
        """Test that verbose mode shows operation history sequence."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=True,
        )

        event = BufferedFileChangeEvent(
            repo_id="test-repo",
            file_paths=[Path("document.txt")],
            operation_type="atomic_rewrite",
            event_count=4,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".document.txt.tmp")},
                {"change_type": "modified", "src_path": Path(".document.txt.tmp")},
                {"change_type": "modified", "src_path": Path(".document.txt.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".document.txt.tmp"),
                    "dest_path": Path("document.txt"),
                },
            ],
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should show sequence
        assert "Sequence" in output_text or "sequence" in output_text.lower()

        # Should show event count
        assert "4" in output_text

        # Should show the arrow (→) indicating a move operation
        assert "→" in output_text or "->" in output_text

    def test_verbose_details_shows_file_list(self):
        """Test that verbose mode shows list of files for multi-file events."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            verbose=True,
        )

        files = [Path(f"file{i}.py") for i in range(7)]

        event = BufferedFileChangeEvent(
            repo_id="test-repo",
            file_paths=files,
            operation_type="batch_operation",
            event_count=7,
            primary_change_type="modified",
            operation_history=[],
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should show file count
        assert "7" in output_text

        # Should show at least first 5 files
        for i in range(5):
            assert f"file{i}.py" in output_text

        # Should show "and X more" for remaining files
        assert "more" in output_text.lower()

    def test_use_ascii_mode(self):
        """Test that ASCII mode is used when enabled."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,  # ASCII mode
        )

        event = FileChangeEvent(
            description="File created",
            repo_id="test-repo",
            file_path=Path("new.py"),
            change_type="created",
        )

        formatter.format_and_print(event)

        output_text = output.getvalue()

        # Should use ASCII characters instead of emojis
        # The specific ASCII characters depend on EmojiMapper implementation
        # Just verify no emoji characters are present
        assert "📝" not in output_text
        assert "🚀" not in output_text
        assert "👁️" not in output_text


# 🔼⚙️🔚
