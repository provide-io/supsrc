#!/usr/bin/env python3
"""
Quick test to verify atomic save bundling is working correctly.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


def test_atomic_save_vscode_pattern():
    """Test VSCode-style atomic save pattern (.tmp.12345 files)."""
    print("Testing VSCode atomic save pattern...")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with smart grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Create atomic save events (VSCode pattern)
    now = datetime.now()
    events = [
        # Create temp file
        FileChangeEvent(
            description="Temp file created",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py.tmp.84"),
            change_type="created",
            timestamp=now,
        ),
        # Move temp to final location
        FileChangeEvent(
            description="Temp file moved",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py.tmp.84"),
            change_type="moved",
            timestamp=now + timedelta(milliseconds=50),
        ),
        # Delete temp file
        FileChangeEvent(
            description="Temp file deleted",
            repo_id="test_repo",
            file_path=Path("test_config_commands.py.tmp.84"),
            change_type="deleted",
            timestamp=now + timedelta(milliseconds=100),
        ),
    ]

    # Process events through smart grouping
    grouped = buffer._group_events_smart(events)

    print(f"Input events: {len(events)}")
    print(f"Output groups: {len(grouped)}")

    for i, group in enumerate(grouped):
        print(f"Group {i+1}:")
        print(f"  Operation type: {group.operation_type}")
        print(f"  Primary change type: {group.primary_change_type}")
        print(f"  File paths: {[str(p) for p in group.file_paths]}")
        print(f"  Event count: {group.event_count}")
        print(f"  Description: {group.description}")
        print()


def test_vim_backup_pattern():
    """Test Vim-style atomic save pattern (file.py~)."""
    print("Testing Vim backup pattern...")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with smart grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Create atomic save events (Vim pattern)
    now = datetime.now()
    events = [
        # Delete original
        FileChangeEvent(
            description="Original deleted",
            repo_id="test_repo",
            file_path=Path("document.py"),
            change_type="deleted",
            timestamp=now,
        ),
        # Create backup
        FileChangeEvent(
            description="Backup created",
            repo_id="test_repo",
            file_path=Path("document.py~"),
            change_type="created",
            timestamp=now + timedelta(milliseconds=10),
        ),
    ]

    # Process events through smart grouping
    grouped = buffer._group_events_smart(events)

    print(f"Input events: {len(events)}")
    print(f"Output groups: {len(grouped)}")

    for i, group in enumerate(grouped):
        print(f"Group {i+1}:")
        print(f"  Operation type: {group.operation_type}")
        print(f"  Primary change type: {group.primary_change_type}")
        print(f"  File paths: {[str(p) for p in group.file_paths]}")
        print(f"  Event count: {group.event_count}")
        print(f"  Description: {group.description}")
        print()


def test_simple_grouping_multiple_events():
    """Test simple grouping with multiple events on same file."""
    print("Testing simple grouping with multiple events...")

    # Create mock callback
    mock_callback = Mock()

    # Create buffer with simple grouping
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="simple",
        emit_callback=mock_callback,
    )

    # Create multiple events on same file
    now = datetime.now()
    events = [
        FileChangeEvent(
            description="File modified 1",
            repo_id="test_repo",
            file_path=Path("test_file.py"),
            change_type="modified",
            timestamp=now,
        ),
        FileChangeEvent(
            description="File modified 2",
            repo_id="test_repo",
            file_path=Path("test_file.py"),
            change_type="modified",
            timestamp=now + timedelta(milliseconds=50),
        ),
        FileChangeEvent(
            description="File modified 3",
            repo_id="test_repo",
            file_path=Path("test_file.py"),
            change_type="modified",
            timestamp=now + timedelta(milliseconds=100),
        ),
    ]

    # Process events through simple grouping
    grouped = buffer._group_events_simple(events)

    print(f"Input events: {len(events)}")
    print(f"Output groups: {len(grouped)}")

    for i, group in enumerate(grouped):
        print(f"Group {i+1}:")
        print(f"  Operation type: {group.operation_type}")
        print(f"  Primary change type: {group.primary_change_type}")
        print(f"  File paths: {[str(p) for p in group.file_paths]}")
        print(f"  Event count: {group.event_count}")
        print(f"  Description: {group.description}")
        print()


if __name__ == "__main__":
    print("🔧 Testing Atomic Save Bundling Fix\n")

    test_atomic_save_vscode_pattern()
    print("-" * 50)

    test_vim_backup_pattern()
    print("-" * 50)

    test_simple_grouping_multiple_events()

    print("✅ Tests completed!")