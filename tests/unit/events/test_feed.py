#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for EventFeed widget."""

from provide.testkit.mocking import Mock, patch

from supsrc.events.base import BaseEvent
from supsrc.events.feed import EventFeed


class MockEvent(BaseEvent):
    """Test event for feed tests."""

    source: str = "test"


class GitMockEvent(BaseEvent):
    """Git test event for color testing."""

    source: str = "git"


class MonitorMockEvent(BaseEvent):
    """Monitor test event for color testing."""

    source: str = "monitor"


@patch("supsrc.events.feed.RichLog.write")
def test_feed_add_event(mock_write: Mock) -> None:
    """Test adding an event to the feed."""
    feed = EventFeed()
    event = MockEvent(description="Test event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    # Check that the text has white spans (default color for unknown source)
    assert any(span.style == "white" for span in call_args.spans)


@patch("supsrc.events.feed.RichLog.write")
def test_feed_git_event_color(mock_write: Mock) -> None:
    """Test that git events get green color."""
    feed = EventFeed()
    event = GitMockEvent(description="Git event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    # Check that the text has green spans for git events
    assert any(span.style == "green" for span in call_args.spans)


@patch("supsrc.events.feed.RichLog.write")
def test_feed_monitor_event_color(mock_write: Mock) -> None:
    """Test that monitor events get blue color."""
    feed = EventFeed()
    event = MonitorMockEvent(description="Monitor event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    # Check that the text has blue spans for monitor events
    assert any(span.style == "blue" for span in call_args.spans)


@patch("supsrc.events.feed.RichLog.write")
def test_feed_multiple_events(mock_write: Mock) -> None:
    """Test adding multiple events to the feed."""
    feed = EventFeed()
    event1 = GitMockEvent(description="First event")
    event2 = MonitorMockEvent(description="Second event")
    event3 = MockEvent(description="Third event")

    feed.add_event(event1)
    feed.add_event(event2)
    feed.add_event(event3)

    assert mock_write.call_count == 3

    # Check first call (git event)
    first_call = mock_write.call_args_list[0][0][0]
    assert any(span.style == "green" for span in first_call.spans)

    # Check second call (monitor event)
    second_call = mock_write.call_args_list[1][0][0]
    assert any(span.style == "blue" for span in second_call.spans)

    # Check third call (test event - should be white for unknown source)
    third_call = mock_write.call_args_list[2][0][0]
    assert any(span.style == "white" for span in third_call.spans)


def test_feed_color_mapping() -> None:
    """Test the color mapping logic."""
    feed = EventFeed()

    # Test all defined colors
    colors = {
        "git": "green",
        "monitor": "blue",
        "rules": "yellow",
        "tui": "cyan",
    }

    for source_name, expected_color in colors.items():

        class SourceEvent(BaseEvent):
            source: str = source_name

        event = SourceEvent(description=f"{source_name} event")

        with patch("supsrc.events.feed.RichLog.write") as mock_write:
            feed.add_event(event)
            call_args = mock_write.call_args[0][0]
            # Check that the text has the expected color spans
            assert any(span.style == expected_color for span in call_args.spans)


# 🔼⚙️🔚
