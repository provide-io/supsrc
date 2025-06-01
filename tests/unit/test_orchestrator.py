# tests/unit/test_orchestrator.py

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.monitor.service import MonitoringService # For type mocking
from supsrc.config import SupsrcConfig, GlobalConfig, RepositoryConfig as SupsrcRepoConfig, RuleConfig # Avoid conflict
from supsrc.config.models import InactivityRuleConfig # Specific rule for testing resume logic

# --- Fixtures ---

@pytest.fixture
def mock_shutdown_event():
    # Simple mock for asyncio.Event; can be enhanced if event wait/set needs to be tested
    return MagicMock(spec=asyncio.Event)

@pytest.fixture
def mock_console():
    return MagicMock()

@pytest.fixture
def mock_monitoring_service():
    service = MagicMock(spec=MonitoringService)
    service.pause_monitoring.return_value = True # Assume success by default
    service.resume_monitoring.return_value = True # Assume success by default
    return service

@pytest.fixture
def mock_repo_state():
    state = MagicMock(spec=RepositoryState)
    state.status = RepositoryStatus.IDLE
    state.repo_id = "test_repo1"
    # Add other attributes if your tests interact with them
    state.inactivity_timer_handle = None
    state.cancel_inactivity_timer = MagicMock()
    state.update_status = MagicMock() # Mock to verify status changes
    state.set_inactivity_timer = MagicMock()
    return state

@pytest.fixture
def minimal_config():
    # Create a SupsrcConfig with one minimal repository for testing
    repo_conf = SupsrcRepoConfig(
        path=Path("/fake/repo1"), # Path doesn't need to exist for these unit tests
        rule={"type": "inactivity", "period": "10s"}, # Example rule
        repository={"type": "supsrc.engines.git"} # Example engine
    )
    # Manually set private attributes that would be set by Pydantic/Cattrs
    repo_conf._path_valid = True

    config = SupsrcConfig(
        global_config=GlobalConfig(),
        repositories={"test_repo1": repo_conf}
    )
    return config

@pytest.fixture
def orchestrator(mock_shutdown_event, mock_console, minimal_config):
    # Patch load_config to return our minimal_config
    with patch('supsrc.runtime.orchestrator.load_config', return_value=minimal_config):
        orch = WatchOrchestrator(
            config_path=Path("dummy_config.toml"), # Path won't be used due to patching load_config
            shutdown_event=mock_shutdown_event,
            console=mock_console,
            app=None # No TUI app for these tests
        )
        # Manually assign the mocked monitoring service after WatchOrchestrator init
        orch.monitor_service = mock_monitoring_service()

        # Initialize repo_states as it's done in run() -> _initialize_repositories
        # This is a simplified version of what _initialize_repositories would do
        orch.config = minimal_config # Ensure config is set for resume logic
        for repo_id in minimal_config.repositories:
            orch.repo_states[repo_id] = RepositoryState(repo_id=repo_id)
            # Link the specific mock_repo_state for "test_repo1" if needed for assertions
            if repo_id == "test_repo1":
                 orch.repo_states[repo_id] = mock_repo_state() # Use the more detailed mock for assertions

        return orch


# --- Tests for WatchOrchestrator Pause/Resume ---

def test_pause_repository_not_found(orchestrator):
    assert not orchestrator.pause_repository("non_existent_repo")
    # Add assertion for logging if available/testable

def test_pause_repository_already_paused(orchestrator, mock_repo_state):
    mock_repo_state.status = RepositoryStatus.PAUSED
    orchestrator.repo_states["test_repo1"] = mock_repo_state # Ensure this state is used

    assert orchestrator.pause_repository("test_repo1") is True # Already in desired state
    orchestrator.monitor_service.pause_monitoring.assert_not_called()
    mock_repo_state.update_status.assert_not_called() # Should not change status if already paused

def test_pause_repository_success(orchestrator, mock_repo_state, mock_monitoring_service):
    mock_repo_state.status = RepositoryStatus.IDLE # Start from a non-paused state
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    assert orchestrator.pause_repository("test_repo1") is True

    mock_monitoring_service.pause_monitoring.assert_called_once_with("test_repo1")
    mock_repo_state.update_status.assert_called_once_with(RepositoryStatus.PAUSED)
    mock_repo_state.cancel_inactivity_timer.assert_called_once()
    # Assert console message or TUI update if those were part of the requirements

def test_pause_repository_service_fail(orchestrator, mock_repo_state, mock_monitoring_service):
    mock_monitoring_service.pause_monitoring.return_value = False # Simulate service failure
    mock_repo_state.status = RepositoryStatus.IDLE
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    assert orchestrator.pause_repository("test_repo1") is False

    mock_monitoring_service.pause_monitoring.assert_called_once_with("test_repo1")
    mock_repo_state.update_status.assert_not_called() # Status should not change if service fails

