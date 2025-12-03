#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

import asyncio
from pathlib import Path

from provide.foundation.logger import get_logger

log = get_logger("runtime.workflow.git_operations")


class GitOperationsHelper:
    """Helper class for Git operations in the workflow."""

    @staticmethod
    async def get_staged_diff(workdir: Path) -> str:
        """Runs `git diff --staged` and returns the output.

        Args:
            workdir: Working directory where git command should be run

        Returns:
            Staged diff output as string, empty string if command fails
        """
        proc = await asyncio.create_subprocess_shell(
            "git diff --staged",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.error("Failed to get staged diff", stderr=stderr.decode())
            return ""
        return stdout.decode()

    @staticmethod
    async def save_change_fragment(
        content: str, repo_path: Path, fragment_dir: str | None, commit_hash: str
    ) -> None:
        """Saves a change fragment to the specified directory.

        Args:
            content: Fragment content to save
            repo_path: Repository root path
            fragment_dir: Directory to save fragments (relative to repo_path)
            commit_hash: Commit hash to use in filename
        """
        if not fragment_dir:
            return

        dir_path = repo_path / fragment_dir
        dir_path.mkdir(exist_ok=True)
        file_path = dir_path / f"{commit_hash[:12]}.feature"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            log.info("Saved change fragment", path=str(file_path))
        except OSError as e:
            log.error("Failed to save change fragment", path=str(file_path), error=str(e))


# 🔼⚙️🔚
