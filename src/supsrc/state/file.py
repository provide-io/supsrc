# src/supsrc/state/file.py
"""
File operations for .supsrc.state files.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from supsrc.state.control import StateData

log = structlog.get_logger("state.file")


class StateFile:
    """Handles reading and writing .supsrc.state files."""

    STATE_FILENAME = ".supsrc.state"

    @classmethod
    def find_state_file(cls, repo_path: Path | None = None) -> Path | None:
        """Find the most relevant state file for a repository.

        Priority order:
        1. {repo_path}/.supsrc.state - Repository-specific
        2. ~/.config/supsrc/state.json - User-global
        3. /tmp/supsrc-global.state - System-wide temporary
        """
        candidates = []

        # Repository-specific state file
        if repo_path:
            repo_state = repo_path / cls.STATE_FILENAME
            candidates.append(repo_state)

        # User-global state file
        home_dir = Path.home()
        user_config_dir = home_dir / ".config" / "supsrc"
        user_state = user_config_dir / "state.json"
        candidates.append(user_state)

        # System-wide temporary state file
        temp_state = Path("/tmp") / "supsrc-global.state"
        candidates.append(temp_state)

        # Return first existing file
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                log.debug("Found state file", path=str(candidate))
                return candidate

        log.debug("No state file found", candidates=[str(c) for c in candidates])
        return None

    @classmethod
    def get_state_file_path(cls, repo_path: Path | None = None, create_dirs: bool = False) -> Path:
        """Get the path where a state file should be written.

        Prefers repository-specific location, falls back to user config.
        """
        if repo_path:
            state_path = repo_path / cls.STATE_FILENAME
            if create_dirs:
                repo_path.mkdir(parents=True, exist_ok=True)
            return state_path

        # Fall back to user config directory
        user_config_dir = Path.home() / ".config" / "supsrc"
        if create_dirs:
            user_config_dir.mkdir(parents=True, exist_ok=True)
        return user_config_dir / "state.json"

    @classmethod
    def load(cls, file_path: Path | None = None, repo_path: Path | None = None) -> StateData | None:
        """Load state data from file.

        Args:
            file_path: Specific file to load from
            repo_path: Repository path to find state file for

        Returns:
            StateData if file exists and is valid, None otherwise
        """
        from supsrc.state.control import StateData, validate_state_file

        if file_path is None:
            file_path = cls.find_state_file(repo_path)

        if not file_path or not file_path.exists():
            log.debug("State file not found", path=str(file_path) if file_path else None)
            return None

        try:
            # Validate file structure first
            if not validate_state_file(file_path):
                log.warning("Invalid state file structure", path=str(file_path))
                return None

            with file_path.open("r") as f:
                data = json.load(f)

            state_data = StateData.from_dict(data)
            log.debug("Loaded state from file", path=str(file_path), paused=state_data.paused)
            return state_data

        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to load state file", path=str(file_path), error=str(e))
            return None

    @classmethod
    def save(
        cls, state_data: StateData, file_path: Path | None = None, repo_path: Path | None = None
    ) -> bool:
        """Save state data to file using atomic write.

        Args:
            state_data: State data to save
            file_path: Specific file to save to
            repo_path: Repository path to determine save location

        Returns:
            True if save was successful, False otherwise
        """
        if file_path is None:
            file_path = cls.get_state_file_path(repo_path, create_dirs=True)

        try:
            # Use atomic write: write to temp file then move
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".tmp", prefix=".supsrc.state", dir=file_path.parent
            )

            try:
                with os.fdopen(temp_fd, "w") as f:
                    json.dump(state_data.to_dict(), f, indent=2, sort_keys=True)

                # Atomic move to final location
                temp_path_obj = Path(temp_path)
                temp_path_obj.replace(file_path)

                log.debug("Saved state to file", path=str(file_path), paused=state_data.paused)
                return True

            except Exception:
                # Clean up temp file on error
                Path(temp_path).unlink(missing_ok=True)
                raise

        except (OSError, TypeError) as e:
            log.error("Failed to save state file", path=str(file_path), error=str(e))
            return False

    @classmethod
    def delete(cls, file_path: Path | None = None, repo_path: Path | None = None) -> bool:
        """Delete a state file.

        Args:
            file_path: Specific file to delete
            repo_path: Repository path to find state file for

        Returns:
            True if deletion was successful or file didn't exist, False on error
        """
        if file_path is None:
            file_path = cls.find_state_file(repo_path)

        if not file_path or not file_path.exists():
            log.debug(
                "State file doesn't exist, nothing to delete",
                path=str(file_path) if file_path else None,
            )
            return True

        try:
            file_path.unlink()
            log.debug("Deleted state file", path=str(file_path))
            return True

        except OSError as e:
            log.error("Failed to delete state file", path=str(file_path), error=str(e))
            return False

    @classmethod
    def cleanup_expired(cls, repo_paths: list[Path] | None = None) -> int:
        """Clean up expired state files.

        Args:
            repo_paths: List of repository paths to check

        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        search_paths = []

        if repo_paths:
            search_paths.extend(repo_paths)
        else:
            # Check common locations
            search_paths.extend([Path.home() / ".config" / "supsrc", Path("/tmp")])

        for search_path in search_paths:
            if not search_path.exists():
                continue

            # Look for state files
            for state_file in search_path.rglob(cls.STATE_FILENAME):
                state_data = cls.load(state_file)
                if state_data and state_data.is_expired() and cls.delete(state_file):
                    cleaned_count += 1
                    log.info("Cleaned up expired state file", path=str(state_file))

        return cleaned_count
