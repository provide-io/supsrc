#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Event grouping strategies for simple time-window buffering."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from provide.foundation.logger import get_logger

from supsrc.events.buffer.converters import create_single_event_group
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent

log = get_logger("events.buffer.grouping")


def group_events_simple(events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
    """Group events using simple file-based grouping.

    Groups events by file path and consolidates multiple events on the same file
    into a single buffered event.

    Args:
        events: List of file change events to group

    Returns:
        List of grouped buffered events
    """
    log.debug("Starting simple event grouping", event_count=len(events))

    # Group by file path
    file_groups: dict[Path, list[FileChangeEvent]] = defaultdict(list)
    for event in events:
        file_groups[event.file_path].append(event)

    log.trace("File groups created", group_count=len(file_groups))

    grouped_events = []

    # Process each file group
    for file_path, file_events in file_groups.items():
        log.trace("Processing file group", file_path=str(file_path), event_count=len(file_events))

        if len(file_events) == 1:
            grouped_events.append(create_single_event_group(file_events[0]))
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

    log.debug("Simple grouping complete", input_events=len(events), output_groups=len(grouped_events))
    return grouped_events


# 🔼⚙️🔚
