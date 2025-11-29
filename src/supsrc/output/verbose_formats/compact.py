#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Compact key=value verbose formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supsrc.events.protocol import Event


class CompactVerboseFormatter:
    """Formats verbose event details in compact key=value style."""

    def __init__(self, indent: str = "  "):
        """Initialize compact formatter.

        Args:
            indent: Indentation string for verbose lines
        """
        self.indent = indent

    def format_verbose_details(self, event: Event) -> list[str]:
        """Format verbose details in compact key=value format.

        Args:
            event: Event to format

        Returns:
            List of formatted lines
        """
        lines = []
        event_type = type(event).__name__

        # Build key=value pairs
        pairs = self._build_key_value_pairs(event, event_type)

        if not pairs:
            return lines

        # Group pairs into logical lines
        # Line 1: Basic metadata
        metadata_line = self._format_pairs(pairs.get("metadata", []))
        if metadata_line:
            lines.append(f"{self.indent}{metadata_line}")

        # Type-specific lines
        if event_type == "BufferedFileChangeEvent":
            lines.extend(self._format_buffered_event_compact(event, pairs))
        elif event_type == "GitCommitEvent":
            lines.extend(self._format_git_commit_compact(pairs))
        elif event_type == "GitPushEvent":
            lines.extend(self._format_git_push_compact(pairs))
        elif event_type == "GitStageEvent":
            lines.extend(self._format_git_stage_compact(event))
        elif event_type == "TimerUpdateEvent":
            lines.extend(self._format_timer_update_compact(pairs))
        elif event_type == "FileChangeEvent":
            lines.extend(self._format_file_change_compact(pairs))

        return lines

    def _build_key_value_pairs(self, event: Event, event_type: str) -> dict[str, list[tuple[str, str]]]:
        """Build categorized key=value pairs.

        Args:
            event: Event to extract data from
            event_type: Type name of the event

        Returns:
            Dictionary mapping category to list of (key, value) pairs
        """
        pairs = {"metadata": [], "operation": [], "files": [], "git": [], "timer": []}

        # Metadata
        pairs["metadata"].append(("type", event_type))
        pairs["metadata"].append(("src", getattr(event, "source", "unknown")))

        # Type-specific pairs
        if event_type == "BufferedFileChangeEvent":
            if hasattr(event, "operation_type"):
                pairs["operation"].append(("op", event.operation_type))
            if hasattr(event, "primary_change_type"):
                pairs["operation"].append(("change", event.primary_change_type))
            if hasattr(event, "event_count"):
                pairs["operation"].append(("count", f"{event.event_count}→1"))

        elif event_type in ("GitCommitEvent", "GitPushEvent", "GitStageEvent"):
            if hasattr(event, "commit_hash"):
                pairs["git"].append(("hash", event.commit_hash[:12]))
            if hasattr(event, "branch"):
                pairs["git"].append(("branch", event.branch))
            if hasattr(event, "files_changed"):
                pairs["git"].append(("files", str(event.files_changed)))
            if hasattr(event, "remote"):
                pairs["git"].append(("remote", event.remote))
            if hasattr(event, "commits_pushed"):
                pairs["git"].append(("commits", str(event.commits_pushed)))

        elif event_type == "TimerUpdateEvent":
            if hasattr(event, "seconds_remaining"):
                pairs["timer"].append(("remaining", f"{event.seconds_remaining}s"))
            if hasattr(event, "total_seconds"):
                pairs["timer"].append(("total", f"{event.total_seconds}s"))
            if hasattr(event, "rule_name") and event.rule_name:
                pairs["timer"].append(("rule", event.rule_name))

        elif event_type == "FileChangeEvent":
            if hasattr(event, "change_type"):
                pairs["operation"].append(("change", event.change_type))

        return pairs

    def _format_pairs(self, pairs: list[tuple[str, str]]) -> str:
        """Format list of key=value pairs into a single line.

        Args:
            pairs: List of (key, value) tuples

        Returns:
            Formatted string like "key1=val1 key2=val2"
        """
        return " ".join(f"{k}={v}" for k, v in pairs)

    def _format_buffered_event_compact(self, event, pairs: dict[str, list[tuple[str, str]]]) -> list[str]:
        """Format BufferedFileChangeEvent in compact style."""
        lines = []

        # Operation details line
        op_line = self._format_pairs(pairs.get("operation", []))
        if op_line:
            lines.append(f"{self.indent}{op_line}")

        # Files line
        if hasattr(event, "file_paths") and event.file_paths:
            file_names = [fp.name if hasattr(fp, "name") else str(fp) for fp in event.file_paths]
            if len(file_names) == 1:
                lines.append(f"{self.indent}files: {file_names[0]}")
            elif len(file_names) <= 5:
                lines.append(f"{self.indent}files: {', '.join(file_names)}")
            else:
                shown = ", ".join(file_names[:3])
                lines.append(f"{self.indent}files: {shown} (+{len(file_names) - 3} more)")

        # Sequence line (abbreviated)
        if hasattr(event, "operation_history") and event.operation_history:
            seq_parts = []
            for op in event.operation_history[:5]:  # Show first 5
                change_type = op.get("change_type", "?")
                src_path = op.get("src_path") or op.get("path")
                dest_path = op.get("dest_path")

                src_name = src_path.name if hasattr(src_path, "name") else str(src_path)

                if dest_path:
                    dest_name = dest_path.name if hasattr(dest_path, "name") else str(dest_path)
                    seq_parts.append(f"[{change_type}]{src_name}→{dest_name}")
                else:
                    seq_parts.append(f"[{change_type}]{src_name}")

            seq_str = " → ".join(seq_parts)
            if len(event.operation_history) > 5:
                seq_str += f" (+{len(event.operation_history) - 5} more)"

            lines.append(f"{self.indent}seq: {seq_str}")

        return lines

    def _format_git_commit_compact(self, pairs: dict[str, list[tuple[str, str]]]) -> list[str]:
        """Format GitCommitEvent in compact style."""
        git_line = self._format_pairs(pairs.get("git", []))
        return [f"{self.indent}{git_line}"] if git_line else []

    def _format_git_push_compact(self, pairs: dict[str, list[tuple[str, str]]]) -> list[str]:
        """Format GitPushEvent in compact style."""
        git_line = self._format_pairs(pairs.get("git", []))
        return [f"{self.indent}{git_line}"] if git_line else []

    def _format_git_stage_compact(self, event) -> list[str]:
        """Format GitStageEvent in compact style."""
        lines = []

        if hasattr(event, "files_staged") and event.files_staged:
            if len(event.files_staged) <= 5:
                files_str = ", ".join(event.files_staged)
            else:
                shown = ", ".join(event.files_staged[:3])
                files_str = f"{shown} (+{len(event.files_staged) - 3} more)"

            lines.append(f"{self.indent}staged: {files_str}")

        return lines

    def _format_timer_update_compact(self, pairs: dict[str, list[tuple[str, str]]]) -> list[str]:
        """Format TimerUpdateEvent in compact style."""
        timer_line = self._format_pairs(pairs.get("timer", []))
        return [f"{self.indent}{timer_line}"] if timer_line else []

    def _format_file_change_compact(self, pairs: dict[str, list[tuple[str, str]]]) -> list[str]:
        """Format FileChangeEvent in compact style."""
        op_line = self._format_pairs(pairs.get("operation", []))
        return [f"{self.indent}{op_line}"] if op_line else []


# 🔼⚙️🔚
