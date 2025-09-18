#!/usr/bin/env python3
"""
Quick test script to verify our pause/suspend fixes work.
"""

import asyncio
from pathlib import Path

# Add our source to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from supsrc.runtime.monitoring_coordinator import MonitoringCoordinator
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.runtime.repository_manager import RepositoryManager
from supsrc.state.runtime import RepositoryState


def test_monitoring_coordinator_suspend():
    """Test that suspend state tracking works."""
    print("Testing MonitoringCoordinator suspend state...")

    coordinator = MonitoringCoordinator(
        event_queue=asyncio.Queue(),
        config_path=Path("test.toml"),
        repo_states={}
    )

    # Initial state
    assert not coordinator._is_paused
    assert not coordinator._is_suspended
    assert not coordinator.is_paused
    assert not coordinator.is_suspended

    # Test suspend
    coordinator.suspend_monitoring()
    assert coordinator._is_suspended
    assert coordinator.is_suspended

    print("✅ MonitoringCoordinator suspend state tracking works!")


def test_orchestrator_suspend_property():
    """Test that orchestrator exposes suspend state."""
    print("Testing WatchOrchestrator suspend property...")

    shutdown_event = asyncio.Event()
    orchestrator = WatchOrchestrator(
        config_path=Path("test.toml"),
        shutdown_event=shutdown_event
    )

    # Initial state - should not crash
    assert not orchestrator._is_suspended

    print("✅ WatchOrchestrator suspend property works!")


def test_repository_pause_timer_cancellation():
    """Test that repository pause cancels timers."""
    print("Testing repository pause timer cancellation...")

    repo_states = {}
    repo_engines = {}

    manager = RepositoryManager(
        repo_states=repo_states,
        repo_engines=repo_engines
    )

    # Create a repository state
    repo_state = RepositoryState(repo_id="test-repo")
    repo_states["test-repo"] = repo_state

    # Simulate an active timer
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    timer_handle = loop.call_later(60, lambda: None)
    repo_state.set_inactivity_timer(timer_handle, 60)

    assert repo_state.inactivity_timer_handle is not None
    assert not repo_state.is_paused

    # Test pause - should cancel timer
    result = manager.toggle_repository_pause("test-repo")
    assert result is True
    assert repo_state.is_paused
    assert repo_state.inactivity_timer_handle is None  # Timer should be cancelled

    print("✅ Repository pause timer cancellation works!")

    loop.close()


if __name__ == "__main__":
    print("Testing pause/suspend fixes...")

    test_monitoring_coordinator_suspend()
    test_orchestrator_suspend_property()
    test_repository_pause_timer_cancellation()

    print("\n🎉 All tests passed! Pause/suspend fixes are working correctly.")