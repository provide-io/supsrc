#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""File operations for .supsrc.state files."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from provide.foundation.file import read_json, write_json
from provide.foundation.logger import get_logger

from supsrc.utils.directories import SupsrcDirectories

if TYPE_CHECKING:
    from supsrc.state.control import StateData

log = get_logger("state.file")


class StateFile:
    """Handles reading and writing .supsrc.state files."""

    STATE_FILENAME = ".supsrc/state.json"
    LOCAL_STATE_FILENAME = ".supsrc/local/state.local.json"

    @classmethod
    def find_state_file(cls, repo_path: Path | None = None, local: bool = False) -> Path | None:
        """Find the most relevant state file for a repository.

        Local=False (shareable state):
        1. {repo_path}/.supsrc/state.json
        2. ~/.config/supsrc/state.json - User-global

        Local=True (machine-specific):
        1. {repo_path}/.supsrc/local/state.local.json
        2. /tmp/supsrc-global.state - System-wide temporary
        """
        candidates = []

        # Repository-specific state file
        if repo_path:
            if local:
                repo_state = SupsrcDirectories.get_state_file(repo_path, local=True)
            else:
                repo_state = SupsrcDirectories.get_state_file(repo_path, local=False)
            candidates.append(repo_state)

        if local:
            # System-wide temporary state file for local data
            temp_state = Path(tempfile.gettempdir()) / "supsrc-global.state"
            candidates.append(temp_state)
        else:
            # User-global state file for shared data
            home_dir = Path.home()
            user_config_dir = home_dir / ".config" / "supsrc"
            user_state = user_config_dir / "state.json"
            candidates.append(user_state)

        # Return first existing file
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                log.debug("Found state file", path=str(candidate), local=local)
                return candidate

        log.debug("No state file found", candidates=[str(c) for c in candidates], local=local)
        return None

    @classmethod
    def get_state_file_path(cls, repo_path: Path | None = None, local: bool = False) -> Path:
        """Get the path where a state file should be written.

        Prefers repository-specific location, falls back to user config.
        """
        if repo_path:
            return SupsrcDirectories.get_state_file(repo_path, local=local)

        # Fall back to user config directory for shared data
        # or temp directory for local data
        if local:
            return Path(tempfile.gettempdir()) / "supsrc-global.state"
        else:
            from provide.foundation.file import ensure_dir

            user_config_dir = ensure_dir(Path.home() / ".config" / "supsrc")
            return user_config_dir / "state.json"

    @classmethod
    def load(
        cls, file_path: Path | None = None, repo_path: Path | None = None, local: bool = False
    ) -> StateData | None:
        """Load state data from file.

        Args:
            file_path: Specific file to load from
            repo_path: Repository path to find state file for

        Returns:
            StateData if file exists and is valid, None otherwise
        """
        from supsrc.state.control import StateData, validate_state_file

        if file_path is None:
            file_path = cls.find_state_file(repo_path, local=local)

        if not file_path or not file_path.exists():
            log.debug("State file not found", path=str(file_path) if file_path else None)
            return None

        try:
            # Validate file structure first
            if not validate_state_file(file_path):
                log.warning("Invalid state file structure", path=str(file_path))
                return None

            data = read_json(file_path)
            if data is None:
                log.debug("Empty or invalid state file", path=str(file_path))
                return None

            state_data = StateData.from_dict(data)
            log.debug("Loaded state from file", path=str(file_path), paused=state_data.paused)
            return state_data

        except Exception as e:
            log.error("Failed to load state file", path=str(file_path), error=str(e))
            return None

    @classmethod
    def save(
        cls,
        state_data: StateData,
        file_path: Path | None = None,
        repo_path: Path | None = None,
        local: bool = False,
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
            file_path = cls.get_state_file_path(repo_path, local=local)

        try:
            # Use foundation's atomic write_json
            write_json(file_path, state_data.to_dict(), indent=2, sort_keys=True, atomic=True)
            log.debug("Saved state to file", path=str(file_path), paused=state_data.paused)
            return True

        except Exception as e:
            log.error("Failed to save state file", path=str(file_path), error=str(e))
            return False

    @classmethod
    def delete(cls, file_path: Path | None = None, repo_path: Path | None = None, local: bool = False) -> bool:
        """Delete a state file.

        Args:
            file_path: Specific file to delete
            repo_path: Repository path to find state file for

        Returns:
            True if deletion was successful or file didn't exist, False on error
        """
        if file_path is None:
            file_path = cls.find_state_file(repo_path, local=local)

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
            search_paths.extend([Path.home() / ".config" / "supsrc", Path(tempfile.gettempdir())])

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


# 🔼⚙️🔚