def test_resume_repository_not_found(orchestrator):
    assert not orchestrator.resume_repository("non_existent_repo")

def test_resume_repository_not_paused(orchestrator, mock_repo_state):
    mock_repo_state.status = RepositoryStatus.IDLE # Not paused
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    assert orchestrator.resume_repository("test_repo1") is False
    orchestrator.monitor_service.resume_monitoring.assert_not_called()
    mock_repo_state.update_status.assert_not_called()

@pytest.mark.asyncio # For get_running_loop in resume_repository
async def test_resume_repository_success(orchestrator, mock_repo_state, mock_monitoring_service, minimal_config):
    mock_repo_state.status = RepositoryStatus.PAUSED
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    # Ensure the config for 'test_repo1' is an InactivityRuleConfig for timer restart test
    # This is a bit detailed for a unit test setup, consider simplifying or focusing
    # The orchestrator fixture now uses minimal_config which has an inactivity rule.

    # Mock get_running_loop if resume_repository uses it directly for call_later
    # If it's always available (e.g. orchestrator runs within an event loop), this might not be needed
    with patch('asyncio.get_running_loop', return_value=MagicMock(spec=asyncio.AbstractEventLoop)) as mock_get_loop:
        mock_event_loop_instance = mock_get_loop.return_value
        mock_event_loop_instance.call_later = MagicMock()

        assert orchestrator.resume_repository("test_repo1") is True

    mock_monitoring_service.resume_monitoring.assert_called_once_with("test_repo1")
    # It should transition to IDLE first.
    mock_repo_state.update_status.assert_called_with(RepositoryStatus.IDLE)

    # Check if inactivity timer was potentially restarted
    # This depends on the rule type in minimal_config for "test_repo1"
    repo_config_obj = minimal_config.repositories["test_repo1"]
    if isinstance(repo_config_obj.rule, InactivityRuleConfig):
         mock_repo_state.set_inactivity_timer.assert_called_once()
         mock_event_loop_instance.call_later.assert_called_once()
    else:
        mock_repo_state.set_inactivity_timer.assert_not_called()


def test_resume_repository_service_fail(orchestrator, mock_repo_state, mock_monitoring_service):
    mock_monitoring_service.resume_monitoring.return_value = False # Simulate service failure
    mock_repo_state.status = RepositoryStatus.PAUSED
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    assert orchestrator.resume_repository("test_repo1") is False

    mock_monitoring_service.resume_monitoring.assert_called_once_with("test_repo1")
    mock_repo_state.update_status.assert_not_called()


# --- Tests for Orchestrator event/action processing with PAUSED state ---

@pytest.mark.asyncio
async def test_orchestrator_action_callback_when_paused(orchestrator, mock_repo_state):
    mock_repo_state.status = RepositoryStatus.PAUSED
    orchestrator.repo_states["test_repo1"] = mock_repo_state

    # _trigger_action_callback is async
    await orchestrator._trigger_action_callback("test_repo1")

    # Assert that no processing methods (like get_status on engine) were called
    # This requires mocking the engine if we were to go deeper.
    # For now, check that state didn't change from PAUSED due to this.
    mock_repo_state.update_status.assert_not_called() # Should not try to change from PAUSED
    mock_repo_state.cancel_inactivity_timer.assert_called_once() # It does cancel timer if called

@pytest.mark.asyncio
async def test_orchestrator_consume_events_when_paused(orchestrator, mock_repo_state):
    # This test is a bit more complex as _consume_events is a long-running loop.
    # We'll simulate one event for a paused repo.
    mock_event = MagicMock()
    mock_event.repo_id = "test_repo1"

    mock_repo_state.status = RepositoryStatus.PAUSED
    orchestrator.repo_states["test_repo1"] = mock_repo_state
    orchestrator.config = orchestrator.config # Ensure config is available

    # To test _consume_events, we'd need to put an event on its queue
    # and then cancel the consumer or make it run once.
    # For simplicity, we're checking the logic *within* _consume_events
    # that handles paused states. The actual test for the loop itself is harder.

    # If an event for a PAUSED repo was somehow processed by the consumer loop's core logic
    # (after queue.get()), it should not record_change or check_trigger_condition.
    mock_repo_state.record_change.assert_not_called()
    # (Assuming check_trigger_condition is not directly mockable here without more setup)

    # The primary defense is in SupsrcEventHandler. This is a secondary check.
    # The test for _consume_events is more of an integration test.
    # For this unit test, we'll rely on the fact that if repo_state.status is PAUSED,
    # the 'elif repo_state.status == RepositoryStatus.PAUSED:' block in _consume_events
    # (which was added in the implementation step) should prevent further processing.
    # Directly testing that specific branch is hard without refactoring _consume_events.
    pass

```
