# src/supsrc/state/control.py
"""
Data models and validation for external supsrc state control.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from attrs import define, field


@define
class RepositoryStateOverride:
    """Override settings for a specific repository's state."""

    paused: bool = field(default=False)
    save_count_disabled: bool = field(default=False)
    inactivity_seconds: int | None = field(default=None)
    rule_overrides: dict[str, Any] = field(factory=dict)


@define
class StateData:
    """Complete state data structure for .supsrc.state files."""

    # Global state
    paused: bool = field(default=False)
    paused_until: datetime | None = field(default=None)
    paused_by: str | None = field(default=None)
    pause_reason: str | None = field(default=None)

    # Repository-specific overrides
    repositories: dict[str, RepositoryStateOverride] = field(factory=dict)

    # Metadata
    version: str = field(default="1.0.0")
    updated_at: datetime = field(factory=lambda: datetime.now(UTC))
    updated_by: str | None = field(default=None)
    pid: int | None = field(default=None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateData:
        """Create StateData from dictionary loaded from JSON."""
        state_section = data.get("state", {})
        metadata_section = data.get("metadata", {})

        # Parse datetime fields
        paused_until = None
        if state_section.get("paused_until"):
            paused_until = datetime.fromisoformat(
                state_section["paused_until"].replace("Z", "+00:00")
            )

        updated_at = datetime.now(UTC)
        if metadata_section.get("updated_at"):
            updated_at = datetime.fromisoformat(
                metadata_section["updated_at"].replace("Z", "+00:00")
            )

        # Parse repository overrides
        repositories = {}
        for repo_id, repo_data in state_section.get("repositories", {}).items():
            repositories[repo_id] = RepositoryStateOverride(
                paused=bool(repo_data.get("paused", False)),
                save_count_disabled=bool(repo_data.get("save_count_disabled", False)),
                inactivity_seconds=repo_data.get("inactivity_seconds"),
                rule_overrides=dict(repo_data.get("rule_overrides", {})),
            )

        return cls(
            paused=state_section.get("paused", False),
            paused_until=paused_until,
            paused_by=state_section.get("paused_by"),
            pause_reason=state_section.get("pause_reason"),
            repositories=repositories,
            version=str(metadata_section.get("version", "1.0.0")),
            updated_at=updated_at,
            updated_by=metadata_section.get("updated_by"),
            pid=metadata_section.get("pid"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert StateData to dictionary for JSON serialization."""
        repositories_dict = {}
        for repo_id, repo_override in self.repositories.items():
            repo_dict = {
                "paused": repo_override.paused,
                "save_count_disabled": repo_override.save_count_disabled,
            }
            if repo_override.inactivity_seconds is not None:
                repo_dict["inactivity_seconds"] = repo_override.inactivity_seconds
            if repo_override.rule_overrides:
                repo_dict["rule_overrides"] = repo_override.rule_overrides
            repositories_dict[repo_id] = repo_dict

        state_dict = {
            "paused": self.paused,
            "repositories": repositories_dict,
        }

        if self.paused_until:
            state_dict["paused_until"] = self.paused_until.isoformat().replace("+00:00", "Z")
        if self.paused_by:
            state_dict["paused_by"] = self.paused_by
        if self.pause_reason:
            state_dict["pause_reason"] = self.pause_reason

        metadata_dict = {
            "version": self.version,
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }

        if self.updated_by:
            metadata_dict["updated_by"] = self.updated_by
        if self.pid:
            metadata_dict["pid"] = self.pid

        return {"state": state_dict, "metadata": metadata_dict}

    def is_expired(self) -> bool:
        """Check if the pause has expired."""
        if not self.paused or not self.paused_until:
            return False
        return datetime.now(UTC) >= self.paused_until

    def is_repo_paused(self, repo_id: str) -> bool:
        """Check if a specific repository is paused."""
        if self.paused:
            return True
        repo_override = self.repositories.get(repo_id)
        return repo_override.paused if repo_override else False


def validate_state_file(file_path: Path) -> bool:
    """Validate that a state file has correct structure."""
    try:
        with file_path.open("r") as f:
            data = json.load(f)

        # Check required top-level keys
        if not isinstance(data, dict):
            return False

        if "state" not in data or "metadata" not in data:
            return False

        # Basic validation of state section
        state = data["state"]
        if not isinstance(state, dict):
            return False

        # Validate metadata section
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            return False

        return "version" in metadata

    except (json.JSONDecodeError, OSError):
        return False
