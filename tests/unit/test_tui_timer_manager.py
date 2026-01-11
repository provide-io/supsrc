#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for the TimerManager functionality."""

from provide.testkit.mocking import Mock, PropertyMock
import pytest

pytestmark = pytest.mark.skip(reason="TUI in active development")
from supsrc.tui.app import TimerManager  # noqa: E402


class TestTimerManager:
    """Test the TimerManager functionality."""

    def test_timer_creation(self) -> None:
        """Test timer creation and tracking."""
        mock_app = Mock()
        mock_timer = Mock()
        mock_app.set_interval.return_value = mock_timer

        manager = TimerManager(mock_app)

        # Create timer
        callback = Mock()
        timer = manager.create_timer("test_timer", 1.0, callback)

        assert timer == mock_timer
        assert "test_timer" in manager._timers
        mock_app.set_interval.assert_called_once_with(1.0, callback, name="test_timer")

    def test_timer_replacement(self) -> None:
        """Test replacing an existing timer."""
        mock_app = Mock()
        old_timer = Mock()
        new_timer = Mock()
        # Mocking the internal handle check
        type(old_timer)._Timer__handle = PropertyMock(return_value=True)
        type(new_timer)._Timer__handle = PropertyMock(return_value=True)
        mock_app.set_interval.side_effect = [old_timer, new_timer]

        manager = TimerManager(mock_app)

        # Create first timer
        callback = Mock()
        manager.create_timer("test_timer", 1.0, callback)

        # Replace with new timer
        manager.create_timer("test_timer", 2.0, callback)

        # Old timer should be stopped
        old_timer.stop.assert_called_once()
        assert manager._timers["test_timer"] == new_timer

    def test_stop_timer(self) -> None:
        """Test stopping a specific timer."""
        mock_app = Mock()
        mock_timer = Mock()
        # Mocking the internal handle check
        type(mock_timer)._Timer__handle = PropertyMock(return_value=True)
        mock_app.set_interval.return_value = mock_timer

        manager = TimerManager(mock_app)

        # Create and stop timer
        manager.create_timer("test_timer", 1.0, Mock())
        result = manager.stop_timer("test_timer")

        assert result is True
        mock_timer.stop.assert_called_once()
        assert "test_timer" not in manager._timers

    def test_stop_nonexistent_timer(self) -> None:
        """Test stopping a timer that doesn't exist."""
        mock_app = Mock()
        manager = TimerManager(mock_app)

        result = manager.stop_timer("nonexistent")

        assert result is False

    def test_stop_all_timers(self) -> None:
        """Test stopping all timers."""
        mock_app = Mock()
        timer1 = Mock()
        timer2 = Mock()
        type(timer1)._Timer__handle = PropertyMock(return_value=True)
        type(timer2)._Timer__handle = PropertyMock(return_value=True)
        mock_app.set_interval.side_effect = [timer1, timer2]

        manager = TimerManager(mock_app)

        # Create multiple timers
        manager.create_timer("timer1", 1.0, Mock())
        manager.create_timer("timer2", 2.0, Mock())

        # Stop all
        manager.stop_all_timers()

        timer1.stop.assert_called_once()
        timer2.stop.assert_called_once()
        assert len(manager._timers) == 0

    def test_timer_manager_error_recovery(self) -> None:
        """Test timer manager error recovery."""
        mock_app = Mock()
        mock_timer = Mock()
        mock_timer.stop.side_effect = Exception("Timer error")
        type(mock_timer)._Timer__handle = PropertyMock(return_value=True)
        mock_app.set_interval.return_value = mock_timer

        manager = TimerManager(mock_app)

        manager.create_timer("test_timer", 1.0, Mock())

        result = manager.stop_timer("test_timer")

        assert result is False  # It now returns False on exception
        assert "test_timer" not in manager._timers


# 🔼⚙️🔚
