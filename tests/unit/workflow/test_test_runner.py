#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for TestRunner."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import AsyncMock, patch

from supsrc.runtime.workflow.test_runner import TestRunner


@pytest.mark.asyncio
class TestTestRunner:
    """Test suite for TestRunner class."""


class TestTestRunnerSync:
    """Test suite for non-async TestRunner methods."""

    def test_infer_test_command_python_project(self, tmp_path):
        """Test test command inference for Python project."""
        workdir = tmp_path
        (workdir / "pyproject.toml").touch()

        result = TestRunner.infer_test_command(workdir)

        assert result == "pytest"

    def test_infer_test_command_nodejs_project(self, tmp_path):
        """Test test command inference for Node.js project."""
        workdir = tmp_path
        (workdir / "package.json").touch()

        result = TestRunner.infer_test_command(workdir)

        assert result == "npm test"

    def test_infer_test_command_go_project(self, tmp_path):
        """Test test command inference for Go project."""
        workdir = tmp_path
        (workdir / "go.mod").touch()

        result = TestRunner.infer_test_command(workdir)

        assert result == "go test ./..."

    def test_infer_test_command_rust_project(self, tmp_path):
        """Test test command inference for Rust project."""
        workdir = tmp_path
        (workdir / "Cargo.toml").touch()

        result = TestRunner.infer_test_command(workdir)

        assert result == "cargo test"

    def test_infer_test_command_unknown_project(self, tmp_path):
        """Test test command inference for unknown project type."""
        workdir = tmp_path
        # No project files

        result = TestRunner.infer_test_command(workdir)

        assert result is None

    def test_infer_test_command_multiple_project_files(self, tmp_path):
        """Test test command inference with multiple project files (precedence)."""
        workdir = tmp_path
        (workdir / "pyproject.toml").touch()
        (workdir / "package.json").touch()
        (workdir / "go.mod").touch()

        # Python should take precedence (first check)
        result = TestRunner.infer_test_command(workdir)

        assert result == "pytest"

    async def test_run_tests_with_explicit_command_success(self):
        """Test running tests with explicit command that succeeds."""
        workdir = Path("/test/repo")
        command = "custom-test-command"
        stdout_output = "All tests passed!"
        stderr_output = ""

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (stdout_output.encode(), stderr_output.encode())
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            exit_code, stdout, stderr = await TestRunner.run_tests(command, workdir)

            assert exit_code == 0
            assert stdout == stdout_output
            assert stderr == stderr_output
            mock_subprocess.assert_called_once_with(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )

    async def test_run_tests_with_explicit_command_failure(self):
        """Test running tests with explicit command that fails."""
        workdir = Path("/test/repo")
        command = "failing-test-command"
        stdout_output = "Some tests failed"
        stderr_output = "Error: test failure"

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (stdout_output.encode(), stderr_output.encode())
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            exit_code, stdout, stderr = await TestRunner.run_tests(command, workdir)

            assert exit_code == 1
            assert stdout == stdout_output
            assert stderr == stderr_output

    async def test_run_tests_with_inferred_command(self, tmp_path):
        """Test running tests with inferred command."""
        workdir = tmp_path
        (workdir / "pyproject.toml").touch()
        stdout_output = "pytest output"

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (stdout_output.encode(), b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            exit_code, stdout, _stderr = await TestRunner.run_tests(None, workdir)

            assert exit_code == 0
            assert stdout == stdout_output
            mock_subprocess.assert_called_once_with(
                "pytest",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )

    async def test_run_tests_no_command_available(self, tmp_path):
        """Test running tests when no command can be inferred."""
        workdir = tmp_path
        # No project files to infer from

        exit_code, stdout, stderr = await TestRunner.run_tests(None, workdir)

        assert exit_code == 0
        assert stdout == "Skipped: No test command configured or inferred."
        assert stderr == ""

    async def test_run_tests_returncode_none(self):
        """Test running tests when process returncode is None."""
        workdir = Path("/test/repo")
        command = "test-command"

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = None  # Simulate None returncode
            mock_subprocess.return_value = mock_process

            exit_code, _, _ = await TestRunner.run_tests(command, workdir)

            assert exit_code == 0  # Should default to 0 when returncode is None


# 🔼⚙️🔚
