#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Event conversion utilities for transforming between different event formats."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from provide.foundation.file.operations import (
    FileEvent,
    FileEventMetadata,
    OperationType,
)
from provide.foundation.logger import get_logger

from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent

log = get_logger("events.buffer.converters")


def convert_to_file_event(event: FileChangeEvent, sequence_counter: dict[str, int]) -> FileEvent:
    """Convert a FileChangeEvent to FileEvent for operation detection.

    Args:
        event: The file change event to convert
        sequence_counter: Per-repo sequence counter for ordering events

    Returns:
        FileEvent suitable for operation detection
    """
    repo_id = event.repo_id
    sequence_counter[repo_id] += 1

    # Create metadata with timing and sequence info
    metadata = FileEventMetadata(
        timestamp=event.timestamp,
        sequence_number=sequence_counter[repo_id],
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


def create_operation_event(operation: Any, repo_id: str) -> BufferedFileChangeEvent:
    """Create a BufferedFileChangeEvent from a detected FileOperation.

    Args:
        operation: The FileOperation from operation detector
        repo_id: Repository identifier

    Returns:
        BufferedFileChangeEvent for emission to TUI
    """
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
    # Ensure we always have a valid list of Path objects
    if operation.files_affected and len(operation.files_affected) > 0:
        file_paths = list(operation.files_affected)
        log.trace("Using files_affected for operation", count=len(file_paths))
    elif operation.primary_path:
        file_paths = [operation.primary_path]
        log.trace("Using primary_path for operation", path=str(operation.primary_path))
    else:
        # Fallback: extract from events if available
        log.warning("Operation has no primary_path or files_affected, extracting from events")
        file_paths = []
        for event in operation.events:
            if hasattr(event, "path") and event.path not in file_paths:
                file_paths.append(event.path)
        if not file_paths:
            log.error("Could not determine file paths from operation")
            # Use a placeholder to avoid empty list
            file_paths = [Path("unknown")]

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

    # Final validation: ensure file_paths is not empty
    if not file_paths:
        log.error("file_paths is empty after extraction, using placeholder")
        file_paths = [Path("unknown")]

    # Final validation: ensure all paths are Path objects
    file_paths = [Path(p) if not isinstance(p, Path) else p for p in file_paths]

    log.trace(
        "Creating BufferedFileChangeEvent",
        file_paths=[str(p) for p in file_paths],
        buffer_op_type=buffer_op_type,
        primary_change_type=primary_change_type,
    )

    return BufferedFileChangeEvent(
        repo_id=repo_id,
        file_paths=file_paths,
        operation_type=buffer_op_type,
        event_count=operation.event_count,
        primary_change_type=primary_change_type,
        operation_history=operation_history,
    )


def create_single_event_group(event: FileChangeEvent) -> BufferedFileChangeEvent:
    """Create a buffered event group for a single event.

    Args:
        event: The file change event to wrap

    Returns:
        BufferedFileChangeEvent containing single event
    """
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


# 🔼⚙️🔚
