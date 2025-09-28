#!/usr/bin/env python3
"""
Test the real atomic save pattern from the original screenshots.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


def test_screenshot_pattern():
    """Test the exact pattern from the original screenshots."""
    print("🔧 Testing the pattern from the screenshots...\n")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with smart grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Create atomic save events exactly like in the screenshots:
    # test_config_commands.py.tmp.84 created/deleted/moved
    now = datetime.now()
    events = [
        # Created: test_config_commands.py.tmp.84
        FileChangeEvent(
            description="Temp file created",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py.tmp.84"),
            change_type="created",
            timestamp=now,
        ),
        # Deleted: test_config_commands.py.tmp.84
        FileChangeEvent(
            description="Temp file deleted",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py.tmp.84"),
            change_type="deleted",
            timestamp=now + timedelta(milliseconds=50),
        ),
        # Created: test_config_commands.py (the real file appears)
        FileChangeEvent(
            description="Real file created",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py"),
            change_type="created",
            timestamp=now + timedelta(milliseconds=100),
        ),
    ]

    print(f"Input events (like in screenshot): {len(events)}")
    for i, event in enumerate(events):
        print(f"  Event {i+1}: {event.change_type} {event.file_path}")

    print("\nTesting with smart grouping...")
    grouped_smart = buffer._group_events_smart(events)

    print(f"Smart grouping - Output groups: {len(grouped_smart)}")
    for i, group in enumerate(grouped_smart):
        print(f"  Group {i+1}: {group.operation_type} - {group.file_paths} ({group.event_count} events)")

    print("\nTesting with simple grouping...")
    grouped_simple = buffer._group_events_simple(events)

    print(f"Simple grouping - Output groups: {len(grouped_simple)}")
    for i, group in enumerate(grouped_simple):
        print(f"  Group {i+1}: {group.operation_type} - {group.file_paths} ({group.event_count} events)")


def test_classic_delete_create_atomic_save():
    """Test classic delete+create atomic save pattern."""
    print("\n🔧 Testing classic delete+create pattern...\n")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with smart grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Create classic atomic save: delete original, create new
    now = datetime.now()
    events = [
        # Delete original file
        FileChangeEvent(
            description="Original deleted",
            repo_id="test_repo",
            file_path=Path("document.txt"),
            change_type="deleted",
            timestamp=now,
        ),
        # Create new file (same name)
        FileChangeEvent(
            description="New file created",
            repo_id="test_repo",
            file_path=Path("document.txt"),
            change_type="created",
            timestamp=now + timedelta(milliseconds=50),
        ),
    ]

    print(f"Input events (delete+create): {len(events)}")
    for i, event in enumerate(events):
        print(f"  Event {i+1}: {event.change_type} {event.file_path}")

    print("\nTesting with smart grouping...")
    grouped_smart = buffer._group_events_smart(events)

    print(f"Smart grouping - Output groups: {len(grouped_smart)}")
    for i, group in enumerate(grouped_smart):
        print(f"  Group {i+1}: {group.operation_type} - {group.file_paths} ({group.event_count} events)")


if __name__ == "__main__":
    test_screenshot_pattern()
    print("-" * 60)
    test_classic_delete_create_atomic_save()