#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter utility methods."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from supsrc.events.monitor import FileChangeEvent
from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatterUtilities:
    """Unit tests for ConsoleEventFormatter utility methods."""

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

    def test_get_terminal_width_fallback(self):
        """Test that terminal width detection has a fallback."""
        formatter = ConsoleEventFormatter()

        width = formatter._get_terminal_width()

        assert width > 0
        assert isinstance(width, int)
