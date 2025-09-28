#!/usr/bin/env python3
"""
Debug test to directly test provide-foundation's OperationDetector.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from provide.foundation.file.operations import (
    DetectorConfig,
    FileEvent,
    FileEventMetadata,
    OperationDetector,
)


def test_foundation_directly():
    """Test provide-foundation's OperationDetector directly."""
    print("🔧 Testing provide-foundation's OperationDetector directly...\n")

    # Create detector with our custom temp patterns
    from supsrc.events.defaults import DEFAULT_TEMP_FILE_PATTERNS, DEFAULT_MIN_CONFIDENCE

    config = DetectorConfig(
        time_window_ms=500,
        min_confidence=DEFAULT_MIN_CONFIDENCE,
        temp_patterns=DEFAULT_TEMP_FILE_PATTERNS,
    )
    detector = OperationDetector(config)

    # Test the exact pattern from screenshots
    now = datetime.now()
    events = [
        FileEvent(
            path=Path("test_config_commands.py.tmp.84"),
            event_type="created",
            metadata=FileEventMetadata(timestamp=now, sequence_number=1, size_after=1024),
        ),
        FileEvent(
            path=Path("test_config_commands.py.tmp.84"),
            event_type="deleted",
            metadata=FileEventMetadata(
                timestamp=now + timedelta(milliseconds=50), sequence_number=2, size_before=1024
            ),
        ),
        FileEvent(
            path=Path("test_config_commands.py"),
            event_type="created",
            metadata=FileEventMetadata(
                timestamp=now + timedelta(milliseconds=100), sequence_number=3, size_after=1024
            ),
        ),
    ]

    print("Input events:")
    for i, event in enumerate(events):
        print(f"  {i+1}. {event.event_type} {event.path} at {event.timestamp}")

    # Test if temp file is detected
    print(f"\nIs temp file? {detector._is_temp_file(Path('test_config_commands.py.tmp.84'))}")
    print(f"Base name: {detector._extract_base_name(Path('test_config_commands.py.tmp.84'))}")
    print(f"Files related? {detector._files_related(Path('test_config_commands.py.tmp.84'), Path('test_config_commands.py'))}")

    # Test operation detection
    operations = detector.detect(events)

    print(f"\nOperations detected: {len(operations)}")
    for i, operation in enumerate(operations):
        print(f"Operation {i+1}:")
        print(f"  Type: {operation.operation_type}")
        print(f"  Primary path: {operation.primary_path}")
        print(f"  Confidence: {operation.confidence}")
        print(f"  Is atomic: {operation.is_atomic}")
        print(f"  Description: {operation.description}")


def test_simple_same_file():
    """Test simple same file delete+create."""
    print("\n" + "="*60)
    print("🔧 Testing simple same file delete+create...\n")

    config = DetectorConfig(time_window_ms=500, min_confidence=0.7)
    detector = OperationDetector(config)

    now = datetime.now()
    events = [
        FileEvent(
            path=Path("document.txt"),
            event_type="deleted",
            metadata=FileEventMetadata(timestamp=now, sequence_number=1, size_before=1000),
        ),
        FileEvent(
            path=Path("document.txt"),
            event_type="created",
            metadata=FileEventMetadata(
                timestamp=now + timedelta(milliseconds=50), sequence_number=2, size_after=1024
            ),
        ),
    ]

    print("Input events:")
    for i, event in enumerate(events):
        print(f"  {i+1}. {event.event_type} {event.path} at {event.timestamp}")

    operations = detector.detect(events)

    print(f"\nOperations detected: {len(operations)}")
    for i, operation in enumerate(operations):
        print(f"Operation {i+1}:")
        print(f"  Type: {operation.operation_type}")
        print(f"  Primary path: {operation.primary_path}")
        print(f"  Confidence: {operation.confidence}")
        print(f"  Is atomic: {operation.is_atomic}")
        print(f"  Description: {operation.description}")


if __name__ == "__main__":
    test_foundation_directly()
    test_simple_same_file()