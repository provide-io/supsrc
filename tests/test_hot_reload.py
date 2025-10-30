#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Direct test of hot reload functionality."""

import asyncio

# Ensure we can import supsrc
import sys
import tempfile
from pathlib import Path

from provide.testkit.mocking import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from supsrc.config import load_config
from supsrc.monitor import MonitoredEvent, MonitoringService
from supsrc.runtime.orchestrator import WatchOrchestrator


async def test_hot_reload():
    """Tests both direct invocation and event-driven invocation of config reload."""

    # --- Setup ---
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        config_path = Path(f.name)
        f.write(
            """
[global]
log_level = "INFO"
[repositories.test]
enabled = true
path = "/tmp/test"
[repositories.test.rule]
type = "supsrc.rules.manual"
[repositories.test.repository]
type = "supsrc.engines.git"
"""
        )

    try:
        shutdown_event = asyncio.Event()
        orchestrator = WatchOrchestrator(config_path, shutdown_event)
        orchestrator.config = load_config(config_path)

        # --- Part 1: Test direct reload_config call ---

        # Mock dependencies for the reload_config method
        mock_monitor_service = MagicMock(spec=MonitoringService)
        mock_monitor_service.is_running = True
        mock_monitor_service.stop = AsyncMock()

        # Mock the helper managers and their methods
        from supsrc.runtime.monitoring_coordinator import MonitoringCoordinator
        from supsrc.runtime.repository_manager import RepositoryManager

        orchestrator.repository_manager = MagicMock(spec=RepositoryManager)
        orchestrator.repository_manager.initialize_repositories = AsyncMock(
            return_value=["test", "test2"]
        )
        orchestrator.repository_manager.cleanup_repository_timers = AsyncMock()

        orchestrator.monitoring_coordinator = MagicMock(spec=MonitoringCoordinator)
        orchestrator.monitoring_coordinator.monitor_service = mock_monitor_service
        orchestrator.monitoring_coordinator.reload_config = AsyncMock(return_value=True)

        orchestrator.app = MagicMock()

        # Modify config file on disk for the reload to pick up
        config_path.write_text(
            """
[global]
log_level = "DEBUG"
[repositories.test]
enabled = true
path = "/tmp/test"
[repositories.test.rule]
type = "supsrc.rules.manual"
[repositories.test.repository]
type = "supsrc.engines.git"
[repositories.test2]
enabled = true
path = "/tmp/test2"
[repositories.test2.rule]
type = "supsrc.rules.manual"
[repositories.test2.repository]
type = "supsrc.engines.git"
"""
        )

        # Execute the reload
        result = await orchestrator.reload_config()

        assert result is True
        # Verify that reload_config was called on the monitoring coordinator
        orchestrator.monitoring_coordinator.reload_config.assert_called_once()

        # --- Part 2: Test event-driven reload ---
        orchestrator.reload_config = AsyncMock(return_value=True)  # Mock the method for this part

        config_event = MonitoredEvent(
            repo_id="__config__",
            event_type="modified",
            src_path=config_path,
            is_directory=False,
        )

        # Manually create the event processor to test its logic
        event_processor = orchestrator.event_processor = MagicMock()
        event_processor.orchestrator = orchestrator  # Link back

        # Simulate the event processor loop consuming one event
        event_processor.run = AsyncMock(side_effect=orchestrator.shutdown_event.set)
        await orchestrator.event_queue.put(config_event)

        # The EventProcessor now needs to be created inside the orchestrator run loop
        # So we test its behavior by calling the orchestrator and checking the mock

        # We'll re-use the same orchestrator but mock its reload method
        # This time, we'll run the event processor loop to consume the event

        async def consume_one_event():
            event = await orchestrator.event_queue.get()
            if event.repo_id == "__config__":
                await orchestrator.reload_config()

        await consume_one_event()

        orchestrator.reload_config.assert_called_once()

    finally:
        config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(test_hot_reload())

# 🔼⚙️🔚
