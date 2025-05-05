#
# filename: src/supsrc/protocols.py
#
"""
Defines the runtime protocols for supsrc components like Rules, Engines,
and standard result objects.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import attrs  # Import attrs

from supsrc.config.models import GlobalConfig  # Assuming config models exist

# Re-export or define core types needed by protocols
from supsrc.state import RepositoryState  # Assuming state.py exists

# --- Base Result Structure ---

# Using attrs.define for a concrete base makes things simpler sometimes,
# but let's stick to Protocol for the base interface and define concrete
# results where needed or let implementations return attrs classes that
# conform to the protocol.

@runtime_checkable
class PluginResult(Protocol):
    """Base protocol for plugin execution results."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None


# --- Concrete Result Objects (Examples using attrs for implementations) ---
# These are examples of how implementations might define their results.
# The protocols below define the *interface* the orchestrator expects.

@attrs.define(frozen=True, slots=True)
class ExampleConcreteConversionResult:
    """Example concrete implementation detail for ConversionResult."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None
    processed_files: list[Path] | None = None
    output_data: Any | None = None


@attrs.define(frozen=True, slots=True)
class ExampleConcreteCommitResult:
    """Example concrete implementation detail for CommitResult."""
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None
    commit_hash: str | None = None


# --- Result Protocols (What the Orchestrator expects) ---

@runtime_checkable
class ConversionResult(PluginResult, Protocol):
    """Protocol for results from a conversion step."""
    processed_files: list[Path] | None = None # Files modified/created
    output_data: Any | None = None # Optional structured output


@runtime_checkable
class RepoStatusResult(PluginResult, Protocol):
    """Protocol for results from checking repository status."""
    # Explicitly list the fields expected by the orchestrator
    # This makes the interface clearer than just inheriting PluginResult.
    success: bool
    message: str | None = None
    details: dict[str, Any] | None = None
    is_clean: bool | None = None
    has_staged_changes: bool | None = None
    has_unstaged_changes: bool | None = None
    # Add other relevant status flags potentially needed
    has_untracked_changes: bool | None = None # Example addition
    is_conflicted: bool | None = None # Example addition
    is_unborn: bool | None = None # Example addition


@runtime_checkable
class StageResult(PluginResult, Protocol):
    """Protocol for results from staging changes."""
    # Currently just inherits success/message/details from PluginResult


@runtime_checkable
class CommitResult(PluginResult, Protocol):
    """Protocol for results from performing a commit."""
    commit_hash: str | None = None


@runtime_checkable
class PushResult(PluginResult, Protocol):
    """Protocol for results from performing a push."""
    # Currently just inherits success/message/details from PluginResult


# --- Engine/Rule Protocols ---

@runtime_checkable
class Rule(Protocol):
    """Protocol for a rule that determines if an action should trigger."""

    def check(self, state: RepositoryState, config: Any, global_config: GlobalConfig) -> bool:
        """
        Checks if the rule's condition is met based on state and config.

        Args:
            state: The current RepositoryState.
            config: The specific configuration block for this rule instance
                    (e.g., an InactivityRuleConfig object).
            global_config: The global configuration section.

        Returns:
            True if the condition is met, False otherwise.
        """
        ...

# ConversionStep Protocol remains the same conceptually
@runtime_checkable
class ConversionStep(Protocol):
    """Protocol for a step in the file conversion/processing pipeline."""
    async def process(
        self, files: list[Path], state: RepositoryState, config: Any, global_config: GlobalConfig, working_dir: Path
    ) -> ConversionResult: ...


@runtime_checkable
class RepositoryEngine(Protocol):
    """Protocol for interacting with a repository (VCS or other)."""

    async def get_status(
        self, state: RepositoryState, config: Any, global_config: GlobalConfig, working_dir: Path
    ) -> RepoStatusResult: # <- Expects an object conforming to this
        """Check the current status of the repository (clean, changes, etc.)."""
        ...

    async def stage_changes(
        self, files: list[Path] | None, state: RepositoryState, config: Any, global_config: GlobalConfig, working_dir: Path
    ) -> StageResult:
        """Stage specified files, or all changes if files is None."""
        ...

    async def perform_commit(
        self, message_template: str, state: RepositoryState, config: Any, global_config: GlobalConfig, working_dir: Path
    ) -> CommitResult:
        """Perform the commit action with the given message template."""
        ...

    async def perform_push(
        self, state: RepositoryState, config: Any, global_config: GlobalConfig, working_dir: Path
    ) -> PushResult:
        """Perform the push action."""
        ...

    # --- Optional Methods (Examples) ---
    # async def get_summary(self, working_dir: Path) -> Any: ... # Define a SummaryResult protocol if needed


# Ensure TypeAlias is imported if used elsewhere, though not strictly needed here now

# 🔼⚙️
