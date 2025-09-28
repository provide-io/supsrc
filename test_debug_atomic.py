#!/usr/bin/env python3
"""
Debug test to see why atomic save detection isn't working.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

from provide.foundation.logger import get_logger

# Set logger to debug level for our modules
get_logger("events.buffer").setLevel(logging.DEBUG)
get_logger("provide.foundation.file.operations").setLevel(logging.DEBUG)

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


def test_debug_atomic_save():
    """Test atomic save with debug logging enabled."""
    print("🔧 Testing with debug logging enabled...\n")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with smart grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Create atomic save events (simple pattern)
    now = datetime.now()
    events = [
        # Create temp file
        FileChangeEvent(
            description="Temp file created",
            repo_id="test_repo",
            file_path=Path("document.txt.tmp.12345"),
            change_type="created",
            timestamp=now,
        ),
        # Move temp to final location (this should be detected as atomic save)
        FileChangeEvent(
            description="Temp file moved",
            repo_id="test_repo",
            file_path=Path("document.txt.tmp.12345"),
            change_type="moved",
            timestamp=now + timedelta(milliseconds=50),
        ),
    ]

    print(f"Input events: {len(events)}")
    for i, event in enumerate(events):
        print(f"  Event {i+1}: {event.change_type} {event.file_path}")

    print("\nProcessing events...")
    grouped = buffer._group_events_smart(events)

    print(f"\nOutput groups: {len(grouped)}")
    for i, group in enumerate(grouped):
        print(f"Group {i+1}:")
        print(f"  Operation type: {group.operation_type}")
        print(f"  Primary change type: {group.primary_change_type}")
        print(f"  File paths: {[str(p) for p in group.file_paths]}")
        print(f"  Event count: {group.event_count}")


if __name__ == "__main__":
    test_debug_atomic_save()