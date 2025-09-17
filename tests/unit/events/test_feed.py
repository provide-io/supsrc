# tests/unit/events/test_feed.py

"""
Tests for EventFeed widget.
"""

from unittest.mock import Mock, patch

from supsrc.events.base import BaseEvent
from supsrc.events.feed import EventFeed


class TestEvent(BaseEvent):
    """Test event for feed tests."""

    source: str = "test"


class GitTestEvent(BaseEvent):
    """Git test event for color testing."""

    source: str = "git"


class MonitorTestEvent(BaseEvent):
    """Monitor test event for color testing."""

    source: str = "monitor"


@patch("supsrc.events.feed.RichLog.write")
def test_feed_add_event(mock_write: Mock) -> None:
    """Test adding an event to the feed."""
    feed = EventFeed()
    event = TestEvent(description="Test event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    assert "[white]" in call_args  # Default color for unknown source
    assert "[/white]" in call_args


@patch("supsrc.events.feed.RichLog.write")
def test_feed_git_event_color(mock_write: Mock) -> None:
    """Test that git events get green color."""
    feed = EventFeed()
    event = GitTestEvent(description="Git event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    assert "[green]" in call_args
    assert "[/green]" in call_args


@patch("supsrc.events.feed.RichLog.write")
def test_feed_monitor_event_color(mock_write: Mock) -> None:
    """Test that monitor events get blue color."""
    feed = EventFeed()
    event = MonitorTestEvent(description="Monitor event")

    feed.add_event(event)

    mock_write.assert_called_once()
    call_args = mock_write.call_args[0][0]
    assert "[blue]" in call_args
    assert "[/blue]" in call_args


@patch("supsrc.events.feed.RichLog.write")
def test_feed_multiple_events(mock_write: Mock) -> None:
    """Test adding multiple events to the feed."""
    feed = EventFeed()
    event1 = GitTestEvent(description="First event")
    event2 = MonitorTestEvent(description="Second event")
    event3 = TestEvent(description="Third event")

    feed.add_event(event1)
    feed.add_event(event2)
    feed.add_event(event3)

    assert mock_write.call_count == 3

    # Check first call (git event)
    first_call = mock_write.call_args_list[0][0][0]
    assert "[green]" in first_call

    # Check second call (monitor event)
    second_call = mock_write.call_args_list[1][0][0]
    assert "[blue]" in second_call

    # Check third call (test event)
    third_call = mock_write.call_args_list[2][0][0]
    assert "[white]" in third_call


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
            assert f"[{expected_color}]" in call_args
            assert f"[/{expected_color}]" in call_args
