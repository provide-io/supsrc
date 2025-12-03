#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for EventProcessor timer debounce functionality."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest
from provide.testkit.mocking import AsyncMock, MagicMock, patch

from supsrc.config import InactivityRuleConfig, SupsrcConfig
from supsrc.events.processor import EventProcessor
from supsrc.monitor import MonitoredEvent
from supsrc.runtime.action_handler import ActionHandler
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.state import RepositoryState


@pytest.fixture
def mock_action_handler():
    """Mock action handler."""
    return AsyncMock(spec=ActionHandler)


@pytest.fixture
def mock_tui():
    """Mock TUI interface."""
    mock = MagicMock(spec=TUIInterface)
    mock.post_state_update = MagicMock()
    mock.post_log_update = MagicMock()
    mock.is_active = False
    return mock


@pytest.fixture
def timer_debounce_config(temp_git_repo: Path) -> SupsrcConfig:
    """Create configuration with inactivity rule for timer testing."""
    from datetime import timedelta

    from supsrc.config import GlobalConfig, RepositoryConfig

    repo_id = "test_repo"
    return SupsrcConfig(
        global_config=GlobalConfig(),
        repositories={
            repo_id: RepositoryConfig(
                path=temp_git_repo,
                enabled=True,
                rule=InactivityRuleConfig(period=timedelta(seconds=30)),  # 30 second timer
                repository={"type": "supsrc.engines.git", "branch": "main"},
            )
        },
    )


@pytest.fixture
def event_processor_with_timer(
    timer_debounce_config: SupsrcConfig,
    mock_action_handler: AsyncMock,
    mock_tui: MagicMock,
) -> EventProcessor:
    """Create EventProcessor configured for timer debounce testing."""
    event_queue = asyncio.Queue()
    shutdown_event = asyncio.Event()
    repo_states = {"test_repo": RepositoryState(repo_id="test_repo")}
    repo_engines = {}

    return EventProcessor(
        config=timer_debounce_config,
        event_queue=event_queue,
        shutdown_event=shutdown_event,
        action_handler=mock_action_handler,
        repo_states=repo_states,
        repo_engines=repo_engines,
        tui=mock_tui,
        config_reload_callback=AsyncMock(),
    )


