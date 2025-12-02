#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for GitOperationsHelper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import AsyncMock, patch

from supsrc.runtime.workflow.git_operations import GitOperationsHelper


@pytest.mark.asyncio
class TestGitOperationsHelper:
    """Test suite for GitOperationsHelper class."""

    async def test_get_staged_diff_success(self):
        """Test successful staged diff retrieval."""
        workdir = Path("/test/repo")
        expected_diff = "diff --git a/file.txt b/file.txt\n+new content"

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (expected_diff.encode(), b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await GitOperationsHelper.get_staged_diff(workdir)

            assert result == expected_diff
            mock_subprocess.assert_called_once_with(
                "git diff --staged",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )

    async def test_get_staged_diff_failure(self):
        """Test staged diff retrieval failure."""
        workdir = Path("/test/repo")
        error_message = "fatal: not a git repository"

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", error_message.encode())
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await GitOperationsHelper.get_staged_diff(workdir)

            assert result == ""

    async def test_save_change_fragment_success(self, tmp_path):
        """Test successful change fragment saving."""
        repo_path = tmp_path
        fragment_dir = "fragments"
        commit_hash = "abc123def456"
        content = "Feature: Added new functionality\n\nThis change implements..."

        await GitOperationsHelper.save_change_fragment(
            content, repo_path, fragment_dir, commit_hash
        )

        # Verify directory was created
        expected_dir = repo_path / fragment_dir
        assert expected_dir.exists()

        # Verify file was created with correct content
        expected_file = expected_dir / f"{commit_hash[:12]}.feature"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == content

    async def test_save_change_fragment_no_dir(self):
        """Test change fragment saving with no directory specified."""
        repo_path = Path("/test/repo")
        fragment_dir = None
        commit_hash = "abc123def456"
        content = "Test content"

        # Should not raise any errors, just return early
        await GitOperationsHelper.save_change_fragment(
            content, repo_path, fragment_dir, commit_hash
        )

    async def test_save_change_fragment_io_error(self, tmp_path):
        """Test change fragment saving with IO error."""
        repo_path = tmp_path
        fragment_dir = "fragments"
        commit_hash = "abc123def456"
        content = "Test content"

        # Create directory but make it read-only to trigger error
        fragment_path = repo_path / fragment_dir
        fragment_path.mkdir()
        fragment_path.chmod(0o444)  # Read-only

        # Should handle the error gracefully without raising
        await GitOperationsHelper.save_change_fragment(
            content, repo_path, fragment_dir, commit_hash
        )

        # Restore permissions for cleanup
        fragment_path.chmod(0o755)

    async def test_get_staged_diff_empty_output(self):
        """Test staged diff with empty output."""
        workdir = Path("/test/repo")

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await GitOperationsHelper.get_staged_diff(workdir)

            assert result == ""


# 🔼⚙️🔚
