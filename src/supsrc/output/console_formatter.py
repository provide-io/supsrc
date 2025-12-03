#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from rich.console import Console
from rich.text import Text

from supsrc.events.feed_table.formatters import EventFormatter
from supsrc.output.emoji_map import EmojiMapper
from supsrc.output.verbose_formats import CompactVerboseFormatter, TableVerboseFormatter
from supsrc.output.verbose_formats.base import VerboseFormatter

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("output.console_formatter")


class ConsoleEventFormatter:
    """Formats events for console output in headless mode."""

    def __init__(
        self,
        console: Console | None = None,
        use_color: bool = True,
        use_ascii: bool = False,
        verbose: bool = False,
        verbose_format: str = "table",
    ):
        """Initialize console formatter.

        Args:
            console: Rich Console instance (creates new if None)
            use_color: Enable color output
            use_ascii: Use ASCII instead of emojis
            verbose: Show verbose event details
            verbose_format: Verbose output format ("table" or "compact")
        """
        self.console = console or Console()
        self.use_color = use_color
        self.use_ascii = use_ascii
        self.verbose = verbose
        self.verbose_format = verbose_format
        self.terminal_width = self._get_terminal_width()

        # Initialize verbose formatter based on format choice
        self.verbose_formatter: VerboseFormatter
        if verbose_format == "compact":
            self.verbose_formatter = CompactVerboseFormatter(indent="  ")
        else:  # default to table
            self.verbose_formatter = TableVerboseFormatter(
                use_ascii=use_ascii, max_width=self.terminal_width
            )

    def _get_terminal_width(self) -> int:
        """Get current terminal width."""
        try:
            width, _ = shutil.get_terminal_size(fallback=(80, 24))
            return width
        except Exception:
            return 80

    def format_and_print(self, event: Event) -> None:
        """Format and print an event to console.

        Args:
            event: Event to format and print
        """
        try:
            # Extract basic event information
            timestamp = self._format_timestamp(event.timestamp)
            repo_id = self._extract_repo_id(event)
            emoji = EmojiMapper.get_event_emoji(event, self.use_ascii)
            impact, file_str, message = self._format_event_details(event)

            # Build the output line
            line = self._build_output_line(timestamp, repo_id, emoji, impact, file_str, message)

            self._print_renderable(line)

            # Print verbose details if enabled
            if self.verbose:
                self._print_verbose_details(event, timestamp, repo_id)

        except Exception as e:
            log.debug(
                "Failed to format event for console", error=str(e), event_type=type(event).__name__
            )

    def _format_timestamp(self, timestamp: datetime) -> str:
        """Format timestamp as HH:MM:SS."""
        return timestamp.strftime("%H:%M:%S")

    def _extract_repo_id(self, event: Event) -> str:
        """Extract repository ID from event."""
        return EventFormatter.extract_repo_id(event)

    def _format_event_details(self, event: Event) -> tuple[str, str, str]:
        """Format event details using TUI's EventFormatter.

        Returns:
            Tuple of (impact_str, file_str, message_str)
        """
        impact, file_str, message = EventFormatter.format_event_details(event)

        # Strip Rich markup from message for console output
        # The TUI formatter returns markup like "[bold cyan]2 files[/]" which needs to be cleaned
        message = self._strip_rich_markup(message)

        return impact, file_str, message

    def _strip_rich_markup(self, text: str) -> str:
        """Remove Rich markup tags from text.

        Args:
            text: Text potentially containing Rich markup like [bold]text[/]

        Returns:
            Text with markup removed
        """
        import re

        # Remove all [tag] and [/] style markup
        return re.sub(r"\[/?[^\]]+\]", "", text)

    def _build_output_line(
        self,
        timestamp: str,
        repo_id: str,
        emoji: str,
        impact: str,
        file_str: str,
        message: str,
    ) -> Text:
        """Build formatted output line with proper column widths.

        Args:
            timestamp: Formatted timestamp (HH:MM:SS)
            repo_id: Repository identifier
            emoji: Event emoji or ASCII
            impact: Impact count
            file_str: File information
            message: Event message

        Returns:
            Rich Text object with formatted line
        """
        # Calculate available width
        width = self.terminal_width

        # Fixed column widths
        time_width = 8  # HH:MM:SS
        repo_width = 20
        emoji_width = 3
        impact_width = 4

        # Check if we have enough space for standard layout
        if width >= 80:
            # Standard layout
            file_width = 20
            message_width = max(
                20, width - time_width - repo_width - emoji_width - impact_width - file_width - 15
            )
        else:
            # Narrow layout - reduce file width but still show it
            file_width = 12
            message_width = max(10, width - time_width - repo_width - emoji_width - file_width - 10)

        # Truncate fields to fit
        repo_id_display = self._truncate(repo_id, repo_width)
        file_display = self._truncate(file_str, file_width)  # Always show files
        impact_display = self._truncate(impact, impact_width) if width >= 80 else ""
        message_display = self._truncate(message, message_width)

        # Build the line with Rich styling
        text = Text()

        # [HH:MM:SS]
        text.append(f"[{timestamp}] ", style="dim")

        # [repo-id]
        text.append(f"[{repo_id_display:^{repo_width}}] ", style="cyan")

        # [emoji]
        text.append(f"[{emoji:^{emoji_width}}] ")

        if width >= 80:
            # [impact]
            text.append(f"[{impact_display:^{impact_width}}] ", style="bold")

        # [files] - Always show files, even in narrow mode
        text.append(f"[{file_display:<{file_width}}] ", style="blue")

        # [message]
        text.append(f"[{message_display}]", style="default")

        return text

    def _truncate(self, text: str, max_width: int) -> str:
        """Truncate text to fit within max_width with ellipsis.

        Args:
            text: Text to truncate
            max_width: Maximum width

        Returns:
            Truncated text
        """
        if len(text) <= max_width:
            return text

        if max_width <= 3:
            return "..."[:max_width]

        return text[: max_width - 3] + "..."

    def print_startup_banner(
        self, repo_count: int, event_log_path: Path | None, app_log_path: Path | None
    ) -> None:
        """Print startup banner with monitoring information.

        Args:
            repo_count: Number of repositories being monitored
            event_log_path: Path to event log file
            app_log_path: Path to application log file
        """
        separator = "━" * min(80, self.terminal_width)

        self.console.print(separator, style="bold blue")
        self.console.print("🚀 Supsrc Watch - Event Stream Mode", style="bold cyan")

        if event_log_path:
            self.console.print(f"📝 Event Log: {event_log_path}", style="dim")

        if app_log_path:
            self.console.print(f"📋 App Log: {app_log_path}", style="dim")

        self.console.print(separator, style="bold blue")

        if self.verbose:
            self.console.print("🔍 Verbose mode: ON", style="yellow")

        self.console.print()  # Blank line

    def _print_verbose_details(self, event: Event, timestamp: str, repo_id: str) -> None:
        """Print detailed verbose information about an event.

        Args:
            event: Event to detail
            timestamp: Formatted timestamp
            repo_id: Repository ID
        """
        # Use the configured verbose formatter
        detail_lines = self.verbose_formatter.format_verbose_details(event)

        # Print each line
        for line in detail_lines:
            self._print_renderable(line)

    def _print_renderable(self, renderable: Text | str) -> None:
        """Print a renderable with or without color support."""
        if self.use_color:
            self.console.print(renderable)
            return

        if isinstance(renderable, Text):
            plain_text = renderable.plain
        else:
            plain_text = self._strip_rich_markup(str(renderable))

        output_stream = getattr(self.console, "file", sys.stdout)
        if not plain_text.endswith("\n"):
            plain_text = f"{plain_text}\n"
        output_stream.write(plain_text)
        output_stream.flush()


# 🔼⚙️🔚
