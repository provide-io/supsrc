#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter verbose mode and startup banner."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from provide.testkit.mocking import Mock
from rich.console import Console

from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent
from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatterVerbose:
    """Unit tests for ConsoleEventFormatter verbose mode and startup banner."""

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
