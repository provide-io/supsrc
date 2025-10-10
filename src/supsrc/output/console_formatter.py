"""Console event formatter for headless mode."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from rich.console import Console
from rich.text import Text

from supsrc.events.feed_table.formatters import EventFormatter
from supsrc.output.emoji_map import EmojiMapper

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
    ):
        """Initialize console formatter.

        Args:
            console: Rich Console instance (creates new if None)
            use_color: Enable color output
            use_ascii: Use ASCII instead of emojis
            verbose: Show verbose event details
        """
        self.console = console or Console()
        self.use_color = use_color
        self.use_ascii = use_ascii
        self.verbose = verbose
        self.terminal_width = self._get_terminal_width()

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

            # Print to console
            if self.use_color:
                self.console.print(line)
            else:
                # Strip Rich markup for no-color mode
                self.console.print(line, highlight=False, markup=False)

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
            # Narrow layout - hide some columns
            file_width = 15
            message_width = max(15, width - time_width - repo_width - emoji_width - 10)

        # Truncate fields to fit
        repo_id_display = self._truncate(repo_id, repo_width)
        file_display = self._truncate(file_str, file_width) if width >= 80 else ""
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

            # [files]
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
        self.console.print(f"📁 Monitoring: {repo_count} repositories", style="cyan")

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

        details = []
        event_type = type(event).__name__

        # Event type and source
        details.append(f"  [dim]Type:[/dim] {event_type}")
        details.append(f"  [dim]Source:[/dim] {getattr(event, 'source', 'unknown')}")

        # TimerUpdateEvent details
        if event_type == "TimerUpdateEvent":
            if hasattr(event, "seconds_remaining"):
                details.append(f"  [dim]Time Remaining:[/dim] [yellow]{event.seconds_remaining}s[/yellow]")
            if hasattr(event, "total_seconds"):
                details.append(f"  [dim]Total Time:[/dim] {event.total_seconds}s")
            if hasattr(event, "rule_name") and event.rule_name:
                details.append(f"  [dim]Rule:[/dim] {event.rule_name}")

        # BufferedFileChangeEvent - show atomic operation details
        if hasattr(event, "operation_type"):
            details.append(f"  [dim]Operation:[/dim] [cyan]{event.operation_type}[/cyan]")

            if hasattr(event, "primary_change_type"):
                details.append(
                    f"  [dim]Change Type:[/dim] [yellow]{event.primary_change_type}[/yellow]"
                )

            # Show file paths involved
            if hasattr(event, "file_paths"):
                file_paths = event.file_paths
                if len(file_paths) == 1:
                    details.append(f"  [dim]File:[/dim] {file_paths[0]}")
                elif len(file_paths) > 1:
                    details.append(f"  [dim]Files ({len(file_paths)}):[/dim]")
                    for fp in file_paths[:5]:  # Show first 5
                        details.append(f"    • {fp.name}")
                    if len(file_paths) > 5:
                        details.append(f"    ... and {len(file_paths) - 5} more")

            # Show operation sequence from operation_history
            if hasattr(event, "operation_history") and event.operation_history:
                details.append(f"  [dim]Sequence ({len(event.operation_history)} events):[/dim]")
                for i, op in enumerate(event.operation_history[:10], 1):  # Show first 10
                    change_type = op.get("change_type", "unknown")
                    src_path = op.get("src_path")
                    dest_path = op.get("dest_path")

                    if dest_path:
                        details.append(
                            f"    {i}. [{change_type}] {src_path.name if hasattr(src_path, 'name') else src_path} → {dest_path.name if hasattr(dest_path, 'name') else dest_path}"
                        )
                    else:
                        details.append(
                            f"    {i}. [{change_type}] {src_path.name if hasattr(src_path, 'name') else src_path}"
                        )

                if len(event.operation_history) > 10:
                    details.append(f"    ... and {len(event.operation_history) - 10} more operations")

            # Show event count (raw events → buffered event)
            if hasattr(event, "event_count"):
                details.append(
                    f"  [dim]Aggregation:[/dim] {event.event_count} raw events → 1 buffered event"
                )

        # GitCommitEvent details
        elif event_type == "GitCommitEvent":
            if hasattr(event, "commit_hash"):
                details.append(f"  [dim]Commit:[/dim] {event.commit_hash[:12]}")
            if hasattr(event, "branch"):
                details.append(f"  [dim]Branch:[/dim] {event.branch}")
            if hasattr(event, "files_changed"):
                details.append(f"  [dim]Files Changed:[/dim] {event.files_changed}")

        # GitPushEvent details
        elif event_type == "GitPushEvent":
            if hasattr(event, "remote"):
                details.append(f"  [dim]Remote:[/dim] {event.remote}")
            if hasattr(event, "branch"):
                details.append(f"  [dim]Branch:[/dim] {event.branch}")
            if hasattr(event, "commits_pushed"):
                details.append(f"  [dim]Commits:[/dim] {event.commits_pushed}")

        # FileChangeEvent (single, unbuffered)
        elif event_type == "FileChangeEvent":
            if hasattr(event, "file_path"):
                details.append(f"  [dim]File:[/dim] {event.file_path}")
            if hasattr(event, "change_type"):
                details.append(f"  [dim]Change:[/dim] {event.change_type}")

        # Show all metadata
        if hasattr(event, "metadata") and event.metadata:
            details.append("  [dim]Metadata:[/dim]")
            for key, value in event.metadata.items():
                details.append(f"    {key}: {value}")

        # Print details with subtle styling
        if details:
            detail_text = "\n".join(details)
            self.console.print(detail_text, style="dim")
