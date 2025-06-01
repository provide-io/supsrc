# tests/unit/test_cli_watch_repl.py

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from prompt_toolkit.formatted_text import HTML

# Assuming supsrc.cli.watch_cmds is discoverable.
# For local testing, ensure PYTHONPATH is set up or the package is installed.
from supsrc.cli.watch_cmds import (
    ParsedCommand,
    parse_command,
    repl_loop,
    HTML_ERROR, # Import for checking error messages if possible
    HTML_SUCCESS, # Import for checking success messages
    HTML_INFO, # Import for checking info messages
)
from supsrc.runtime.orchestrator import WatchOrchestrator # Needed for typing, will be mocked
from supsrc.state import RepositoryStatus # For asserting state changes if we get that far


# --- Tests for parse_command ---

def test_parse_command_empty_string():
    assert parse_command("") is None

def test_parse_command_only_spaces():
    assert parse_command("   ") is None

def test_parse_command_quit():
    assert parse_command("quit") == ParsedCommand(name="quit", args=())

def test_parse_command_quit_with_spaces():
    assert parse_command("  quit  ") == ParsedCommand(name="quit", args=())

def test_parse_command_pause_repo1():
    assert parse_command("pause repo1") == ParsedCommand(name="pause", args=("repo1",))

def test_parse_command_pause_repo1_with_extra_spaces():
    assert parse_command("  pause   repo1  ") == ParsedCommand(name="pause", args=("repo1",))

def test_parse_command_status_repo1_extra_arg():
    assert parse_command("status repo1 extra_arg") == ParsedCommand(name="status", args=("repo1", "extra_arg"))

def test_parse_command_mixed_case_help():
    assert parse_command("Help") == ParsedCommand(name="help", args=())

def test_parse_command_details_with_args():
    assert parse_command("details my-repo arg2") == ParsedCommand(name="details", args=("my-repo", "arg2"))


# --- Simplified Tests for repl_loop interactions ---
# These tests will focus on whether the correct orchestrator methods are called
# and basic command pathing, rather than exact print_formatted_text output.

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text') # Mocking print_formatted_text
async def test_repl_quit_command(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, True] # Loop once, then shutdown

    mock_session.prompt_async.return_value = "quit"

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_shutdown_event.set.assert_called_once()
    # Check for the "Exiting REPL..." message
    # Example: mock_print_formatted_text.assert_any_call(HTML(HTML_INFO.format(message="Exiting REPL...")))
    # This kind of assertion can be added for all relevant print calls if needed.

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_pause_command_success(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    # Simulate "pause repo1" then "quit"
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["pause repo1", "quit"]

    mock_orchestrator.pause_repository.return_value = True

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_orchestrator.pause_repository.assert_called_once_with("repo1")
    # Example check for success message:
    # expected_msg = HTML(HTML_SUCCESS.format(message="Repository 'repo1' monitoring paused."))
    # mock_print_formatted_text.assert_any_call(expected_msg)

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_pause_command_fail(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["pause repo1", "quit"]

    mock_orchestrator.pause_repository.return_value = False # Simulate failure

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_orchestrator.pause_repository.assert_called_once_with("repo1")
    # Example check for error message:
    # expected_msg = HTML(HTML_ERROR.format(message="Failed to pause monitoring for 'repo1'. May already be paused or not found. Check logs."))
    # mock_print_formatted_text.assert_any_call(expected_msg)

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_pause_command_wrong_args(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["pause", "quit"] # No repo_id

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_orchestrator.pause_repository.assert_not_called()
    # Example check for usage error message:
    # expected_msg = HTML(HTML_ERROR.format(message="Usage: pause &lt;repository_id&gt;"))
    # mock_print_formatted_text.assert_any_call(expected_msg)

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_resume_command_success(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["resume repo1", "quit"]

    mock_orchestrator.resume_repository.return_value = True

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_orchestrator.resume_repository.assert_called_once_with("repo1")

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_details_command_success(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["details repo1", "quit"]

    # Simulate orchestrator returning some history
    mock_orchestrator.get_repository_details.return_value = {
        "repo_id": "repo1",
        "commit_history": ["commit1", "commit2"]
    }

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    mock_orchestrator.get_repository_details.assert_called_once_with("repo1")
    # Add more assertions here to check if print_formatted_text was called with history

@pytest.mark.asyncio
@patch('supsrc.cli.watch_cmds.print_formatted_text')
async def test_repl_unknown_command(mock_print_formatted_text):
    mock_session = AsyncMock()
    mock_orchestrator = MagicMock(spec=WatchOrchestrator)
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.side_effect = [False, False, True]
    mock_session.prompt_async.side_effect = ["foobar", "quit"]

    await repl_loop(mock_session, mock_orchestrator, mock_shutdown_event)

    # Example check for unknown command message
    # expected_msg = HTML(HTML_ERROR.format(message="Unknown command: 'foobar'. Type 'help' for available commands."))
    # mock_print_formatted_text.assert_any_call(expected_msg)

# Add more tests for list, status, and other commands as needed.
# The main challenge is asserting print_formatted_text calls correctly.
# Consider a helper function or fixture if this pattern repeats often.
# For example, a helper that checks if *any* call to mock_print_formatted_text
# contains a certain substring or matches a specific HTML structure.
#
# def assert_printed_html_contains(mock_print_fn, expected_substring):
#     found = False
#     for call_args in mock_print_fn.call_args_list:
#         args, _ = call_args
#         if args and isinstance(args[0], HTML) and expected_substring in args[0].value:
#             found = True
#             break
#     assert found, f"Substring '{expected_substring}' not found in any print_formatted_text HTML call."

# You would then use it like:
# assert_printed_html_contains(mock_print_formatted_text, "Repository 'repo1' monitoring paused.")

# For HTML_ERROR("Usage: pause &lt;repository_id&gt;"), the substring is "Usage: pause <repository_id>"
# because the HTML entities are rendered.
# When using HTML(...).format(message=...), the assertion should be on the formatted string.
# Example: HTML_ERROR.format(message="Usage: pause &lt;repository_id&gt;") has .value
# "Usage: pause <repository_id>" if no color tags, or "<tomato>Usage: pause &lt;repository_id&gt;</tomato>"
# So, asserting against the *content* of the HTML might be more robust.
#
# For example, to check the "Usage: pause <repo_id>" message:
#   expected_html_obj = HTML(HTML_ERROR.format(message="Usage: pause &lt;repository_id&gt;"))
#   mock_print_formatted_text.assert_any_call(expected_html_obj)
# This requires HTML_ERROR to be imported.
# Note: `&lt;` is the HTML entity for `<`.
# The `HTML()` constructor from prompt_toolkit might handle this.
# If `HTML_ERROR` is `<tomato>{message}</tomato>`, then
# `HTML(HTML_ERROR.format(message="Usage: pause &lt;repository_id&gt;"))`
# results in an HTML object representing `<tomato>Usage: pause &lt;repository_id&gt;</tomato>`.
# Asserting this directly is the most accurate way.
```
