#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter output line building."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatterOutput:
    """Unit tests for ConsoleEventFormatter output line building."""

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
