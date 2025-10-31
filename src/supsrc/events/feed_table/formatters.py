#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

# Import FilePathFormatter for multi-file display
try:
    from supsrc.events.feed_table.file_utils import FilePathFormatter
except ImportError:
    # Fallback if not available
    class FilePathFormatter:
        @staticmethod
        def get_files_summary_short(file_paths: list[Path]) -> str:
            if len(file_paths) <= 1:
                return file_paths[0].name if file_paths else "-"
            elif len(file_paths) <= 3:
                return f"{len(file_paths)} files"
            else:
                return f"{len(file_paths)} files"


class EventFormatter:
    """Handles formatting of events for display in the feed table."""

    @staticmethod
    def get_event_emoji(event: Event) -> str:
        """Get appropriate emoji for the event type."""
        # Check for specific event types first (new system events and git events)
        event_type = type(event).__name__
        event_type_emojis = {
            "ExternalCommitEvent": "🤔",  # THINKING FACE
            "ConflictDetectedEvent": "⚠️",  # WARNING SIGN
            "RepositoryFrozenEvent": "🧊",  # ICE CUBE
            "LLMVetoEvent": "🧠",  # BRAIN
            "GitCommitEvent": "📝",  # MEMO
            "GitPushEvent": "🚀",  # ROCKET
            "GitStageEvent": "📋",  # CLIPBOARD
            "GitBranchEvent": "🌿",  # HERB
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
            return emoji_map.get(event.primary_change_type, "❓")

        # Default based on event source
        source_emojis = {
            "monitor": "👁️",  # EYE
            "rules": "⚡",  # HIGH VOLTAGE SIGN
            "tui": "💻",  # PERSONAL COMPUTER
        }

        source = getattr(event, "source", "unknown")
        return source_emojis.get(source, "📝")  # MEMO as default

    @staticmethod
    def format_event_details(event: Event) -> tuple[str, str, str]:
        """Format event impact, file, and message details.

        Returns:
            Tuple of (impact_str, file_str, message_str)
        """
        # Handle Git events specially
        event_type = type(event).__name__
        if event_type == "GitCommitEvent":
            files_changed = getattr(event, "files_changed", 1)
            commit_hash = getattr(event, "commit_hash", "")
            impact_str = str(files_changed)
            file_str = f"{files_changed} files" if files_changed != 1 else "1 file"
            # Put colored text first, then commit info
            colored_files = GitEventFormatter.format_git_files_display(files_changed)
            commit_info = f"Commit {commit_hash[:7]}" if commit_hash else "Commit"
            message_str = f"{colored_files} - {commit_info}"
            return impact_str, file_str, message_str

        elif event_type == "GitPushEvent":
            commits_pushed = getattr(event, "commits_pushed", 1)
            remote = getattr(event, "remote", "origin")
            impact_str = str(commits_pushed)
            file_str = "-"
            message_str = f"Push to {remote}"
            return impact_str, file_str, message_str

        elif event_type == "GitStageEvent":
            files_staged = getattr(event, "files_staged", [])
            file_count = len(files_staged)
            impact_str = str(file_count)
            file_str = GitEventFormatter.format_git_files_display(file_count)
            message_str = "Staged changes"
            return impact_str, file_str, message_str

        # Handle BufferedFileChangeEvent
        if hasattr(event, "file_paths") and hasattr(event, "event_count"):
            file_paths = getattr(event, "file_paths", [])
            event_count = getattr(event, "event_count", 1)

            impact_str = str(event_count)

            # Format file list - show actual files, not generic counts
            if len(file_paths) == 0:
                file_str = "-"
            elif len(file_paths) == 1:
                file_str = str(file_paths[0].name)
            elif len(file_paths) <= 3:
                # Show actual file names (comma-separated)
                file_str = ", ".join(str(p.name) for p in file_paths)
            else:
                # Truncate with count for many files
                first_three = ", ".join(str(p.name) for p in file_paths[:3])
                remaining = len(file_paths) - 3
                file_str = f"{first_three} (+{remaining})"

            # Extract message from description if available
            message_str = MessageExtractor.extract_message(event)

            return impact_str, file_str, message_str

        # Handle other event types
        description = getattr(event, "description", "")

        # Default single event
        impact_str = "1"

        # Extract file and message from description
        file_str, message_str = DescriptionParser.parse_description(description)

        return impact_str, file_str, message_str

    @staticmethod
    def extract_repo_id(event: Event) -> str:
        """Extract repository ID from the event."""
        # Check if event has repo_id attribute (BufferedFileChangeEvent, Git events, etc.)
        # Also ensure it's not a Mock object
        if hasattr(event, "repo_id") and "Mock" not in str(type(event)):
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


class GitEventFormatter:
    """Handles formatting of Git-specific events."""

    @staticmethod
    def format_git_files_display(file_count: int) -> str:
        """Format git file display with Rich markup based on file count.

        Args:
            file_count: Number of files affected

        Returns:
            Formatted string with Rich markup for color/style
        """
        if file_count == 0:
            return "-"
        elif file_count == 1:
            return "[dim]1 file[/]"
        elif file_count <= 3:
            return f"[bold cyan]{file_count} files[/]"
        elif file_count <= 10:
            return f"[bold yellow]{file_count} files[/]"
        else:
            # Large change set - use warning style
            return f"[bold red]⚡[/] {file_count} files"


class MessageExtractor:
    """Handles extraction of messages from events."""

    @staticmethod
    def extract_message(event: Event) -> str:
        """Extract a message from the event."""
        # Handle specific event types with custom messages
        event_type = type(event).__name__
        if event_type == "ExternalCommitEvent":
            commit_hash = getattr(event, "commit_hash", None)
            return f"Committed externally{f' ({commit_hash[:7]})' if commit_hash else ''}"
        elif event_type == "ConflictDetectedEvent":
            conflict_files = getattr(event, "conflict_files", [])
            file_count = len(conflict_files)
            return (
                f"Conflicts in {file_count} file{'s' if file_count != 1 else ''}"
                if file_count > 0
                else "Merge conflicts"
            )
        elif event_type == "RepositoryFrozenEvent":
            reason = getattr(event, "reason", "Unknown reason")
            return f"Frozen: {reason}"
        elif event_type == "TestFailureEvent":
            return "Tests failed"
        elif event_type == "LLMVetoEvent":
            reason = getattr(event, "reason", "Review failed")
            return f"Blocked: {reason[:20]}..." if len(reason) > 20 else f"Blocked: {reason}"

        # For BufferedFileChangeEvent, show actual operation (not "Batch changes")
        if hasattr(event, "operation_type"):
            # Get the actual change type (modified, created, deleted, moved)
            if hasattr(event, "primary_change_type"):
                change_type = getattr(event, "primary_change_type", "")

                # For move events, try to show destination if available
                if change_type == "moved" and hasattr(event, "operation_history"):
                    history = getattr(event, "operation_history", [])
                    if history and len(history) > 0:
                        # Try to find move chain
                        last_entry = history[-1]
                        if last_entry.get("dest_path"):
                            dest_name = (
                                last_entry["dest_path"].name
                                if hasattr(last_entry["dest_path"], "name")
                                else str(last_entry["dest_path"])
                            )
                            return f"→ {dest_name}"

                # For other operations, just show the type
                return change_type.capitalize() if change_type else "Changed"
            return "Changed"

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


class DescriptionParser:
    """Handles parsing of event descriptions."""

    @staticmethod
    def parse_description(description: str) -> tuple[str, str]:
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


# 🔼⚙️🔚
