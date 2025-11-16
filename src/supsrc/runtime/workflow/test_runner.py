#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

import asyncio
from pathlib import Path

from provide.foundation.logger import get_logger

log = get_logger("runtime.workflow.test_runner")


class TestRunner:
    """Handles test command inference and execution."""

    @staticmethod
    def infer_test_command(workdir: Path) -> str | None:
        """Infers a default test command based on project structure.

        Args:
            workdir: Working directory to analyze

        Returns:
            Inferred test command or None if no suitable command found
        """
        if (workdir / "pyproject.toml").exists():
            log.info("Inferred 'pytest' for Python project.", repo_path=str(workdir))
            return "pytest"
        if (workdir / "package.json").exists():
            log.info("Inferred 'npm test' for Node.js project.", repo_path=str(workdir))
            return "npm test"
        if (workdir / "go.mod").exists():
            log.info("Inferred 'go test ./...' for Go project.", repo_path=str(workdir))
            return "go test ./..."
        if (workdir / "Cargo.toml").exists():
            log.info("Inferred 'cargo test' for Rust project.", repo_path=str(workdir))
            return "cargo test"

        log.warning("Could not infer a default test command.", repo_path=str(workdir))
        return None

    @staticmethod
    async def run_tests(command: str | None, workdir: Path) -> tuple[int, str, str]:
        """Runs the configured or inferred test command.

        Args:
            command: Test command to run, or None to infer
            workdir: Working directory to run tests in

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        effective_command = command or TestRunner.infer_test_command(workdir)

        if not effective_command:
            log.warning("No test command configured or inferred, skipping tests.")
            return 0, "Skipped: No test command configured or inferred.", ""

        log.info("Running test command", command=effective_command)
        proc = await asyncio.create_subprocess_shell(
            effective_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()


# 🔼⚙️🔚
