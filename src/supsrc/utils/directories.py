#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

from pathlib import Path

from provide.foundation.file import ensure_dir
from provide.foundation.logger import get_logger

log = get_logger("utils.directories")


class SupsrcDirectories:
    """Manages .supsrc/ directory structure for repositories."""

    SUPSRC_DIR = ".supsrc"
    LOCAL_DIR = "local"
    LOGS_DIR = "logs"

    @classmethod
    def ensure_structure(cls, repo_path: Path) -> dict[str, Path]:
        """Create and return all standard directory paths.

        Returns dict with keys:
        - config_dir: .supsrc/
        - local_dir: .supsrc/local/
        - logs_dir: .supsrc/local/logs/
        - state_file: .supsrc/state.json
        - local_state_file: .supsrc/local/state.local.json
        """
        log.debug("Ensuring .supsrc directory structure", repo_path=str(repo_path))

        config_dir = ensure_dir(repo_path / cls.SUPSRC_DIR)
        local_dir = ensure_dir(repo_path / cls.SUPSRC_DIR / cls.LOCAL_DIR)
        logs_dir = ensure_dir(repo_path / cls.SUPSRC_DIR / cls.LOCAL_DIR / cls.LOGS_DIR)

        paths = {
            "config_dir": config_dir,
            "local_dir": local_dir,
            "logs_dir": logs_dir,
            "state_file": config_dir / "state.json",
            "local_state_file": local_dir / "state.local.json",
        }

        log.debug("Directory structure ensured", paths={k: str(v) for k, v in paths.items()})
        return paths

    @classmethod
    def get_log_dir(cls, repo_path: Path) -> Path:
        """Get or create log directory: .supsrc/local/logs/"""
        return ensure_dir(repo_path / cls.SUPSRC_DIR / cls.LOCAL_DIR / cls.LOGS_DIR)

    @classmethod
    def get_state_file(cls, repo_path: Path, local: bool = False) -> Path:
        """Get path for state file (creates parent dirs if needed)"""
        if local:
            ensure_dir(repo_path / cls.SUPSRC_DIR / cls.LOCAL_DIR)
            return repo_path / cls.SUPSRC_DIR / cls.LOCAL_DIR / "state.local.json"
        else:
            ensure_dir(repo_path / cls.SUPSRC_DIR)
            return repo_path / cls.SUPSRC_DIR / "state.json"

    @classmethod
    def get_config_file(cls, repo_path: Path) -> Path:
        """Get path for repository config: .supsrc/config.toml"""
        ensure_dir(repo_path / cls.SUPSRC_DIR)
        return repo_path / cls.SUPSRC_DIR / "config.toml"


# 🔼⚙️🔚
