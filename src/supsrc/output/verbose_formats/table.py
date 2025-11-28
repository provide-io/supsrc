#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Table-style verbose formatter with box drawing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supsrc.events.protocol import Event


class TableVerboseFormatter:
    """Formats verbose event details in a structured table with box drawing."""

    def __init__(self, use_ascii: bool = False, max_width: int = 80):
        """Initialize table formatter.

        Args:
            use_ascii: Use ASCII box characters instead of Unicode
            max_width: Maximum width for the table
        """
        self.use_ascii = use_ascii
        self.max_width = max_width

        # Box drawing characters
        if use_ascii:
            self.chars = {
                "top_left": "+",
                "top_right": "+",
                "bottom_left": "+",
                "bottom_right": "+",
                "horizontal": "-",
                "vertical": "|",
                "left_join": "+",
                "right_join": "+",
            }
        else:
            self.chars = {
                "top_left": "┌",
                "top_right": "┐",
                "bottom_left": "└",
                "bottom_right": "┘",
                "horizontal": "─",
                "vertical": "│",
                "left_join": "├",
                "right_join": "┤",
            }

    def format_verbose_details(self, event: Event) -> list[str]:
        """Format verbose details as a structured table.

        Args:
            event: Event to format

        Returns:
            List of formatted lines
        """
        lines = []
        event_type = type(event).__name__

        # Build sections based on event type
        sections = self._build_sections(event, event_type)

        if not sections:
            return lines

        # Calculate content width (accounting for borders and padding)
        content_width = min(self.max_width - 4, 76)  # 2 for borders, 2 for padding

        # Top border
        lines.append(self._build_border("top", "Event Details", content_width))

        # Add sections
        for i, (section_title, fields) in enumerate(sections):
            if i > 0:
                # Section separator
                lines.append(self._build_border("middle", section_title, content_width))

            # Add fields
            for field_name, field_value in fields:
                lines.append(self._build_field_line(field_name, field_value, content_width))

        # Bottom border
        lines.append(self._build_border("bottom", "", content_width))

        return lines

    def _build_sections(self, event: Event, event_type: str) -> list[tuple[str, list[tuple[str, str]]]]:
        """Build sections based on event type.

        Args:
            event: Event to extract data from
            event_type: Type name of the event

        Returns:
            List of (section_title, [(field_name, field_value), ...])
        """
        sections = []

        # Common fields section
        common_fields = [
            ("Type", event_type),
            ("Source", getattr(event, "source", "unknown")),
        ]
        sections.append(("Event Details", common_fields))

        # Type-specific sections
        if event_type == "BufferedFileChangeEvent":
            sections.extend(self._format_buffered_event(event))
        elif event_type == "GitCommitEvent":
            sections.extend(self._format_git_commit(event))
        elif event_type == "GitPushEvent":
            sections.extend(self._format_git_push(event))
        elif event_type == "GitStageEvent":
            sections.extend(self._format_git_stage(event))
        elif event_type == "TimerUpdateEvent":
            sections.extend(self._format_timer_update(event))
        elif event_type == "FileChangeEvent":
            sections.extend(self._format_file_change(event))
        elif "ErrorEvent" in event_type:
            sections.extend(self._format_error_event(event))

        # Metadata section (if present)
        if hasattr(event, "metadata") and event.metadata:
            metadata_fields = [(k, str(v)) for k, v in event.metadata.items()]
            sections.append(("Metadata", metadata_fields))

        return sections

    def _format_buffered_event(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format BufferedFileChangeEvent sections."""
        sections = []

        # Operation details
        operation_fields = [
            ("Operation", getattr(event, "operation_type", "unknown")),
            ("Change Type", getattr(event, "primary_change_type", "unknown")),
        ]

        if hasattr(event, "event_count"):
            operation_fields.append(("Aggregation", f"{event.event_count} raw events → 1 buffered event"))

        sections.append(("Operation", operation_fields))

        # Files section
        if hasattr(event, "file_paths") and event.file_paths:
            file_list = []
            # Show up to 5 files for consistency with old behavior
            display_count = min(5, len(event.file_paths))
            for fp in event.file_paths[:display_count]:
                file_list.append(("", f"• {fp.name if hasattr(fp, 'name') else fp}"))
            if len(event.file_paths) > display_count:
                file_list.append(("", f"... and {len(event.file_paths) - display_count} more"))
            sections.append(("Files", file_list))

        # Operation sequence
        if hasattr(event, "operation_history") and event.operation_history:
            sequence_list = []
            for i, op in enumerate(event.operation_history[:15], 1):  # Show first 15
                change_type = op.get("change_type", "unknown")
                src_path = op.get("src_path") or op.get("path")
                dest_path = op.get("dest_path")

                if dest_path:
                    src_name = src_path.name if hasattr(src_path, "name") else str(src_path)
                    dest_name = dest_path.name if hasattr(dest_path, "name") else str(dest_path)
                    sequence_list.append(("", f"{i}. [{change_type}] {src_name} → {dest_name}"))
                else:
                    src_name = src_path.name if hasattr(src_path, "name") else str(src_path)
                    sequence_list.append(("", f"{i}. [{change_type}] {src_name}"))

            if len(event.operation_history) > 15:
                sequence_list.append(("", f"... and {len(event.operation_history) - 15} more operations"))

            sections.append((f"Operation Sequence ({len(event.operation_history)} events)", sequence_list))

        return sections

    def _format_git_commit(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format GitCommitEvent sections."""
        fields = []

        if hasattr(event, "commit_hash"):
            # Show first 12 chars of hash
            fields.append(("Commit Hash", event.commit_hash[:12]))

        if hasattr(event, "branch"):
            fields.append(("Branch", event.branch))

        if hasattr(event, "files_changed"):
            fields.append(("Files Changed", str(event.files_changed)))

        return [("Git Commit", fields)] if fields else []

    def _format_git_push(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format GitPushEvent sections."""
        fields = []

        if hasattr(event, "remote"):
            fields.append(("Remote", event.remote))

        if hasattr(event, "branch"):
            fields.append(("Branch", event.branch))

        if hasattr(event, "commits_pushed"):
            fields.append(("Commits Pushed", str(event.commits_pushed)))

        return [("Git Push", fields)] if fields else []

    def _format_git_stage(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format GitStageEvent sections."""
        sections = []

        if hasattr(event, "files_staged") and event.files_staged:
            file_list = []
            for file_path in event.files_staged[:10]:
                file_list.append(("", f"• {file_path}"))
            if len(event.files_staged) > 10:
                file_list.append(("", f"... and {len(event.files_staged) - 10} more"))

            sections.append((f"Staged Files ({len(event.files_staged)})", file_list))

        return sections

    def _format_timer_update(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format TimerUpdateEvent sections."""
        fields = []

        if hasattr(event, "seconds_remaining"):
            fields.append(("Time Remaining", f"{event.seconds_remaining}s"))

        if hasattr(event, "total_seconds"):
            fields.append(("Total Time", f"{event.total_seconds}s"))

            # Calculate percentage if both values available
            if hasattr(event, "seconds_remaining"):
                percentage = (event.total_seconds - event.seconds_remaining) / event.total_seconds * 100
                fields.append(("Progress", f"{percentage:.1f}%"))

        if hasattr(event, "rule_name") and event.rule_name:
            fields.append(("Rule", event.rule_name))

        return [("Timer", fields)] if fields else []

    def _format_file_change(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format FileChangeEvent sections."""
        fields = []

        if hasattr(event, "file_path"):
            fields.append(("File Path", str(event.file_path)))

        if hasattr(event, "change_type"):
            fields.append(("Change Type", event.change_type))

        if hasattr(event, "dest_path") and event.dest_path:
            fields.append(("Destination", str(event.dest_path)))

        return [("File Change", fields)] if fields else []

    def _format_error_event(self, event) -> list[tuple[str, list[tuple[str, str]]]]:
        """Format ErrorEvent sections."""
        fields = []

        if hasattr(event, "error_type"):
            fields.append(("Error Type", event.error_type))

        if hasattr(event, "source"):
            fields.append(("Error Source", event.source))

        if hasattr(event, "description"):
            fields.append(("Description", event.description))

        return [("Error Details", fields)] if fields else []

    def _build_border(self, position: str, title: str, width: int) -> str:
        """Build a border line.

        Args:
            position: "top", "middle", or "bottom"
            title: Optional title text for the border
            width: Content width

        Returns:
            Formatted border string
        """
        c = self.chars

        if position == "top":
            left = c["top_left"]
            right = c["top_right"]
        elif position == "middle":
            left = c["left_join"]
            right = c["right_join"]
        else:  # bottom
            left = c["bottom_left"]
            right = c["bottom_right"]

        if title:
            # Border with title: ├─ Title ───────┤
            title_text = f" {title} "
            remaining_width = width - len(title_text)
            if remaining_width > 0:
                return f"{left}{c['horizontal']} {title} {c['horizontal'] * remaining_width}{right}"
            else:
                # Title too long, truncate
                truncated = title[: width - 5] + "..."
                return f"{left}{c['horizontal']} {truncated} {c['horizontal']}{right}"
        else:
            # Simple border: └────────────────────┘
            return f"{left}{c['horizontal'] * width}{right}"

    def _build_field_line(self, field_name: str, field_value: str, width: int) -> str:
        """Build a field line with proper padding.

        Args:
            field_name: Name of the field
            field_value: Value of the field
            width: Content width

        Returns:
            Formatted field line
        """
        c = self.chars

        if field_name:
            # Field with name: │ Name          : Value                  │
            label_width = 14  # Fixed width for field names
            value_width = width - label_width - 3  # Account for ": " separator

            # Truncate if needed
            truncated_name = field_name[:label_width].ljust(label_width)
            truncated_value = field_value[:value_width] if len(field_value) > value_width else field_value

            # Pad to full width
            content = f"{truncated_name}: {truncated_value}"
            content = content.ljust(width)

            return f"{c['vertical']} {content} {c['vertical']}"
        else:
            # Field without name (list items): │   • Item                        │
            truncated_value = field_value[:width] if len(field_value) > width else field_value
            content = truncated_value.ljust(width)
            return f"{c['vertical']} {content} {c['vertical']}"


# 🔼⚙️🔚
