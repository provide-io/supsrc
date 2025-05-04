#
# supsrc/protocols.py
#

from typing import Protocol, Any, runtime_checkable
from pathlib import Path
from enum import Enum

# Re-export or define core types needed by protocols
from supsrc.state import RepositoryState, RepositoryStatus # Assuming state.py exists
from supsrc.config.models import SupsrcConfig # Assuming config models exist

# --- Result Objects (Examples - Define robustly) ---
# These help standardize return values from engine methods

@runtime_checkable
class PluginResult(Protocol):
    """Base for plugin execution results."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None

class ConversionResult(PluginResult):
    """Result from a conversion step."""
    processed_files: list[Path] | None = None # Files modified/created
    output_data: Any | None = None # Optional structured output

class RepoStatusResult(PluginResult):
    """Result from checking repository status."""
    is_clean: bool | None = None
    has_staged_changes: bool | None = None
    has_unstaged_changes: bool | None = None
    # Add more specific fields as needed (e.g., branch, conflicts)

class StageResult(PluginResult): ... # Simple success/failure + message
class CommitResult(PluginResult):
    commit_hash: str | None = None
class PushResult(PluginResult): ... # Simple success/failure + message

# --- Engine Protocols ---

@runtime_checkable
class Rule(Protocol):
    """Protocol for a rule that determines if an action should trigger."""

    def check(self, state: RepositoryState, config: Any, global_config: Any) -> bool:
        """
        Checks if the rule's condition is met based on state and config.

        Args:
            state: The current RepositoryState.
            config: The specific configuration block for this rule instance.
            global_config: The global configuration section.

        Returns:
            True if the condition is met, False otherwise.
        """
        ...

@runtime_checkable
class ConversionStep(Protocol):
    """Protocol for a step in the file conversion/processing pipeline."""

    async def process(
        self,
        files: list[Path],
        state: RepositoryState,
        config: Any,
        global_config: Any,
        working_dir: Path,
    ) -> ConversionResult:
        """
        Processes a list of files based on the step's logic.

        Args:
            files: List of absolute paths to potentially changed files.
                   (May need refinement - perhaps provide diff info?)
            state: The current RepositoryState.
            config: The specific configuration block for this conversion step.
            global_config: The global configuration section.
            working_dir: The root directory of the repository being processed.

        Returns:
            A ConversionResult indicating success/failure and outcomes.
        """
        ...

@runtime_checkable
class RepositoryEngine(Protocol):
    """Protocol for interacting with a repository (VCS or other)."""

    async def get_status(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> RepoStatusResult:
        """Check the current status of the repository (clean, changes, etc.)."""
        ...

    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        ...

    async def perform_commit(
        self, message: str, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with the given message."""
        ...

    async def perform_push(
        self, state: RepositoryState, config: Any, global_config: Any, working_dir: Path
    ) -> PushResult:
        """Perform the push action."""
        ...

    # Optional: Add methods for init, clone, fetch, etc. if needed later

# 🔼⚙️
