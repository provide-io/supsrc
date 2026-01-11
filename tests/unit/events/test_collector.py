#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for EventCollector."""

from provide.testkit.mocking import Mock

from supsrc.events.base import BaseEvent
from supsrc.events.collector import EventCollector


class MockEvent(BaseEvent):
    """Test event for collector tests."""

    source: str = "test"


def test_collector_creation() -> None:
    """Test creating an EventCollector."""
    collector = EventCollector()
    assert collector._handlers == []


def test_collector_subscribe() -> None:
    """Test subscribing a handler."""
    collector = EventCollector()
    handler = Mock()

    collector.subscribe(handler)
    assert len(collector._handlers) == 1
    assert handler in collector._handlers


def test_collector_unsubscribe() -> None:
    """Test unsubscribing a handler."""
    collector = EventCollector()
    handler = Mock()

    collector.subscribe(handler)
    assert len(collector._handlers) == 1

    collector.unsubscribe(handler)
    assert len(collector._handlers) == 0


def test_collector_unsubscribe_nonexistent() -> None:
    """Test unsubscribing a handler that wasn't subscribed."""
    collector = EventCollector()
    handler = Mock()

    # Should not raise an exception
    collector.unsubscribe(handler)


def test_collector_emit_single_handler() -> None:
    """Test emitting an event to a single handler."""
    collector = EventCollector()
    handler = Mock()
    event = MockEvent(description="Test event")

    collector.subscribe(handler)
    collector.emit(event)

    handler.assert_called_once_with(event)


def test_collector_emit_multiple_handlers() -> None:
    """Test emitting an event to multiple handlers."""
    collector = EventCollector()
    handler1 = Mock()
    handler2 = Mock()
    handler3 = Mock()
    event = MockEvent(description="Multi-handler test")

    collector.subscribe(handler1)
    collector.subscribe(handler2)
    collector.subscribe(handler3)

    collector.emit(event)

    handler1.assert_called_once_with(event)
    handler2.assert_called_once_with(event)
    handler3.assert_called_once_with(event)


def test_collector_emit_no_handlers() -> None:
    """Test emitting an event with no subscribed handlers."""
    collector = EventCollector()
    event = MockEvent(description="No handlers test")

    # Should not raise an exception
    collector.emit(event)


def test_collector_handler_exception() -> None:
    """Test that handler exceptions don't affect other handlers."""
    collector = EventCollector()
    good_handler = Mock()
    bad_handler = Mock(side_effect=ValueError("Handler error"))
    another_handler = Mock()
    event = MockEvent(description="Exception test")

    collector.subscribe(good_handler)
    collector.subscribe(bad_handler)
    collector.subscribe(another_handler)

    # Should not raise an exception
    collector.emit(event)

    # All handlers should have been called
    good_handler.assert_called_once_with(event)
    bad_handler.assert_called_once_with(event)
    another_handler.assert_called_once_with(event)


def test_collector_multiple_subscriptions() -> None:
    """Test subscribing the same handler multiple times."""
    collector = EventCollector()
    handler = Mock()
    event = MockEvent(description="Multi-subscription test")

    collector.subscribe(handler)
    collector.subscribe(handler)  # Subscribe again

    assert len(collector._handlers) == 2
    assert collector._handlers.count(handler) == 2

    collector.emit(event)
    assert handler.call_count == 2


# 🔼⚙️🔚
