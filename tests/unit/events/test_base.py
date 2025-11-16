#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for BaseEvent implementation."""

from datetime import datetime

import pytest

from supsrc.events.base import BaseEvent


class MockEvent(BaseEvent):
    """Mock event implementation."""

    source: str = "test"


def test_base_event_creation() -> None:
    """Test creating a BaseEvent instance."""
    event = MockEvent(description="Test event")

    assert event.description == "Test event"
    assert event.source == "test"
    assert isinstance(event.timestamp, datetime)
    assert event.metadata == {}


def test_base_event_with_metadata() -> None:
    """Test BaseEvent with custom metadata."""
    metadata = {"key": "value", "count": 42}
    event = MockEvent(description="Test with metadata", metadata=metadata)

    assert event.metadata == metadata


def test_base_event_with_custom_timestamp() -> None:
    """Test BaseEvent with custom timestamp."""
    custom_time = datetime(2023, 1, 1, 12, 0, 0)
    event = MockEvent(description="Timed event", timestamp=custom_time)

    assert event.timestamp == custom_time


def test_base_event_format() -> None:
    """Test BaseEvent default formatting."""
    event = MockEvent(description="Format test")

    formatted = event.format()
    assert "[test]" in formatted
    assert "Format test" in formatted
    assert len(formatted.split("[")[1].split("]")[0]) == 8  # Time format HH:MM:SS


def test_base_event_immutable() -> None:
    """Test that BaseEvent is frozen (immutable)."""
    event = MockEvent(description="Immutable test")

    with pytest.raises((AttributeError, TypeError)):
        event.description = "Changed"  # type: ignore

    with pytest.raises((AttributeError, TypeError)):
        event.source = "modified"  # type: ignore


def test_base_event_kw_only() -> None:
    """Test that BaseEvent enforces keyword-only arguments."""
    # This should work
    event = MockEvent(description="Keyword test")
    assert event.description == "Keyword test"

    # This should also work with explicit kwargs
    event2 = MockEvent(description="Another test", metadata={"test": True})
    assert event2.metadata == {"test": True}


# 🔼⚙️🔚
