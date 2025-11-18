#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for the Event protocol."""

from datetime import datetime

from supsrc.events.protocol import Event


class MockEvent:
    """Mock implementation of Event protocol for testing."""

    def __init__(self, source: str, description: str) -> None:
        self.timestamp = datetime.now()
        self.source = source
        self.description = description

    def format(self) -> str:
        """Mock format implementation."""
        return f"[{self.source}] {self.description}"


def test_event_protocol_compliance() -> None:
    """Test that MockEvent satisfies the Event protocol."""
    event = MockEvent("test", "Test event")

    # Check protocol compliance
    assert isinstance(event, Event)
    assert hasattr(event, "timestamp")
    assert hasattr(event, "source")
    assert hasattr(event, "description")
    assert hasattr(event, "format")


def test_event_attributes() -> None:
    """Test event attributes."""
    event = MockEvent("git", "Commit performed")

    assert event.source == "git"
    assert event.description == "Commit performed"
    assert isinstance(event.timestamp, datetime)


def test_event_format() -> None:
    """Test event formatting."""
    event = MockEvent("monitor", "File changed")

    formatted = event.format()
    assert "[monitor]" in formatted
    assert "File changed" in formatted


# 🔼⚙️🔚
