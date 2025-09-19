# src/supsrc/events/buffer.py

"""
Event buffering and grouping system for reducing TUI event log spam.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
from provide.foundation.logger import get_logger

from supsrc.events.monitor import FileChangeEvent
from supsrc.events.protocol import Event

log = get_logger("events.buffer")


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

    def format(self) -> str:
        """Format buffered file change event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")

        if self.operation_type == "atomic_rewrite":
            emoji = "🔄"  # COUNTERCLOCKWISE ARROWS BUTTON
            if len(self.file_paths) == 1:
                return f"[{time_str}] {emoji} [{self.repo_id}] {self.file_paths[0].name} (atomic rewrite)"
            else:
                return f"[{time_str}] {emoji} [{self.repo_id}] Atomic rewrite of {len(self.file_paths)} files"

        elif self.operation_type == "batch_operation":
            emoji = "📦"  # PACKAGE
            return f"[{time_str}] {emoji} [{self.repo_id}] Batch operation on {len(self.file_paths)} files"

        else:  # single_file
            emoji_map = {
                "created": "➕",  # HEAVY PLUS SIGN
                "modified": "✏️",  # PENCIL
                "deleted": "➖",  # HEAVY MINUS SIGN
                "moved": "🔄",  # COUNTERCLOCKWISE ARROWS BUTTON
            }
            emoji = emoji_map.get(self.primary_change_type, "📄")  # PAGE FACING UP

            if len(self.file_paths) == 1:
                suffix = f" ({self.event_count} events)" if self.event_count > 1 else ""
                return f"[{time_str}] {emoji} [{self.repo_id}] {self.file_paths[0].name}{suffix}"
            else:
                return f"[{time_str}] {emoji} [{self.repo_id}] {len(self.file_paths)} files {self.primary_change_type}"


