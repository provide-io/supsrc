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

from provide.foundation.logger import get_logger

from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.defaults import (
    DEFAULT_BUFFER_WINDOW_MS,
    DEFAULT_GROUPING_MODE,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_TEMP_FILE_PATTERNS,
    GROUPING_MODE_OFF,
    GROUPING_MODE_SIMPLE,
    GROUPING_MODE_SMART,
)
from supsrc.events.monitor import FileChangeEvent

# Re-export for backward compatibility
__all__ = ["BufferedFileChangeEvent", "EventBuffer"]

# Import foundation operations - required dependency
from provide.foundation.file.operations import (
    DetectorConfig,
    FileEvent,
    FileEventMetadata,
    OperationDetector,
    OperationType,
)

log = get_logger("events.buffer")


class EventBuffer:
    """Buffers and groups filesystem events to reduce TUI log spam."""

    def __init__(
        self,
        window_ms: int = DEFAULT_BUFFER_WINDOW_MS,
        grouping_mode: str = DEFAULT_GROUPING_MODE,
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
        # Sequence counter for streaming detection
        self._sequence_counter: dict[str, int] = defaultdict(int)
        # Per-repo operation detectors for smart mode
        self._operation_detectors: dict[str, OperationDetector] = {}

        # Store detector config for creating per-repo detectors
        if grouping_mode == GROUPING_MODE_SMART:
            self._detector_config = DetectorConfig(
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns=DEFAULT_TEMP_FILE_PATTERNS,
            )
            log.debug(
                "Smart mode enabled, using per-repo operation detectors",
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns_count=len(DEFAULT_TEMP_FILE_PATTERNS),
            )
        else:
            self._detector_config = None
            log.debug(
                "OperationDetector disabled",
                grouping_mode=grouping_mode,
            )

        log.debug("EventBuffer initialized", window_ms=window_ms, grouping_mode=grouping_mode)

    def add_event(self, event: FileChangeEvent) -> None:
        """Add a file change event to the buffer.

        For smart grouping mode, uses streaming detection to hide temp files
        until atomic operations complete.
        """
        log.trace(
            "Event received",
            repo_id=event.repo_id,
            file_path=str(event.file_path),
            change_type=event.change_type,
            grouping_mode=self.grouping_mode,
        )

        if self.grouping_mode == GROUPING_MODE_OFF:
            # Pass through immediately without buffering
            log.trace("Passing through unbuffered event", file_path=str(event.file_path))
            if self.emit_callback:
                self.emit_callback(event)
            return

        repo_id = event.repo_id

        # SMART MODE: Use foundation's callback-based streaming detection
        if self.grouping_mode == GROUPING_MODE_SMART and self._detector_config:
            # Get or create detector for this repo
            detector = self._get_or_create_detector(repo_id)

            # Convert to FileEvent and pass to detector
            # Foundation handles everything: temp file hiding, auto-flush, callbacks
            file_event = self._convert_to_file_event(event)
            detector.add_event(file_event)

            return

        # SIMPLE MODE or fallback: Use time-window buffering
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
        if self.grouping_mode == GROUPING_MODE_SIMPLE:
            log.debug("Using simple event grouping")
            grouped_events = self._group_events_simple(events)
        elif self.grouping_mode == GROUPING_MODE_SMART:
            log.debug("Using smart event grouping")
            grouped_events = self._group_events_smart(events)
        else:
            # Fallback - treat as individual events
            log.debug("Using individual event mode")
            grouped_events = [self._create_single_event_group(e) for e in events]

        log.debug(
            "Event grouping complete",
            input_events=len(events),
            output_groups=len(grouped_events),
            grouping_mode=self.grouping_mode,
        )

        # Emit grouped events
        if self.emit_callback:
            for i, grouped_event in enumerate(grouped_events):
                log.trace(
                    "Emitting grouped event",
                    index=i,
                    operation_type=grouped_event.operation_type,
                    file_paths=[str(p) for p in grouped_event.file_paths],
                    event_count=grouped_event.event_count,
                )
                self.emit_callback(grouped_event)
        else:
            log.warning("No emit callback available, grouped events not emitted")

    def _group_events_simple(self, events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
        """Group events using simple file-based grouping."""
        log.debug("Starting simple event grouping", event_count=len(events))

        # Group by file path
        file_groups: dict[Path, list[FileChangeEvent]] = defaultdict(list)
        for event in events:
            file_groups[event.file_path].append(event)

        log.trace("File groups created", group_count=len(file_groups))

        grouped_events = []

        # Process each file group
        for file_path, file_events in file_groups.items():
            log.trace(
                "Processing file group", file_path=str(file_path), event_count=len(file_events)
            )

            if len(file_events) == 1:
                grouped_events.append(self._create_single_event_group(file_events[0]))
            else:
                # Multiple events on same file - consolidate
                most_recent = file_events[-1]
                log.debug(
                    "Consolidating multiple events on same file",
                    file_path=str(file_path),
                    event_count=len(file_events),
                    final_change_type=most_recent.change_type,
                )

                # Build operation history for all events on this file
                operation_history = []
                for event in file_events:
                    operation_history.append(
                        {
                            "path": event.file_path,
                            "change_type": event.change_type,
                            "timestamp": event.timestamp,
                            "is_primary": True,
                            "dest_path": event.dest_path,  # Include destination for move events
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

        log.debug(
            "Simple grouping complete", input_events=len(events), output_groups=len(grouped_events)
        )
        return grouped_events


    def _get_or_create_detector(self, repo_id: str) -> OperationDetector:
        """Get or create operation detector for a repository."""
        if repo_id not in self._operation_detectors:
            # Create repo-specific callback that captures repo_id
            def on_operation_complete(operation: Any) -> None:
                self._on_operation_complete(operation, repo_id)

            # Create new detector with callback
            detector = OperationDetector(
                config=self._detector_config, on_operation_complete=on_operation_complete
            )
            self._operation_detectors[repo_id] = detector
            log.debug("Created operation detector for repo", repo_id=repo_id)

        return self._operation_detectors[repo_id]

    def _on_operation_complete(self, operation: Any, repo_id: str) -> None:
        """Callback when foundation detects a completed operation."""
        log.debug(
            "Operation completed callback",
            operation_type=operation.operation_type.value,
            primary_path=str(operation.primary_path),
            event_count=operation.event_count,
            repo_id=repo_id,
        )

        # Convert foundation operation to buffered event
        buffered_event = self._create_operation_event(operation, repo_id)

        # Emit via callback
        if self.emit_callback:
            self.emit_callback(buffered_event)

    def _convert_to_file_event(self, event: FileChangeEvent) -> FileEvent:
        """Convert a single FileChangeEvent to FileEvent for operation detection."""
        repo_id = event.repo_id
        self._sequence_counter[repo_id] += 1

        # Create metadata with timing and sequence info
        metadata = FileEventMetadata(
            timestamp=event.timestamp,
            sequence_number=self._sequence_counter[repo_id],
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

        # Handle dest_path if available
        dest_path = getattr(event, "dest_path", None)

        return FileEvent(
            path=event.file_path,
            event_type=event_type,
            metadata=metadata,
            dest_path=dest_path,
        )


    def _create_operation_event(
        self, operation: Any, repo_id: str
    ) -> BufferedFileChangeEvent:
        """Create a BufferedFileChangeEvent from a detected FileOperation."""
        # Map operation types to our buffer operation types
        operation_type_map = {
            OperationType.ATOMIC_SAVE: "atomic_rewrite",
            OperationType.SAFE_WRITE: "atomic_rewrite",
            OperationType.BATCH_UPDATE: "batch_operation",
            OperationType.RENAME_SEQUENCE: "atomic_rewrite",
            OperationType.BACKUP_CREATE: "single_file",
        }

        buffer_op_type = operation_type_map.get(operation.operation_type, "single_file")

        # Use files_affected if available (for batch operations), otherwise use primary_path
        if operation.files_affected:
            file_paths = operation.files_affected
        else:
            file_paths = [operation.primary_path]

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
                "dest_path": getattr(event, "dest_path", None),  # Include destination for move events
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
                "dest_path": event.dest_path,  # Include destination for move events
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

    def flush_all(self) -> None:
        """Flush all pending buffers immediately.

        For smart grouping, also flushes any incomplete operations from the
        streaming detectors, showing temp files if they never completed.
        """
        # Flush streaming detectors if in smart mode
        if self.grouping_mode == GROUPING_MODE_SMART:
            for repo_id, detector in self._operation_detectors.items():
                pending_operations = detector.flush()

                for operation in pending_operations:
                    log.debug(
                        "Flushing incomplete operation on shutdown",
                        repo_id=repo_id,
                        operation_type=operation.operation_type.value,
                        primary_path=str(operation.primary_path),
                        event_count=operation.event_count,
                    )

                    # Emit the incomplete operation
                    buffered_event = self._create_operation_event(operation, [])
                    if self.emit_callback:
                        self.emit_callback(buffered_event)

        # Flush time-window buffers (for simple mode or fallback)
        repo_ids = list(self._buffers.keys())
        for repo_id in repo_ids:
            if repo_id in self._timers:
                self._timers[repo_id].cancel()
            self._flush_buffer(repo_id)
