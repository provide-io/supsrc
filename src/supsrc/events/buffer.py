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

        # Initialize operation detector for smart grouping
        if grouping_mode == GROUPING_MODE_SMART and HAS_OPERATION_DETECTION:
            detector_config = DetectorConfig(
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns=DEFAULT_TEMP_FILE_PATTERNS,
            )
            self._operation_detector = OperationDetector(detector_config)
            log.debug(
                "OperationDetector initialized",
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns_count=len(DEFAULT_TEMP_FILE_PATTERNS),
            )
        else:
            self._operation_detector = None
            log.debug(
                "OperationDetector disabled",
                grouping_mode=grouping_mode,
                has_foundation=HAS_OPERATION_DETECTION,
            )

        log.debug("EventBuffer initialized", window_ms=window_ms, grouping_mode=grouping_mode)

    def add_event(self, event: FileChangeEvent) -> None:
        """Add a file change event to the buffer."""
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

    def _group_events_smart(self, events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
        """Group events using smart pattern recognition via provide-foundation."""
        log.debug("Starting smart event grouping", event_count=len(events))

        if len(events) == 1:
            log.trace("Single event, skipping smart detection")
            return [self._create_single_event_group(events[0])]

        if not self._operation_detector or not HAS_OPERATION_DETECTION:
            # Fallback to simple grouping if detector not available
            log.warning(
                "OperationDetector not available, falling back to simple grouping",
                has_detector=bool(self._operation_detector),
                has_foundation=HAS_OPERATION_DETECTION,
                event_count=len(events),
                reason="Operation detector not initialized or foundation not available",
            )
            return self._group_events_simple(events)

        # Convert FileChangeEvents to FileEvents for operation detection
        file_events = self._convert_to_file_events(events)
        log.trace("Converted to foundation FileEvents", file_event_count=len(file_events))

        # Detect operations using foundation's detector
        operations = self._operation_detector.detect(file_events)
        log.debug("Operations detected", operation_count=len(operations))

        for i, operation in enumerate(operations):
            log.trace(
                "Detected operation",
                index=i,
                operation_type=operation.operation_type.value,
                primary_path=str(operation.primary_path),
                confidence=operation.confidence,
                event_count=operation.event_count,
                is_atomic=operation.is_atomic,
            )

        if operations:
            # Convert detected operations back to BufferedFileChangeEvents
            buffered_events = []
            processed_paths = set()

            for operation in operations:
                # Track which file paths were part of operations
                for event in operation.events:
                    processed_paths.add(event.path)
                    log.trace("Marking path as processed", path=str(event.path))

                # Create buffered event for this operation
                buffered_event = self._create_operation_event(operation, events)
                buffered_events.append(buffered_event)
                log.debug(
                    "Created buffered event for operation",
                    operation_type=buffered_event.operation_type,
                    primary_path=str(buffered_event.file_paths[0])
                    if buffered_event.file_paths
                    else "none",
                )

            # Handle any events that weren't part of detected operations
            remaining_events = [e for e in events if e.file_path not in processed_paths]

            if remaining_events:
                log.info(
                    "Some events not matched by operation detector",
                    remaining_count=len(remaining_events),
                    total_events=len(events),
                    processed_paths=len(processed_paths),
                    remaining_files=[str(e.file_path) for e in remaining_events[:3]],  # First 3
                )
            else:
                log.debug(
                    "All events matched by operation detector",
                    total_events=len(events),
                    operations_detected=len(operations),
                )

            if remaining_events:
                remaining_buffered = self._group_events_simple(remaining_events)
                buffered_events.extend(remaining_buffered)
                log.debug(
                    "Added remaining events", remaining_buffered_count=len(remaining_buffered)
                )

            log.debug(
                "Smart grouping complete",
                input_events=len(events),
                operations_detected=len(operations),
                output_groups=len(buffered_events),
            )
            return buffered_events

        # Fall back to simple grouping if no operations detected
        log.info(
            "No operations detected by foundation detector, using simple grouping",
            event_count=len(events),
            event_types=[e.change_type for e in events[:5]],  # First 5
            file_paths=[str(e.file_path) for e in events[:5]],  # First 5
        )
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

        # Use files_affected if available (for batch operations), otherwise use primary_path
        if operation.files_affected:
            file_paths = operation.files_affected
        else:
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

    def flush_all(self) -> None:
        """Flush all pending buffers immediately."""
        repo_ids = list(self._buffers.keys())
        for repo_id in repo_ids:
            if repo_id in self._timers:
                self._timers[repo_id].cancel()
            self._flush_buffer(repo_id)