class EventBuffer:
    """Buffers and groups filesystem events to reduce TUI log spam."""

    def __init__(
        self,
        window_ms: int = 200,
        grouping_mode: str = "smart",
        emit_callback: Any = None,
    ):
        """Initialize the event buffer.

        Args:
            window_ms: Buffering window in milliseconds
            grouping_mode: "off", "simple", or "smart"
            emit_callback: Function to call when emitting buffered events
        """
        self.window_ms = window_ms
        self.grouping_mode = grouping_mode
        self.emit_callback = emit_callback

        # Buffered events by repo_id
        self._buffers: dict[str, list[FileChangeEvent]] = defaultdict(list)
        # Active timer handles for each repo
        self._timers: dict[str, asyncio.TimerHandle] = {}

        log.debug("EventBuffer initialized", window_ms=window_ms, grouping_mode=grouping_mode)

    def add_event(self, event: FileChangeEvent) -> None:
        """Add a file change event to the buffer."""
        if self.grouping_mode == "off":
            # Pass through immediately without buffering
            if self.emit_callback:
                self.emit_callback(event)
            return

        repo_id = event.repo_id
        self._buffers[repo_id].append(event)

        # Cancel any existing timer for this repo
        if repo_id in self._timers:
            self._timers[repo_id].cancel()

        # Set new timer to flush after window
        loop = asyncio.get_event_loop()
        self._timers[repo_id] = loop.call_later(
            self.window_ms / 1000.0, self._flush_buffer, repo_id
        )

        log.debug(
            "Event added to buffer",
            repo_id=repo_id,
            file_path=str(event.file_path),
            change_type=event.change_type,
            buffer_size=len(self._buffers[repo_id]),
        )

    def _flush_buffer(self, repo_id: str) -> None:
        """Flush buffered events for a repository."""
        events = self._buffers.pop(repo_id, [])
        if repo_id in self._timers:
            del self._timers[repo_id]

        if not events:
            return

        log.debug("Flushing event buffer", repo_id=repo_id, event_count=len(events))

        # Group events based on the configured mode
        if self.grouping_mode == "simple":
            grouped_events = self._group_events_simple(events)
        elif self.grouping_mode == "smart":
            grouped_events = self._group_events_smart(events)
        else:
            # Fallback - treat as individual events
            grouped_events = [self._create_single_event_group(e) for e in events]

        # Emit grouped events
        if self.emit_callback:
            for grouped_event in grouped_events:
                self.emit_callback(grouped_event)

    def _group_events_simple(self, events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
        """Group events using simple file-based grouping."""
        # Group by file path
        file_groups: dict[Path, list[FileChangeEvent]] = defaultdict(list)
        for event in events:
            file_groups[event.file_path].append(event)

        grouped_events = []
        for file_path, file_events in file_groups.items():
            if len(file_events) == 1:
                grouped_events.append(self._create_single_event_group(file_events[0]))
            else:
                # Multiple events on same file - consolidate
                most_recent = file_events[-1]
                grouped_events.append(
                    BufferedFileChangeEvent(
                        repo_id=most_recent.repo_id,
                        file_paths=[file_path],
                        operation_type="single_file",
                        event_count=len(file_events),
                        primary_change_type=most_recent.change_type,
                    )
                )

        return grouped_events

    def _group_events_smart(self, events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
        """Group events using smart pattern recognition."""
        if len(events) == 1:
            return [self._create_single_event_group(events[0])]

        # Try to detect atomic rewrite patterns
        atomic_groups = self._detect_atomic_rewrites(events)
        if atomic_groups:
            return atomic_groups

        # Check for batch operations (multiple files in quick succession)
        if len({e.file_path for e in events}) >= 3:
            return [self._create_batch_operation_group(events)]

        # Fall back to simple grouping
        return self._group_events_simple(events)

    def _detect_atomic_rewrites(
        self, events: list[FileChangeEvent]
    ) -> list[BufferedFileChangeEvent] | None:
        """Detect atomic file rewrite patterns (temp file -> rename)."""
        # Look for patterns like:
        # 1. Create temp file, modify original, delete original, rename temp -> original
        # 2. Create temp file, delete original, rename temp -> original

        # Group events by directory
        dir_events: dict[Path, list[FileChangeEvent]] = defaultdict(list)
        for event in events:
            dir_events[event.file_path.parent].append(event)

        atomic_groups = []
        processed_events = set()

        for _directory, dir_event_list in dir_events.items():
            if len(dir_event_list) < 2:
                continue

            # Sort by timestamp
            dir_event_list.sort(key=lambda e: e.timestamp)

            # Look for temp file patterns (files with common prefixes/suffixes)
            temp_patterns = self._find_temp_file_patterns(dir_event_list)

            for original_file, temp_files in temp_patterns.items():
                if not temp_files:
                    continue

                # Check if we have the pattern: create temp, modify/delete original, rename temp
                pattern_events = []
                for event in dir_event_list:
                    if event.file_path == original_file or event.file_path in temp_files:
                        pattern_events.append(event)
                        processed_events.add(id(event))

                if len(pattern_events) >= 2:
                    atomic_groups.append(
                        BufferedFileChangeEvent(
                            repo_id=pattern_events[0].repo_id,
                            file_paths=[original_file],
                            operation_type="atomic_rewrite",
                            event_count=len(pattern_events),
                            primary_change_type="modified",
                        )
                    )

        # If we found atomic patterns, also include any unprocessed events
        if atomic_groups:
            remaining_events = [e for e in events if id(e) not in processed_events]
            if remaining_events:
                atomic_groups.extend(self._group_events_simple(remaining_events))
            return atomic_groups

        return None

    def _find_temp_file_patterns(self, events: list[FileChangeEvent]) -> dict[Path, list[Path]]:
        """Find temporary file patterns that might indicate atomic operations."""
        file_paths = [e.file_path for e in events]
        temp_patterns: dict[Path, list[Path]] = defaultdict(list)

        for file_path in file_paths:
            # Check for common temp file patterns
            name = file_path.name

            # Pattern 1: .filename.tmp, filename.tmp, filename~
            if name.endswith(".tmp") or name.endswith("~"):
                original_name = name.replace(".tmp", "").replace("~", "")
                if original_name:
                    original_path = file_path.parent / original_name
                    if original_path in file_paths:
                        temp_patterns[original_path].append(file_path)

            # Pattern 2: .filename.xxx (where xxx is random chars)
            elif name.startswith(".") and len(name) > 8:
                # Look for files without the leading dot and random suffix
                # Handle cases like .file.py.abcd1234 -> file.py
                name_parts = name[1:].split(".")
                if len(name_parts) >= 2:
                    # Try different combinations
                    for i in range(1, len(name_parts)):
                        potential_name = ".".join(name_parts[:i])
                        if potential_name:
                            potential_original = file_path.parent / potential_name
                            if potential_original in file_paths:
                                temp_patterns[potential_original].append(file_path)
                                break

        return temp_patterns

    def _create_single_event_group(self, event: FileChangeEvent) -> BufferedFileChangeEvent:
        """Create a buffered event group for a single event."""
        return BufferedFileChangeEvent(
            repo_id=event.repo_id,
            file_paths=[event.file_path],
            operation_type="single_file",
            event_count=1,
            primary_change_type=event.change_type,
        )

    def _create_batch_operation_group(
        self, events: list[FileChangeEvent]
    ) -> BufferedFileChangeEvent:
        """Create a buffered event group for a batch operation."""
        file_paths = list({e.file_path for e in events})
        most_common_type = self._get_most_common_change_type(events)

        return BufferedFileChangeEvent(
            repo_id=events[0].repo_id,
            file_paths=file_paths,
            operation_type="batch_operation",
            event_count=len(events),
            primary_change_type=most_common_type,
        )

    def _get_most_common_change_type(self, events: list[FileChangeEvent]) -> str:
        """Get the most common change type from a list of events."""
        type_counts: dict[str, int] = defaultdict(int)
        for event in events:
            type_counts[event.change_type] += 1

        return max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else "modified"

    def flush_all(self) -> None:
        """Flush all pending buffers immediately."""
        repo_ids = list(self._buffers.keys())
        for repo_id in repo_ids:
            if repo_id in self._timers:
                self._timers[repo_id].cancel()
            self._flush_buffer(repo_id)
