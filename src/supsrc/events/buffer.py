# src/supsrc/events/buffer.py

"""
Event buffering and grouping system for reducing TUI event log spam.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import attrs
from provide.foundation.logger import get_logger

from supsrc.events.monitor import FileChangeEvent
from supsrc.events.protocol import Event

# Import foundation operations with fallback
try:
    from provide.foundation.file.operations import (
        DetectorConfig,
        FileEvent,
        FileEventMetadata,
        OperationDetector,
        OperationType,
    )

    HAS_OPERATION_DETECTION = True
except ImportError:
    # Fallback for when foundation operations is not available
    HAS_OPERATION_DETECTION = False
    DetectorConfig = None
    FileEvent = None
    FileEventMetadata = None
    OperationDetector = None
    OperationType = None

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

        if self.operation_type == "atomic_rewrite":
            emoji = "✏️"  # PENCIL
            if len(self.file_paths) == 1:
                suffix = f" ({self.event_count} ops)" if self.event_count > 1 else ""
                return f"[{time_str}] {emoji} [{self.repo_id}] {self.file_paths[0].name} Updated{suffix}"
            else:
                return f"[{time_str}] {emoji} [{self.repo_id}] Updated {len(self.file_paths)} files ({self.event_count} ops)"

        elif self.operation_type == "batch_operation":
            emoji = "📦"  # PACKAGE
            return f"[{time_str}] {emoji} [{self.repo_id}] Batch operation on {len(self.file_paths)} files"

        else:  # single_file
            emoji_map = {
                "created": "+",  # PLUS SIGN
                "modified": "✏️",  # PENCIL
                "deleted": "-",  # MINUS SIGN
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
        window_ms: int = 500,
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

        # Initialize operation detector for smart grouping
        if grouping_mode == "smart" and HAS_OPERATION_DETECTION:
            detector_config = DetectorConfig(time_window_ms=window_ms, min_confidence=0.7)
            self._operation_detector = OperationDetector(detector_config)
        else:
            self._operation_detector = None

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
        """Group events using simple file-based grouping with atomic save detection."""
        # Group by file path
        file_groups: dict[Path, list[FileChangeEvent]] = defaultdict(list)
        for event in events:
            file_groups[event.file_path].append(event)

        # Look for atomic save patterns within the time window
        atomic_saves = self._detect_simple_atomic_saves(events)
        processed_files = set()

        grouped_events = []

        # Process atomic saves first
        for atomic_save in atomic_saves:
            grouped_events.append(atomic_save)
            # Mark files as processed
            for file_path in atomic_save.file_paths:
                processed_files.add(file_path)

        # Process remaining files
        for file_path, file_events in file_groups.items():
            if file_path in processed_files:
                continue

            if len(file_events) == 1:
                grouped_events.append(self._create_single_event_group(file_events[0]))
            else:
                # Multiple events on same file - consolidate
                most_recent = file_events[-1]

                # Build operation history for all events on this file
                operation_history = []
                for event in file_events:
                    operation_history.append(
                        {
                            "path": event.file_path,
                            "change_type": event.change_type,
                            "timestamp": event.timestamp,
                            "is_primary": True,
                        }
                    )

                grouped_events.append(
                    BufferedFileChangeEvent(
                        repo_id=most_recent.repo_id,
                        file_paths=[file_path],
                        operation_type="single_file",
                        event_count=len(file_events),
                        primary_change_type=most_recent.change_type,
                        operation_history=operation_history,
                    )
                )

        return grouped_events

    def _group_events_smart(self, events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
        """Group events using smart pattern recognition via provide-foundation."""
        if len(events) == 1:
            return [self._create_single_event_group(events[0])]

        if not self._operation_detector or not HAS_OPERATION_DETECTION:
            # Fallback to simple grouping if detector not available
            return self._group_events_simple(events)

        # Convert FileChangeEvents to FileEvents for operation detection
        file_events = self._convert_to_file_events(events)

        # Detect operations using foundation's detector
        operations = self._operation_detector.detect(file_events)

        if operations:
            # Convert detected operations back to BufferedFileChangeEvents
            buffered_events = []
            processed_paths = set()

            for operation in operations:
                # Track which file paths were part of operations
                for event in operation.events:
                    processed_paths.add(event.path)

                # Create buffered event for this operation
                buffered_events.append(self._create_operation_event(operation, events))

            # Handle any events that weren't part of detected operations
            remaining_events = [e for e in events if e.file_path not in processed_paths]

            if remaining_events:
                buffered_events.extend(self._group_events_simple(remaining_events))

            return buffered_events

        # Fall back to simple grouping if no operations detected
        return self._group_events_simple(events)

    def _convert_to_file_events(self, events: list[FileChangeEvent]) -> list:
        """Convert FileChangeEvents to FileEvents for operation detection."""
        if not HAS_OPERATION_DETECTION or not FileEvent or not FileEventMetadata:
            return []

        file_events = []

        for i, event in enumerate(events):
            # Create metadata with timing and sequence info
            metadata = FileEventMetadata(
                timestamp=event.timestamp,
                sequence_number=i + 1,
                # Note: FileChangeEvent doesn't have size info, so we leave it None
                size_before=None,
                size_after=None,
            )

            # Map change types to event types expected by operation detector
            event_type_map = {
                "created": "created",
                "modified": "modified",
                "deleted": "deleted",
                "moved": "moved",
            }
            event_type = event_type_map.get(event.change_type, "modified")

            file_event = FileEvent(
                path=event.file_path,
                event_type=event_type,
                metadata=metadata,
                # FileChangeEvent doesn't have dest_path, would need to be added if needed
                dest_path=None,
            )
            file_events.append(file_event)

        return file_events

    def _create_operation_event(
        self, operation: Any, original_events: list[FileChangeEvent]
    ) -> BufferedFileChangeEvent:
        """Create a BufferedFileChangeEvent from a detected FileOperation."""
        if not HAS_OPERATION_DETECTION or not OperationType:
            # Fallback for when operation detection is not available
            return self._create_single_event_group(original_events[0])

        # Map operation types to our buffer operation types
        operation_type_map = {
            OperationType.ATOMIC_SAVE: "atomic_rewrite",
            OperationType.SAFE_WRITE: "atomic_rewrite",
            OperationType.BATCH_UPDATE: "batch_operation",
            OperationType.RENAME_SEQUENCE: "atomic_rewrite",
            OperationType.BACKUP_CREATE: "single_file",
        }

        buffer_op_type = operation_type_map.get(operation.operation_type, "single_file")

        # Use primary_path (end-state file) as the main file path
        file_paths = [operation.primary_path]

        # Find the repo_id from original events
        repo_id = original_events[0].repo_id if original_events else "unknown"

        # Determine primary change type based on operation
        if operation.operation_type in (OperationType.ATOMIC_SAVE, OperationType.SAFE_WRITE):
            primary_change_type = "modified"
        elif operation.operation_type == OperationType.RENAME_SEQUENCE:
            primary_change_type = "moved"
        elif operation.operation_type == OperationType.BACKUP_CREATE:
            primary_change_type = "created"
        else:
            primary_change_type = "modified"

        # Build operation history from all events involved
        operation_history = []
        for event in operation.events:
            history_entry = {
                "path": event.path,
                "change_type": event.event_type,
                "timestamp": event.timestamp,
                "is_primary": event.path == operation.primary_path
                or (hasattr(event, "dest_path") and event.dest_path == operation.primary_path),
            }
            operation_history.append(history_entry)

        # Sort by timestamp to maintain chronological order
        operation_history.sort(key=lambda x: cast(datetime, x["timestamp"]))

        return BufferedFileChangeEvent(
            repo_id=repo_id,
            file_paths=file_paths,
            operation_type=buffer_op_type,
            event_count=operation.event_count,
            primary_change_type=primary_change_type,
            operation_history=operation_history,
        )

    def _create_single_event_group(self, event: FileChangeEvent) -> BufferedFileChangeEvent:
        """Create a buffered event group for a single event."""
        operation_history = [
            {
                "path": event.file_path,
                "change_type": event.change_type,
                "timestamp": event.timestamp,
                "is_primary": True,
            }
        ]

        return BufferedFileChangeEvent(
            repo_id=event.repo_id,
            file_paths=[event.file_path],
            operation_type="single_file",
            event_count=1,
            primary_change_type=event.change_type,
            operation_history=operation_history,
        )

    def _create_batch_operation_group(
        self, events: list[FileChangeEvent]
    ) -> BufferedFileChangeEvent:
        """Create a buffered event group for a batch operation."""
        file_paths = list({e.file_path for e in events})
        most_common_type = self._get_most_common_change_type(events)

        # Build operation history for all events
        operation_history = []
        for event in events:
            operation_history.append(
                {
                    "path": event.file_path,
                    "change_type": event.change_type,
                    "timestamp": event.timestamp,
                    "is_primary": True,  # All files are primary in batch operations
                }
            )

        # Sort by timestamp to maintain chronological order
        operation_history.sort(key=lambda x: cast(datetime, x["timestamp"]))

        return BufferedFileChangeEvent(
            repo_id=events[0].repo_id,
            file_paths=file_paths,
            operation_type="batch_operation",
            event_count=len(events),
            primary_change_type=most_common_type,
            operation_history=operation_history,
        )

    def _detect_simple_atomic_saves(
        self, events: list[FileChangeEvent]
    ) -> list[BufferedFileChangeEvent]:
        """Detect atomic save patterns using simple heuristics."""
        atomic_saves = []

        # Look for delete + create patterns with related filenames
        deletes = [e for e in events if e.change_type == "deleted"]
        creates = [e for e in events if e.change_type == "created"]

        for delete_event in deletes:
            for create_event in creates:
                # Check if files are related (same base name)
                if self._files_are_related_simple(delete_event.file_path, create_event.file_path):
                    # This looks like an atomic save operation
                    operation_history = [
                        {
                            "path": delete_event.file_path,
                            "change_type": "deleted",
                            "timestamp": delete_event.timestamp,
                            "is_primary": False,
                        },
                        {
                            "path": create_event.file_path,
                            "change_type": "created",
                            "timestamp": create_event.timestamp,
                            "is_primary": True,
                        },
                    ]

                    # Sort by timestamp
                    operation_history.sort(key=lambda x: cast(datetime, x["timestamp"]))

                    atomic_save = BufferedFileChangeEvent(
                        repo_id=create_event.repo_id,
                        file_paths=[create_event.file_path],  # End-state file
                        operation_type="atomic_rewrite",
                        event_count=2,
                        primary_change_type="modified",  # Atomic save is essentially a modification
                        operation_history=operation_history,
                    )
                    atomic_saves.append(atomic_save)

        return atomic_saves

    def _files_are_related_simple(self, path1: Path, path2: Path) -> bool:
        """Check if two paths are related for atomic save detection."""
        # Same file name -> likely atomic save
        if path1.name == path2.name:
            return True

        # Check for temp file patterns
        name1, name2 = path1.name, path2.name

        # Common temp file patterns:
        # file.txt -> .file.txt.tmp
        # file.txt -> file.txt.tmp
        # file.txt -> file.tmp123

        # Pattern 1: One is a temp version of the other
        if name1.startswith(".") and name1.endswith(".tmp") and name1[1:-4] == name2:
            return True
        if name2.startswith(".") and name2.endswith(".tmp") and name2[1:-4] == name1:
            return True

        # Pattern 2: One has .tmp suffix
        if name1.endswith(".tmp") and name1[:-4] == name2:
            return True
        if name2.endswith(".tmp") and name2[:-4] == name1:
            return True

        # Pattern 3: One has random suffix (like .tmp123)
        if name1.rsplit(".", 1)[0] == name2 and len(name1.rsplit(".", 1)) == 2:
            suffix = name1.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                return True
        if name2.rsplit(".", 1)[0] == name1 and len(name2.rsplit(".", 1)) == 2:
            suffix = name2.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                return True

        # Pattern 4: Common editor temp patterns
        # vim: .file.swp
        # emacs: #file#, .#file
        stem1, stem2 = path1.stem, path2.stem
        if name1.startswith(".") and name1.endswith(".swp") and stem1[1:-4] == stem2:
            return True
        return bool(name2.startswith(".") and name2.endswith(".swp") and stem2[1:-4] == stem1)

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
