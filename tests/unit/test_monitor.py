# tests/unit/test_monitor.py

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

from supsrc.monitor.handler import SupsrcEventHandler
from supsrc.monitor.service import MonitoringService
from supsrc.monitor.events import MonitoredEvent
from supsrc.config.models import RepositoryConfig # Needed for service tests

# --- Tests for SupsrcEventHandler ---

@pytest.fixture
def mock_event_queue():
    return MagicMock(spec=asyncio.Queue)

@pytest.fixture
def mock_loop():
    return MagicMock(spec=asyncio.AbstractEventLoop)

@pytest.fixture
def mock_repo_path(tmp_path):
    # Create a .git directory so the path is considered a repo for some tests
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path

@pytest.fixture
def event_handler(mock_event_queue, mock_loop, mock_repo_path):
    handler = SupsrcEventHandler(
        repo_id="test_repo",
        repo_path=mock_repo_path,
        event_queue=mock_event_queue,
        loop=mock_loop
    )
    # Prevent actual gitignore loading for these unit tests by default
    handler.gitignore_spec = None
    return handler

def test_event_handler_init(event_handler, mock_repo_path):
    assert event_handler.repo_id == "test_repo"
    assert event_handler.repo_path == mock_repo_path
    assert not event_handler._is_paused

def test_event_handler_pause(event_handler):
    event_handler.pause()
    assert event_handler._is_paused

def test_event_handler_resume(event_handler):
    event_handler.pause() # Pause first
    assert event_handler._is_paused
    event_handler.resume()
    assert not event_handler._is_paused

def test_event_handler_process_event_when_paused(event_handler, mock_event_queue):
    event_handler.pause()
    mock_watchdog_event = MagicMock()
    mock_watchdog_event.event_type = "modified"
    mock_watchdog_event.src_path = str(event_handler.repo_path / "some_file.txt")
    mock_watchdog_event.is_directory = False

    # _process_and_queue_event is called by on_modified, on_created etc.
    event_handler._process_and_queue_event(mock_watchdog_event)

    mock_event_queue.put_nowait.assert_not_called() # Should not queue if paused
    # Check if loop.call_soon_threadsafe was not called
    event_handler.loop.call_soon_threadsafe.assert_not_called()


@patch.object(SupsrcEventHandler, '_is_ignored', return_value=False) # Ensure not ignored
def test_event_handler_process_event_when_not_paused(mock_is_ignored, event_handler, mock_event_queue, mock_loop):
    mock_watchdog_event = MagicMock()
    mock_watchdog_event.event_type = "modified"
    src_file_path = event_handler.repo_path / "some_file.txt"
    mock_watchdog_event.src_path = str(src_file_path)
    mock_watchdog_event.is_directory = False

    # Mock loop.is_running() to return True
    mock_loop.is_running.return_value = True

    event_handler.resume() # Ensure not paused
    event_handler._process_and_queue_event(mock_watchdog_event)

    # Check that loop.call_soon_threadsafe was called with _queue_event_threadsafe
    # and a MonitoredEvent
    assert mock_loop.call_soon_threadsafe.call_count == 1
    args, _ = mock_loop.call_soon_threadsafe.call_args
    target_func = args[0]
    event_arg = args[1]

    assert target_func == event_handler._queue_event_threadsafe
    assert isinstance(event_arg, MonitoredEvent)
    assert event_arg.repo_id == "test_repo"
    assert event_arg.src_path == src_file_path.resolve()


# --- Tests for MonitoringService ---

@pytest.fixture
def monitoring_service(mock_event_queue):
    return MonitoringService(event_queue=mock_event_queue)

@pytest.fixture
def mock_repo_config(mock_repo_path):
    # A basic RepositoryConfig. Adjust fields as necessary for your tests.
    # Assuming RepositoryConfig has 'enabled' and 'path' attributes.
    # And _path_valid is set by the config loader.
    config = MagicMock(spec=RepositoryConfig)
    config.enabled = True
    config.path = mock_repo_path
    config._path_valid = True # Assume path validation passed
    config.repository = {"type": "supsrc.engines.git"} # Example engine config
    return config

@patch('supsrc.monitor.service.SupsrcEventHandler') # Mock the handler class
def test_monitoring_service_add_repository(MockSupsrcEventHandler, monitoring_service, mock_repo_config, mock_loop):
    mock_handler_instance = MockSupsrcEventHandler.return_value

    monitoring_service.add_repository("repo1", mock_repo_config, mock_loop)

    MockSupsrcEventHandler.assert_called_once_with(
        repo_id="repo1",
        repo_path=mock_repo_config.path,
        event_queue=monitoring_service._event_queue,
        loop=mock_loop
    )
    monitoring_service._observer.schedule.assert_called_once_with(
        mock_handler_instance, str(mock_repo_config.path), recursive=True
    )
    assert "repo1" in monitoring_service._handlers
    assert monitoring_service._handlers["repo1"] == mock_handler_instance

def test_monitoring_service_pause_monitoring_success(monitoring_service):
    mock_handler = MagicMock(spec=SupsrcEventHandler)
    monitoring_service._handlers["repo1"] = mock_handler

    result = monitoring_service.pause_monitoring("repo1")

    assert result is True
    mock_handler.pause.assert_called_once()

def test_monitoring_service_pause_monitoring_not_found(monitoring_service):
    result = monitoring_service.pause_monitoring("non_existent_repo")
    assert result is False

def test_monitoring_service_resume_monitoring_success(monitoring_service):
    mock_handler = MagicMock(spec=SupsrcEventHandler)
    monitoring_service._handlers["repo1"] = mock_handler

    result = monitoring_service.resume_monitoring("repo1")

    assert result is True
    mock_handler.resume.assert_called_once()

def test_monitoring_service_resume_monitoring_not_found(monitoring_service):
    result = monitoring_service.resume_monitoring("non_existent_repo")
    assert result is False

# Tests for start/stop of MonitoringService are more complex due to threading
# and might be better suited for integration tests or require more advanced mocking.
# For this subtask, focusing on add, pause, and resume logic.
```
