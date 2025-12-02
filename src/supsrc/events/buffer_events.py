#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Buffered event types for the event buffering system."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import attrs

from supsrc.events.protocol import Event


@attrs.define(frozen=True)
class BufferedFileChangeEvent(Event):
    """A buffered/grouped file change event for cleaner TUI display."""

    source: str = attrs.field(default="buffer", init=False)
    repo_id: str = attrs.field(kw_only=True)
    file_paths: list[Path] = attrs.field(kw_only=True)
    operation_type: str = attrs.field(
        kw_only=True
    )  # "single_file", "atomic_rewrite", "batch_operation"
    event_count: int = attrs.field(kw_only=True)
    primary_change_type: str = attrs.field(kw_only=True, default="modified")
    operation_history: list[dict[str, Any]] = attrs.field(kw_only=True, factory=list)

    # Required by Event protocol
    description: str = attrs.field(init=False)
    timestamp: datetime = attrs.field(factory=datetime.now, init=False)

    def __attrs_post_init__(self):
        """Set description after initialization."""
        if self.operation_type == "atomic_rewrite":
            desc = f"Atomic rewrite of {len(self.file_paths)} file(s)"
        elif self.operation_type == "batch_operation":
            desc = f"Batch operation on {len(self.file_paths)} files"
        else:
            desc = f"File {self.primary_change_type}: {self.file_paths[0].name if self.file_paths else 'unknown'}"

        object.__setattr__(self, "description", desc)

    def get_operation_history(self) -> list[dict[str, Any]]:
        """Get the history of all operations that contributed to this event.

        Returns:
            List of operation dictionaries with keys:
            - path: Path involved in the operation
            - change_type: Type of change (created, modified, deleted, moved)
            - timestamp: When the operation occurred
            - is_primary: Whether this is the primary/end-state file
        """
        return self.operation_history.copy()

    def format(self) -> str:
        """Format buffered file change event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")

        # Get emoji for change type
        emoji_map = {
            "created": "+",  # PLUS SIGN
            "modified": "✏️",  # PENCIL
            "deleted": "-",  # MINUS SIGN
            "moved": "🔄",  # COUNTERCLOCKWISE ARROWS BUTTON
        }
        emoji = emoji_map.get(self.primary_change_type, "?")

        # Special handling for move events - reconstruct the move chain
        if self.primary_change_type == "moved" and self.operation_history:
            move_chain = self._reconstruct_move_chain()
            if move_chain:
                if len(move_chain) > 2:
                    # Multiple moves: show chain with count
                    return f"[{time_str}] {emoji} [{self.repo_id}] {' → '.join(move_chain)} ({len(move_chain) - 1} moves)"
                else:
                    # Simple move: just show source → dest
                    return f"[{time_str}] {emoji} [{self.repo_id}] {' → '.join(move_chain)}"

        # Format file list for display
        file_list = self._format_file_list()

        # Show actual files that changed with the operation type
        return f"[{time_str}] {emoji} [{self.repo_id}] {file_list} {self.primary_change_type}"

    def _format_file_list(self, max_files: int = 3) -> str:
        """Format file paths for display.

        Args:
            max_files: Maximum number of files to show before truncating

        Returns:
            Formatted file list string
        """
        if not self.file_paths:
            return "unknown"

        # Get relative names, handling both Path objects and strings
        names = []
        for path in self.file_paths:
            if hasattr(path, "name"):
                names.append(str(path.name))
            else:
                names.append(str(path))

        if len(names) == 1:
            return names[0]

        # For multiple files, show list (truncate if too many)
        if len(names) <= max_files:
            return ", ".join(names)
        else:
            shown = ", ".join(names[:max_files])
            remaining = len(names) - max_files
            return f"{shown} (+{remaining} more)"

    def _reconstruct_move_chain(self) -> list[str]:
        """Reconstruct move chain from operation history.

        Returns:
            List of filenames in order: [source, intermediate1, ..., final_dest]
        """
        if not self.operation_history:
            return []

        # Extract move events with destinations
        moves = []
        for entry in self.operation_history:
            if entry.get("change_type") == "moved" and entry.get("dest_path"):
                src_name = (
                    entry["path"].name if hasattr(entry["path"], "name") else str(entry["path"])
                )
                dest_name = (
                    entry["dest_path"].name
                    if hasattr(entry["dest_path"], "name")
                    else str(entry["dest_path"])
                )
                moves.append((src_name, dest_name))

        if not moves:
            return []

        # Build chain: source → dest1 → dest2 → ...
        # Assumes moves are in chronological order (sorted by timestamp)
        chain = [moves[0][0]]  # Start with first source
        for _src, dest in moves:
            chain.append(dest)

        return chain


# 🔼⚙️🔚
