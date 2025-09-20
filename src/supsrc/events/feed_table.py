# src/supsrc/events/feed_table.py

"""
EventFeedTable widget for displaying events in a structured columnar format.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from textual.widgets import DataTable

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.feed_table")


class EventFeedTable(DataTable):
    """Widget for displaying events in a structured table format.

    This widget displays events in columns: Time, Repo, Emoji, Count, Files
    It provides a cleaner, more organized view than the simple text log.
    """

    # Enable focus for keyboard navigation
    can_focus = True

    def __init__(self, **kwargs) -> None:
        """Initialize the EventFeedTable with columns."""
        super().__init__(
            cursor_type="row",
            zebra_stripes=True,
            header_height=1,
            show_row_labels=False,
            **kwargs,
        )

    def on_mount(self) -> None:
        """Initialize the EventFeedTable when mounted."""
        # Set up columns with emoji headers
        self.add_columns(
            "⏰",  # Time - Event timestamp (HH:MM:SS)
            "📦",  # Repo - Repository ID
            "🎯",  # Operation - Operation type emoji
            "#️⃣",  # Impact - Numerical impact (event count/size)
            "📁",  # File - Primary file or directory
            "💬",  # Message - Optional descriptive message
        )

        # Add initial message to show the widget is ready
        self.add_row(
            "--:--:--",
            "system",
            "📋",
            "1",
            "Ready",
            "EventFeed initialized",
            key="ready_message",
        )

        self.add_row(
            "--:--:--",
            "system",
            "🚀",
            "1",
            "startup",
            "Widget mounted",
            key="mounted_message",
        )

    def add_event(self, event: Event) -> None:
        """Add an event to the feed table.

        Args:
            event: Event to display
        """
        try:
            # Extract basic information
            time_str = event.timestamp.strftime("%H:%M:%S")
            repo_id = self._extract_repo_id(event)
            operation_emoji = self._get_event_emoji(event)
            impact_str, file_str, message_str = self._format_event_details_v2(event)

            # Add row to table
            self.add_row(
                time_str,
                repo_id,
                operation_emoji,
                impact_str,
                file_str,
                message_str,
                key=f"event_{event.timestamp.isoformat()}",
            )

            # Scroll to show the latest event
            self.scroll_end()

        except Exception as e:
            log.error(
                "Failed to add event to feed table",
                error=str(e),
                event_source=getattr(event, "source", "unknown"),
                exc_info=True,
            )

    def _extract_repo_id(self, event: Event) -> str:
        """Extract repository ID from the event."""
        # Check if event has repo_id attribute (BufferedFileChangeEvent)
        # Also ensure it's not a Mock object
        if (
            hasattr(event, "repo_id")
            and hasattr(event, "file_paths")
            and "Mock" not in str(type(event))
        ):
            return str(event.repo_id)

        # Try to extract from description for other events
        description = getattr(event, "description", "")
        if "[" in description and "]" in description:
            # Look for [repo_id] pattern in description after source
            # Pattern: [timestamp] [source] [repo_id] description
            parts = description.split("] ")
            if len(parts) >= 3:
                # Look for remaining brackets in the full description after the first two parts
                remaining_text = "] ".join(parts[2:])  # Rejoin in case there are more parts
                if remaining_text.startswith("[") and "]" in remaining_text:
                    end_bracket = remaining_text.find("]")
                    if end_bracket != -1:
                        return remaining_text[1:end_bracket]

        # Fallback to event source
        return getattr(event, "source", "unknown")

    def _get_event_emoji(self, event: Event) -> str:
        """Get appropriate emoji for the event type."""
        # Check for specific event types first (new system events)
        event_type = type(event).__name__
        event_type_emojis = {
            "ExternalCommitEvent": "🤔",  # THINKING FACE
            "ConflictDetectedEvent": "⚠️",  # WARNING SIGN
            "RepositoryFrozenEvent": "🧊",  # ICE CUBE
            "TestFailureEvent": "🔬",  # MICROSCOPE
            "LLMVetoEvent": "🧠",  # BRAIN
        }
        if event_type in event_type_emojis:
            return event_type_emojis[event_type]

        # Check if it's a BufferedFileChangeEvent with specific operations
        if hasattr(event, "operation_type"):
            if event.operation_type == "atomic_rewrite":
                return "🔄"  # COUNTERCLOCKWISE ARROWS BUTTON
            elif event.operation_type == "batch_operation":
                return "📦"  # PACKAGE

        # Check if it has primary_change_type
        if hasattr(event, "primary_change_type"):
            emoji_map = {
                "created": "➕",  # HEAVY PLUS SIGN  # noqa: RUF001
                "modified": "✏️",  # PENCIL
                "deleted": "➖",  # HEAVY MINUS SIGN  # noqa: RUF001
                "moved": "🔄",  # COUNTERCLOCKWISE ARROWS BUTTON
            }
            return emoji_map.get(event.primary_change_type, "📁")

        # Default based on event source
        source_emojis = {
            "git": "🔧",  # WRENCH
            "monitor": "👁️",  # EYE
            "rules": "⚡",  # HIGH VOLTAGE SIGN
            "tui": "💻",  # PERSONAL COMPUTER
            "buffer": "📁",  # FILE FOLDER
            "system": "⚙️",  # GEAR
        }

        source = getattr(event, "source", "unknown")
        return source_emojis.get(source, "📝")  # MEMO as default

    def _format_event_details_v2(self, event: Event) -> tuple[str, str, str]:
        """Format event impact, file, and message details.

        Returns:
            Tuple of (impact_str, file_str, message_str)
        """
        # Handle BufferedFileChangeEvent
        if hasattr(event, "file_paths") and hasattr(event, "event_count"):
            file_paths = getattr(event, "file_paths", [])
            event_count = getattr(event, "event_count", 1)

            impact_str = str(event_count)

            if len(file_paths) == 0:
                file_str = "-"
            elif len(file_paths) == 1:
                file_str = str(file_paths[0].name)
            else:
                # Find common prefix for multiple files
                file_str = self._get_files_summary_short(file_paths)

            # Extract message from description if available
            message_str = self._extract_message(event)

            return impact_str, file_str, message_str

        # Handle other event types
        description = getattr(event, "description", "")

        # Default single event
        impact_str = "1"

        # Extract file and message from description
        file_str, message_str = self._parse_description(description)

        return impact_str, file_str, message_str

    def _format_event_details(self, event: Event) -> tuple[str, str]:
        """Format event count and file details.

        Returns:
            Tuple of (count_str, files_str)
        """
        # Handle BufferedFileChangeEvent
        if hasattr(event, "file_paths") and hasattr(event, "event_count"):
            file_paths = getattr(event, "file_paths", [])
            event_count = getattr(event, "event_count", 1)

            count_str = str(event_count)

            if len(file_paths) == 0:
                files_str = "No files"
            elif len(file_paths) == 1:
                files_str = str(file_paths[0].name)
            else:
                # Find common prefix for multiple files
                files_str = self._get_files_summary(file_paths)

            return count_str, files_str

        # Handle other event types
        description = getattr(event, "description", "")

        # Default single event
        count_str = "1"

        # Clean up description for files column
        # Remove timestamp and source prefixes that are now in their own columns
        files_str = description
        if "] " in files_str:
            # Remove "[HH:MM:SS] [source] " prefix
            parts = files_str.split("] ", 2)
            if len(parts) >= 3:
                files_str = parts[2]
            elif len(parts) == 2:
                files_str = parts[1]

        # Truncate if too long
        if len(files_str) > 50:
            files_str = files_str[:47] + "..."

        return count_str, files_str

    def _get_files_summary_short(self, file_paths: list[Path]) -> str:
        """Get a short summary of multiple file paths for the File column."""
        if not file_paths:
            return "-"

        if len(file_paths) == 1:
            return str(file_paths[0].name)

        # Try to find common directory
        str_paths = [str(p) for p in file_paths]

        # Find common prefix
        if len(str_paths) > 1:
            common_prefix = ""
            min_path = min(str_paths)
            max_path = max(str_paths)

            for i, char in enumerate(min_path):
                if i < len(max_path) and char == max_path[i]:
                    common_prefix += char
                else:
                    break

            # Clean up to end at directory boundary
            if "/" in common_prefix:
                common_prefix = common_prefix.rsplit("/", 1)[0] + "/"

        # Create short summary
        if len(file_paths) <= 2:
            # Show individual file names
            names = [p.name for p in file_paths]
            return ", ".join(names)
        else:
            # Show common directory or count
            if common_prefix and len(common_prefix) > 1:
                common_dir = Path(common_prefix).name or Path(common_prefix).parent.name
                return f"{common_dir}/"
            else:
                return f"{len(file_paths)} files"

    def _extract_message(self, event: Event) -> str:
        """Extract a message from the event."""
        # Handle specific event types with custom messages
        event_type = type(event).__name__
        if event_type == "ExternalCommitEvent":
            commit_hash = getattr(event, "commit_hash", None)
            return f"Committed externally{f' ({commit_hash[:7]})' if commit_hash else ''}"
        elif event_type == "ConflictDetectedEvent":
            conflict_files = getattr(event, "conflict_files", [])
            file_count = len(conflict_files)
            return f"Conflicts in {file_count} file{'s' if file_count != 1 else ''}" if file_count > 0 else "Merge conflicts"
        elif event_type == "RepositoryFrozenEvent":
            reason = getattr(event, "reason", "Unknown reason")
            return f"Frozen: {reason}"
        elif event_type == "TestFailureEvent":
            return "Tests failed"
        elif event_type == "LLMVetoEvent":
            reason = getattr(event, "reason", "Review failed")
            return f"Blocked: {reason[:20]}..." if len(reason) > 20 else f"Blocked: {reason}"

        # For BufferedFileChangeEvent, create a descriptive message
        if hasattr(event, "operation_type"):
            op_type = getattr(event, "operation_type", "")
            if op_type == "atomic_rewrite":
                return "Atomic save"
            elif op_type == "batch_operation":
                return "Batch changes"
            else:
                # Use primary_change_type if available
                if hasattr(event, "primary_change_type"):
                    change_type = getattr(event, "primary_change_type", "")
                    return change_type.capitalize() if change_type else ""
                return ""

        # For other events, extract from description
        description = getattr(event, "description", "")

        # Remove timestamp and source prefixes
        if "] " in description:
            parts = description.split("] ", 2)
            if len(parts) >= 3:
                # Remove repo ID if present
                remaining = parts[2]
                if remaining.startswith("[") and "]" in remaining:
                    bracket_end = remaining.find("]")
                    return remaining[bracket_end + 2 :] if bracket_end != -1 else remaining
                return remaining
            elif len(parts) == 2:
                return parts[1]

        return description[:30] if len(description) > 30 else description

    def _parse_description(self, description: str) -> tuple[str, str]:
        """Parse description to extract file and message.

        Returns:
            Tuple of (file_str, message_str)
        """
        # Default values
        file_str = "-"
        message_str = ""

        # Remove timestamp and source prefixes
        clean_desc = description
        if "] " in clean_desc:
            parts = clean_desc.split("] ", 2)
            if len(parts) >= 3:
                clean_desc = parts[2]
                # Remove repo ID if present
                if clean_desc.startswith("[") and "]" in clean_desc:
                    bracket_end = clean_desc.find("]")
                    if bracket_end != -1:
                        clean_desc = clean_desc[bracket_end + 2 :]
            elif len(parts) == 2:
                clean_desc = parts[1]

        # Try to extract file path from description
        # Look for common file patterns
        import re

        file_pattern = re.compile(
            r"([\w\-./]+\.(py|js|ts|tsx|jsx|json|toml|yaml|yml|md|txt|sh|rs|go|java|c|cpp|h|hpp))",
            re.IGNORECASE,
        )
        match = file_pattern.search(clean_desc)
        if match:
            file_path = match.group(1)
            file_str = Path(file_path).name
            # Use remaining text as message
            message_str = clean_desc.replace(file_path, "").strip()
        else:
            # Use the whole description as message
            message_str = clean_desc

        # Truncate message if too long
        if len(message_str) > 40:
            message_str = message_str[:37] + "..."

        return file_str, message_str

    def _get_files_summary(self, file_paths: list[Path]) -> str:
        """Get a summary of multiple file paths."""
        if not file_paths:
            return "No files"

        if len(file_paths) == 1:
            return str(file_paths[0].name)

        # Try to find common directory
        str_paths = [str(p) for p in file_paths]

        # Find common prefix
        if len(str_paths) > 1:
            common_prefix = ""
            min_path = min(str_paths)
            max_path = max(str_paths)

            for i, char in enumerate(min_path):
                if i < len(max_path) and char == max_path[i]:
                    common_prefix += char
                else:
                    break

            # Clean up to end at directory boundary
            if "/" in common_prefix:
                common_prefix = common_prefix.rsplit("/", 1)[0] + "/"

        # Create summary
        if len(file_paths) <= 3:
            # Show individual file names
            names = [p.name for p in file_paths]
            return ", ".join(names)
        else:
            # Show count and common prefix or directory
            if common_prefix and len(common_prefix) > 1:
                common_dir = Path(common_prefix).name or Path(common_prefix).parent.name
                return f"{len(file_paths)} files in {common_dir}/"
            else:
                return f"{len(file_paths)} files"

    def clear(self) -> None:
        """Clear all events from the table."""
        # Clear all rows but keep columns
        for row_key in list(self.rows.keys()):
            self.remove_row(row_key)

        # Add back the ready message
        self.add_row(
            "--:--:--",
            "system",
            "🧹",
            "1",
            "cleared",
            "Event feed cleared",
            key="cleared_message",
        )

    # Keyboard navigation methods (inherited from DataTable should work)
    def key_up(self) -> None:
        """Handle up arrow key for scrolling."""
        self.cursor_coordinate = (max(0, self.cursor_coordinate.row - 1), 0)

    def key_down(self) -> None:
        """Handle down arrow key for scrolling."""
        max_row = self.row_count - 1
        self.cursor_coordinate = (min(max_row, self.cursor_coordinate.row + 1), 0)

    def key_page_up(self) -> None:
        """Handle page up key for scrolling."""
        new_row = max(0, self.cursor_coordinate.row - 10)
        self.cursor_coordinate = (new_row, 0)

    def key_page_down(self) -> None:
        """Handle page down key for scrolling."""
        max_row = self.row_count - 1
        new_row = min(max_row, self.cursor_coordinate.row + 10)
        self.cursor_coordinate = (new_row, 0)

    def key_home(self) -> None:
        """Handle home key for scrolling."""
        self.cursor_coordinate = (0, 0)

    def key_end(self) -> None:
        """Handle end key for scrolling."""
        max_row = max(0, self.row_count - 1)
        self.cursor_coordinate = (max_row, 0)
