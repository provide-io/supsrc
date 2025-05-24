#
# supsrc/tui/messages.py
#
"""
Defines custom messages for the Textual User Interface (TUI).
"""

from typing import (  # Changed from "Dict" to "dict" for modern Python, textual.message.Message uses it.
    Any,
)

from textual.message import Message

# Type alias for state map used within StateUpdate (avoiding direct import of RepositoryStatesMap)
# This is for type hinting within this file only.
# The actual RepositoryStatesMap type from orchestrator will be used in app.py.
RepoStatesDictForMessage: dict[str, Any] # type: ignore


class StateUpdate(Message):
    """Message to update the main repository status table in the TUI."""
    ALLOW_BUBBLE = True # Or False if only handled by App

    def __init__(self, repo_states: RepoStatesDictForMessage) -> None:
        self.repo_states = repo_states
        super().__init__()

class LogMessageUpdate(Message):
    """Message to send a new log entry to the TUI's event log."""
    ALLOW_BUBBLE = True # Or False if only handled by App

    def __init__(self, repo_id: str | None, level: str, message: str) -> None:
        self.repo_id = repo_id
        self.level = level
        self.message = message
        super().__init__()

class RepoDetailUpdate(Message):
    """Message to update the repo detail pane with fetched information."""
    ALLOW_BUBBLE = True # Or False if only handled by App

    def __init__(self, repo_id: str, details: dict[str, Any]) -> None:
        self.repo_id = repo_id
        self.details = details # This will contain {"commit_history": [...]}
        super().__init__()

# 🔼⚙️