class TestEventProcessorTimerDebounce:
    """Test cases for EventProcessor timer debouncing."""

    def test_timer_debounce_initialization(self, event_processor_with_timer: EventProcessor):
        """Test that timer debounce is properly initialized."""
        processor = event_processor_with_timer

        assert hasattr(processor, "_pending_timer_checks")
        assert hasattr(processor, "_timer_check_delay")
        assert processor._pending_timer_checks == {}
        assert processor._timer_check_delay == 0.5  # 500ms

    @pytest.mark.asyncio
    async def test_single_event_triggers_debounced_timer_check(
        self,
        event_processor_with_timer: EventProcessor,
        temp_git_repo: Path,
    ):
        """Test that a single event triggers a debounced timer check."""
        processor = event_processor_with_timer
        repo_id = "test_repo"

        # Mock the actual timer check method
        with patch.object(
            processor, "_check_repo_status_and_handle_timer", new_callable=AsyncMock
        ) as mock_timer_check:
            # Create a file change event
            event = MonitoredEvent(repo_id, "modified", temp_git_repo / "test.py", False)

            # Add event to queue and process it
            await processor.event_queue.put(event)

            # Run processor briefly
            run_task = asyncio.create_task(processor.run())
            await asyncio.sleep(0.1)  # Let it process the event

            # Should have a pending timer check
            assert repo_id in processor._pending_timer_checks

            # Wait for debounce delay
            await asyncio.sleep(0.6)  # Wait longer than debounce delay

            # Timer check should have been called
            mock_timer_check.assert_called_once_with(repo_id)

            # Clean up
            processor.shutdown_event.set()
            await asyncio.gather(run_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_debounce_scheduler_directly(
        self,
        event_processor_with_timer: EventProcessor,
    ):
        """Test that the debounce scheduler works correctly when called multiple times."""
        processor = event_processor_with_timer
        repo_id = "test_repo"

        # Track timer check calls
        timer_check_calls = []

        async def mock_timer_check(repo_id_arg):
            timer_check_calls.append(repo_id_arg)

        # Mock the actual timer check method
        with patch.object(processor, "_check_repo_status_and_handle_timer", side_effect=mock_timer_check):
            # Call the scheduler multiple times rapidly
            processor._schedule_debounced_timer_check(repo_id)
            assert repo_id in processor._pending_timer_checks
            first_task = processor._pending_timer_checks[repo_id]

            processor._schedule_debounced_timer_check(repo_id)
            # Give a moment for the cancellation to take effect
            await asyncio.sleep(0.01)
            assert first_task.cancelled()  # First task should be cancelled

            processor._schedule_debounced_timer_check(repo_id)
            processor._schedule_debounced_timer_check(repo_id)
            processor._schedule_debounced_timer_check(repo_id)

            # Should have only one pending check
            assert len(processor._pending_timer_checks) == 1

            # Wait for debounce delay
            await asyncio.sleep(0.6)

            # Timer check should have been called only once
            assert len(timer_check_calls) == 1
            assert timer_check_calls[0] == repo_id

    @pytest.mark.asyncio
    async def test_cancellation_behavior_directly(
        self,
        event_processor_with_timer: EventProcessor,
    ):
        """Test that scheduling new timer checks cancels pending ones."""
        processor = event_processor_with_timer
        repo_id = "test_repo"

        # Mock the actual timer check method to take a long time
        async def slow_timer_check(repo_id_arg):
            await asyncio.sleep(2)  # Long enough to be cancelled

        # Mock the actual timer check method
        with patch.object(processor, "_check_repo_status_and_handle_timer", side_effect=slow_timer_check):
            # Schedule first timer check
            processor._schedule_debounced_timer_check(repo_id)
            assert repo_id in processor._pending_timer_checks
            first_task = processor._pending_timer_checks[repo_id]

            # Schedule second timer check (should cancel first)
            processor._schedule_debounced_timer_check(repo_id)
            await asyncio.sleep(0.01)  # Let cancellation take effect

            # First task should be cancelled
            assert first_task.cancelled()

            # Should have new pending timer check
            assert repo_id in processor._pending_timer_checks
            second_task = processor._pending_timer_checks[repo_id]
            assert second_task != first_task

            # Clean up remaining task
            second_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await second_task

    @pytest.mark.asyncio
    async def test_multiple_repos_independent_debouncing(
        self,
        temp_git_repo: Path,
        mock_action_handler: AsyncMock,
        mock_tui: MagicMock,
    ):
        """Test that multiple repos have independent timer debouncing."""
        from datetime import timedelta

        from supsrc.config import GlobalConfig, InactivityRuleConfig, RepositoryConfig

        # Create config with multiple repos
        config = SupsrcConfig(
            global_config=GlobalConfig(),
            repositories={
                "repo1": RepositoryConfig(
                    path=temp_git_repo,
                    enabled=True,
                    rule=InactivityRuleConfig(period=timedelta(seconds=30)),
                    repository={"type": "supsrc.engines.git", "branch": "main"},
                ),
                "repo2": RepositoryConfig(
                    path=temp_git_repo,
                    enabled=True,
                    rule=InactivityRuleConfig(period=timedelta(seconds=30)),
                    repository={"type": "supsrc.engines.git", "branch": "main"},
                ),
            },
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()
        repo_states = {
            "repo1": RepositoryState(repo_id="repo1"),
            "repo2": RepositoryState(repo_id="repo2"),
        }

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states=repo_states,
            repo_engines={},
            tui=mock_tui,
            config_reload_callback=AsyncMock(),
        )

        # Mock the timer check method
        with patch.object(processor, "_check_repo_status_and_handle_timer") as mock_timer_check:
            mock_timer_check.return_value = asyncio.create_task(asyncio.sleep(0))

            # Add events for both repos
            event1 = MonitoredEvent("repo1", "modified", temp_git_repo / "test1.py", False)
            event2 = MonitoredEvent("repo2", "modified", temp_git_repo / "test2.py", False)

            await processor.event_queue.put(event1)
            await processor.event_queue.put(event2)

            # Run processor briefly
            run_task = asyncio.create_task(processor.run())
            await asyncio.sleep(0.1)

            # Should have pending timer checks for both repos
            assert "repo1" in processor._pending_timer_checks
            assert "repo2" in processor._pending_timer_checks
            assert len(processor._pending_timer_checks) == 2

            # Wait for debounce delays
            await asyncio.sleep(0.6)

            # Both timer checks should have been called
            assert mock_timer_check.call_count == 2
            mock_timer_check.assert_any_call("repo1")
            mock_timer_check.assert_any_call("repo2")

            # Clean up
            processor.shutdown_event.set()
            await asyncio.gather(run_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_stop_cancels_pending_timer_checks(
        self,
        event_processor_with_timer: EventProcessor,
        temp_git_repo: Path,
    ):
        """Test that stopping the processor cancels pending timer checks."""
        processor = event_processor_with_timer
        repo_id = "test_repo"

        # Mock the timer check method to never complete
        async def long_running_timer_check(repo_id):
            await asyncio.sleep(10)  # Long delay

        with patch.object(
            processor, "_check_repo_status_and_handle_timer", side_effect=long_running_timer_check
        ):
            # Add event
            event = MonitoredEvent(repo_id, "modified", temp_git_repo / "test.py", False)
            await processor.event_queue.put(event)

            # Run processor briefly
            run_task = asyncio.create_task(processor.run())
            await asyncio.sleep(0.1)

            # Should have pending timer check
            assert repo_id in processor._pending_timer_checks
            timer_task = processor._pending_timer_checks[repo_id]

            # Stop processor
            await processor.stop()

            # Give a moment for the cancellation to take effect
            await asyncio.sleep(0.01)

            # Timer task should be cancelled
            assert timer_task.cancelled()
            assert len(processor._pending_timer_checks) == 0

            # Clean up
            processor.shutdown_event.set()
            await asyncio.gather(run_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_schedule_debounced_timer_check_method(self, event_processor_with_timer: EventProcessor):
        """Test the _schedule_debounced_timer_check method directly."""
        processor = event_processor_with_timer
        repo_id = "test_repo"

        # Mock the timer check method
        with patch.object(processor, "_check_repo_status_and_handle_timer", new_callable=AsyncMock):
            # Initially no pending checks
            assert len(processor._pending_timer_checks) == 0

            # Schedule first check
            processor._schedule_debounced_timer_check(repo_id)

            # Should have one pending check
            assert repo_id in processor._pending_timer_checks
            first_task = processor._pending_timer_checks[repo_id]

            # Schedule second check (should cancel first)
            processor._schedule_debounced_timer_check(repo_id)

            # Give a moment for the cancellation to take effect
            await asyncio.sleep(0.01)

            # First task should be cancelled
            assert first_task.cancelled()

            # Should still have one pending check (the new one)
            assert repo_id in processor._pending_timer_checks
            second_task = processor._pending_timer_checks[repo_id]
            assert second_task != first_task
            assert not second_task.cancelled()

            # Clean up pending tasks
            second_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await second_task


# 🔼⚙️🔚
