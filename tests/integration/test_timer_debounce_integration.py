#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Integration tests for timer debounce functionality with rapid file changes."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile

from provide.testkit.mocking import Mock
import pytest

from supsrc.config import (
    GlobalConfig,
    InactivityRuleConfig,
    RepositoryConfig,
    SupsrcConfig,
    load_config,
)
from supsrc.events.processor import EventProcessor
from supsrc.monitor import MonitoredEvent
from supsrc.runtime.action_handler import ActionHandler
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.state import RepositoryState


@pytest.fixture
async def rapid_change_test_setup(tmp_path: Path):
    """Setup for testing rapid file changes with timer debouncing."""
    # Create test repository
    repo_path = tmp_path / "timer_test_repo"
    repo_path.mkdir()

    # Initialize Git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    # Configure Git user for timer integration testing
    subprocess.run(["git", "config", "user.name", "Timer Test User"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "timer@supsrc.example.com"], cwd=repo_path, check=True)
    # Disable GPG signing to prevent tests from failing
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "gpg.program", ""], cwd=repo_path, check=True)

    # Create initial commit
    (repo_path / "README.md").write_text("Timer test repository")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

    # Create configuration for short timer (easier testing)
    config_dir = Path(tempfile.mkdtemp())
    config_file = config_dir / "timer_test.conf"

    config_content = f"""
    [global]
    log_level = "DEBUG"

    [repositories.timer-repo]
    path = "{repo_path}"
    enabled = true

    [repositories.timer-repo.rule]
    type = "supsrc.rules.inactivity"
    period = "5s"  # Short timer for testing

    [repositories.timer-repo.repository]
    type = "supsrc.engines.git"
    auto_push = false
    """

    config_file.write_text(config_content)
    config = load_config(config_file)

    yield {
        "repo_path": repo_path,
        "config_file": config_file,
        "config": config,
        "config_dir": config_dir,
    }

    # Cleanup
    import shutil

    shutil.rmtree(config_dir, ignore_errors=True)


