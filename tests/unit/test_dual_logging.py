#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for the dual logging functionality (EventCollector + JSONEventLogger)."""

import json
from pathlib import Path
import tempfile

import pytest

from supsrc.events.base import BaseEvent
from supsrc.events.collector import EventCollector
from supsrc.events.json_logger import JSONEventLogger


@pytest.fixture
def temp_json_file():
    """Create a temporary JSON file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


class DummyEvent(BaseEvent):
    """Dummy event for dual logging tests."""

    source: str = "test"


class TestDualLogging:
    """Test the dual logging system (EventCollector + JSONEventLogger)."""

    def test_event_collector_initialization(self):
        """Test EventCollector can be initialized."""
        collector = EventCollector()
        assert collector._handlers == []

    def test_json_logger_initialization(self, temp_json_file):
        """Test JSONEventLogger can be initialized."""
        logger = JSONEventLogger(temp_json_file)
        assert logger.file_path == temp_json_file
        assert logger._file_handle is not None
        logger.close()

    def test_event_collector_subscription(self, temp_json_file):
        """Test EventCollector subscription mechanism."""
        collector = EventCollector()
        json_logger = JSONEventLogger(temp_json_file)

        collector.subscribe(json_logger.log_event)
        assert len(collector._handlers) == 1

        json_logger.close()

    def test_event_emission_and_logging(self, temp_json_file):
        """Test complete dual logging flow."""
        collector = EventCollector()
        json_logger = JSONEventLogger(temp_json_file)
        collector.subscribe(json_logger.log_event)

        # Create and emit test event
        test_event = DummyEvent(description="Test dual logging")
        collector.emit(test_event)

        # Close logger to ensure data is written
        json_logger.close()

        # Verify JSON file was created and contains event data
        assert temp_json_file.exists()

        with open(temp_json_file) as f:
            lines = f.readlines()

        assert len(lines) == 1
        event_data = json.loads(lines[0].strip())

        assert event_data["description"] == "Test dual logging"
        assert event_data["source"] == "test"
        assert "timestamp" in event_data
        assert "metadata" in event_data

    def test_multiple_events_logging(self, temp_json_file):
        """Test logging multiple events."""
        collector = EventCollector()
        json_logger = JSONEventLogger(temp_json_file)
        collector.subscribe(json_logger.log_event)

        # Emit multiple events
        events = [
            DummyEvent(description="First event"),
            DummyEvent(description="Second event"),
            DummyEvent(description="Third event"),
        ]

        for event in events:
            collector.emit(event)

        json_logger.close()

        # Verify all events were logged
        with open(temp_json_file) as f:
            lines = f.readlines()

        assert len(lines) == 3

        for i, line in enumerate(lines):
            event_data = json.loads(line.strip())
            assert event_data["description"] == f"{['First', 'Second', 'Third'][i]} event"

    def test_event_collector_error_handling(self, temp_json_file):
        """Test EventCollector handles handler errors gracefully."""
        collector = EventCollector()

        def failing_handler(event):
            raise Exception("Handler failed")

        def working_handler(event):
            pass

        collector.subscribe(failing_handler)
        collector.subscribe(working_handler)

        # This should not raise an exception
        test_event = DummyEvent(description="Test error handling")
        collector.emit(test_event)

        # Verify both handlers are still subscribed
        assert len(collector._handlers) == 2

    def test_json_logger_handles_path_objects(self, temp_json_file):
        """Test JSONEventLogger handles Path objects in event metadata."""
        collector = EventCollector()
        json_logger = JSONEventLogger(temp_json_file)
        collector.subscribe(json_logger.log_event)

        # Create event with Path object in metadata
        test_event = DummyEvent(description="Test with path", metadata={"file_path": Path("/tmp/test.txt")})
        collector.emit(test_event)

        json_logger.close()

        # Verify Path was converted to string
        with open(temp_json_file) as f:
            event_data = json.loads(f.read().strip())

        assert event_data["metadata"]["file_path"] == "/tmp/test.txt"


# 🔼⚙️🔚
