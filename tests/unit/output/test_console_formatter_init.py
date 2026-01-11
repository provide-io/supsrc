#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ConsoleEventFormatter initialization."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleEventFormatterInit:
    """Unit tests for ConsoleEventFormatter initialization."""

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