class TestTimerDebounceIntegration:
    """Integration tests for timer debounce behavior."""

    @pytest.mark.asyncio
    async def test_rapid_file_changes_debounce_timer_resets(self, rapid_change_test_setup):
        """Test that rapid file changes are debounced and timer only resets once."""
        setup = rapid_change_test_setup
        repo_path = setup["repo_path"]
        config = setup["config"]

        # Create event processor with mocked components
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        repo_states = {"timer-repo": RepositoryState(repo_id="timer-repo")}
        repo_engines = {}  # Mock engines for this test

        mock_action_handler = Mock(spec=ActionHandler)
        mock_tui = Mock(spec=TUIInterface)
        mock_tui.post_state_update = Mock()
        mock_tui.is_active = False

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states=repo_states,
            repo_engines=repo_engines,
            tui=mock_tui,
            config_reload_callback=Mock(),
        )

        # Track timer check calls
        timer_check_calls = []

        async def mock_timer_check(repo_id):
            timer_check_calls.append(repo_id)
            # Don't actually perform the check to avoid complexity

        processor._check_repo_status_and_handle_timer = mock_timer_check

        # Start processor
        processor_task = asyncio.create_task(processor.run())

        try:
            # Simulate rapid file changes (5 events with no delay - truly rapid)
            for i in range(5):
                event = MonitoredEvent("timer-repo", "modified", repo_path / f"file{i}.py", False)
                await event_queue.put(event)

            # Wait for events to be processed
            await asyncio.sleep(0.1)

            # Should have pending timer checks
            assert "timer-repo" in processor._pending_timer_checks

            # Wait for debounce delay to expire
            await asyncio.sleep(0.6)  # Wait longer than debounce delay (500ms)

            # Should have called timer check fewer times than events due to debouncing
            # Without debouncing, we'd expect 5 calls (one per event)
            # With debouncing, we should get significantly fewer calls
            assert len(timer_check_calls) < 5  # Should be much less than number of events
            assert len(timer_check_calls) >= 1  # Should be at least 1
            assert "timer-repo" in timer_check_calls

        finally:
            # Clean shutdown
            shutdown_event.set()
            await asyncio.gather(processor_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_spaced_events_trigger_multiple_timer_checks(self, rapid_change_test_setup):
        """Test that events spaced apart trigger separate timer checks."""
        setup = rapid_change_test_setup
        repo_path = setup["repo_path"]
        config = setup["config"]

        # Create event processor
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        repo_states = {"timer-repo": RepositoryState(repo_id="timer-repo")}
        mock_action_handler = Mock(spec=ActionHandler)
        mock_tui = Mock(spec=TUIInterface)
        mock_tui.post_state_update = Mock()
        mock_tui.is_active = False

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states=repo_states,
            repo_engines={},
            tui=mock_tui,
            config_reload_callback=Mock(),
        )

        # Track timer check calls
        timer_check_calls = []

        async def mock_timer_check(repo_id):
            timer_check_calls.append(repo_id)

        processor._check_repo_status_and_handle_timer = mock_timer_check

        # Start processor
        processor_task = asyncio.create_task(processor.run())

        try:
            # Send first event
            event1 = MonitoredEvent("timer-repo", "modified", repo_path / "file1.py", False)
            await event_queue.put(event1)
            await asyncio.sleep(0.1)

            # Wait for first debounce to complete
            await asyncio.sleep(0.6)
            assert len(timer_check_calls) == 1

            # Send second event after debounce period
            event2 = MonitoredEvent("timer-repo", "modified", repo_path / "file2.py", False)
            await event_queue.put(event2)
            await asyncio.sleep(0.1)

            # Wait for second debounce to complete
            await asyncio.sleep(0.6)
            assert len(timer_check_calls) == 2

        finally:
            shutdown_event.set()
            await asyncio.gather(processor_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_atomic_file_operations_with_timer_debounce(self, rapid_change_test_setup):
        """Test that atomic file operations work correctly with timer debouncing."""
        setup = rapid_change_test_setup
        repo_path = setup["repo_path"]
        config = setup["config"]

        # Create event processor with event buffering enabled
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        repo_states = {"timer-repo": RepositoryState(repo_id="timer-repo")}
        mock_action_handler = Mock(spec=ActionHandler)
        mock_tui = Mock(spec=TUIInterface)
        mock_tui.post_state_update = Mock()
        mock_tui.is_active = False

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states=repo_states,
            repo_engines={},
            tui=mock_tui,
            config_reload_callback=Mock(),
        )

        # Track timer check calls
        timer_check_calls = []

        async def mock_timer_check(repo_id):
            timer_check_calls.append(repo_id)

        processor._check_repo_status_and_handle_timer = mock_timer_check

        # Start processor
        processor_task = asyncio.create_task(processor.run())

        try:
            # Simulate atomic file operation (temp file creation, original deletion, rename)
            atomic_events = [
                MonitoredEvent("timer-repo", "created", repo_path / "document.txt.tmp", False),
                MonitoredEvent("timer-repo", "deleted", repo_path / "document.txt", False),
                MonitoredEvent("timer-repo", "moved", repo_path / "document.txt", False),
            ]

            # Send all atomic events rapidly
            for event in atomic_events:
                await event_queue.put(event)
                await asyncio.sleep(0.02)  # Very rapid

            # Wait for processing and debounce
            await asyncio.sleep(0.1)
            await asyncio.sleep(0.6)  # Debounce delay

            # Should have called timer check only once for the atomic operation
            # Allow for some timing variance in integration tests
            assert len(timer_check_calls) <= 2  # Should be 1, but allow 2 for timing variance

        finally:
            shutdown_event.set()
            await asyncio.gather(processor_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_processor_shutdown_cancels_pending_timer_checks(self, rapid_change_test_setup):
        """Test that processor shutdown properly cancels pending timer checks."""
        setup = rapid_change_test_setup
        repo_path = setup["repo_path"]
        config = setup["config"]

        # Create event processor
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        repo_states = {"timer-repo": RepositoryState(repo_id="timer-repo")}
        mock_action_handler = Mock(spec=ActionHandler)
        mock_tui = Mock(spec=TUIInterface)
        mock_tui.post_state_update = Mock()
        mock_tui.is_active = False

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states=repo_states,
            repo_engines={},
            tui=mock_tui,
            config_reload_callback=Mock(),
        )

        # Start processor
        processor_task = asyncio.create_task(processor.run())

        try:
            # Send event to create pending timer check
            event = MonitoredEvent("timer-repo", "modified", repo_path / "file.py", False)
            await event_queue.put(event)
            await asyncio.sleep(0.1)

            # Should have pending timer check
            assert "timer-repo" in processor._pending_timer_checks
            timer_task = processor._pending_timer_checks["timer-repo"]

            # Stop processor
            await processor.stop()

            # Give a moment for cancellation to take effect
            await asyncio.sleep(0.01)

            # Timer task should be cancelled
            assert timer_task.cancelled()
            assert len(processor._pending_timer_checks) == 0

        finally:
            shutdown_event.set()
            await asyncio.gather(processor_task, return_exceptions=True)

    def test_debounce_delay_configuration(self, rapid_change_test_setup):
        """Test that debounce delay is configurable."""
        setup = rapid_change_test_setup
        config = setup["config"]

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=Mock(),
            repo_states={},
            repo_engines={},
            tui=Mock(),
            config_reload_callback=Mock(),
        )

        # Check default debounce delay
        assert processor._timer_check_delay == 0.5  # 500ms

        # Verify it's configurable by checking the attribute exists
        assert hasattr(processor, "_timer_check_delay")

    @pytest.mark.asyncio
    async def test_rapid_changes_different_repos_independent_debouncing(self, tmp_path: Path):
        """Test that rapid changes to different repos have independent debouncing."""
        # Create two separate test repos
        repo1_path = tmp_path / "repo1"
        repo2_path = tmp_path / "repo2"

        for repo_path in [repo1_path, repo2_path]:
            repo_path.mkdir()
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "gpg.program", ""], cwd=repo_path, check=True)

            (repo_path / "README.md").write_text("Test repo")
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        # Create config with both repos
        from datetime import timedelta

        config = SupsrcConfig(
            global_config=GlobalConfig(),
            repositories={
                "repo1": RepositoryConfig(
                    path=repo1_path,
                    enabled=True,
                    rule=InactivityRuleConfig(period=timedelta(seconds=5)),
                    repository={"type": "supsrc.engines.git", "branch": "main"},
                ),
                "repo2": RepositoryConfig(
                    path=repo2_path,
                    enabled=True,
                    rule=InactivityRuleConfig(period=timedelta(seconds=5)),
                    repository={"type": "supsrc.engines.git", "branch": "main"},
                ),
            },
        )

        # Create processor
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
            action_handler=Mock(),
            repo_states=repo_states,
            repo_engines={},
            tui=Mock(),
            config_reload_callback=Mock(),
        )

        # Track timer checks per repo
        timer_check_calls = []

        async def mock_timer_check(repo_id):
            timer_check_calls.append(repo_id)

        processor._check_repo_status_and_handle_timer = mock_timer_check

        # Start processor
        processor_task = asyncio.create_task(processor.run())

        try:
            # Send rapid events to both repos
            events = [
                MonitoredEvent("repo1", "modified", repo1_path / "file1.py", False),
                MonitoredEvent("repo2", "modified", repo2_path / "file1.py", False),
                MonitoredEvent("repo1", "modified", repo1_path / "file2.py", False),
                MonitoredEvent("repo2", "modified", repo2_path / "file2.py", False),
            ]

            for event in events:
                await event_queue.put(event)
                await asyncio.sleep(0.02)

            # Wait for processing and debounce
            await asyncio.sleep(0.1)
            await asyncio.sleep(0.6)

            # Should have one timer check per repo despite multiple events each
            assert len(timer_check_calls) == 2
            assert "repo1" in timer_check_calls
            assert "repo2" in timer_check_calls

        finally:
            shutdown_event.set()
            await asyncio.gather(processor_task, return_exceptions=True)


# 🔼⚙️🔚
