#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for directory management utilities."""

from __future__ import annotations

from pathlib import Path

from supsrc.utils.directories import SupsrcDirectories


class TestSupsrcDirectories:
    """Test cases for SupsrcDirectories class."""

    def test_ensure_structure_creates_all_directories(self, tmp_path: Path):
        """Test that ensure_structure creates all expected directories."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        result = SupsrcDirectories.ensure_structure(repo_path)

        # Check that all expected paths are in result
        expected_keys = {"config_dir", "local_dir", "logs_dir", "state_file", "local_state_file"}
        assert set(result.keys()) == expected_keys

        # Check that directories were created
        assert result["config_dir"].exists()
        assert result["config_dir"].is_dir()
        assert result["local_dir"].exists()
        assert result["local_dir"].is_dir()
        assert result["logs_dir"].exists()
        assert result["logs_dir"].is_dir()

        # Check directory structure
        assert result["config_dir"] == repo_path / ".supsrc"
        assert result["local_dir"] == repo_path / ".supsrc/local"
        assert result["logs_dir"] == repo_path / ".supsrc/local/logs"
        assert result["state_file"] == repo_path / ".supsrc/state.json"
        assert result["local_state_file"] == repo_path / ".supsrc/local/state.local.json"

    def test_ensure_structure_idempotent(self, tmp_path: Path):
        """Test that ensure_structure can be called multiple times safely."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Call twice
        result1 = SupsrcDirectories.ensure_structure(repo_path)
        result2 = SupsrcDirectories.ensure_structure(repo_path)

        # Results should be identical
        assert result1 == result2

        # Directories should still exist
        assert result2["config_dir"].exists()
        assert result2["local_dir"].exists()
        assert result2["logs_dir"].exists()

    def test_get_log_dir_creates_directory(self, tmp_path: Path):
        """Test that get_log_dir creates the log directory."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        log_dir = SupsrcDirectories.get_log_dir(repo_path)

        assert log_dir.exists()
        assert log_dir.is_dir()
        assert log_dir == repo_path / ".supsrc/local/logs"

    def test_get_state_file_shared(self, tmp_path: Path):
        """Test that get_state_file returns correct path for shared state."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        state_file = SupsrcDirectories.get_state_file(repo_path, local=False)

        assert state_file == repo_path / ".supsrc/state.json"
        # Parent directory should be created
        assert state_file.parent.exists()

    def test_get_state_file_local(self, tmp_path: Path):
        """Test that get_state_file returns correct path for local state."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        state_file = SupsrcDirectories.get_state_file(repo_path, local=True)

        assert state_file == repo_path / ".supsrc/local/state.local.json"
        # Parent directory should be created
        assert state_file.parent.exists()

    def test_get_config_file(self, tmp_path: Path):
        """Test that get_config_file returns correct path."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        config_file = SupsrcDirectories.get_config_file(repo_path)

        assert config_file == repo_path / ".supsrc/config.toml"
        # Parent directory should be created
        assert config_file.parent.exists()

    def test_directory_permissions(self, tmp_path: Path):
        """Test that created directories have appropriate permissions."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        result = SupsrcDirectories.ensure_structure(repo_path)

        # Check that directories are readable and writable
        for dir_path in [result["config_dir"], result["local_dir"], result["logs_dir"]]:
            assert dir_path.exists()
            assert dir_path.is_dir()
            # Test that we can create a file in the directory
            test_file = dir_path / "test.txt"
            test_file.write_text("test")
            assert test_file.exists()
            test_file.unlink()

    def test_nonexistent_repo_path(self, tmp_path: Path):
        """Test behavior with nonexistent repository path."""
        repo_path = tmp_path / "nonexistent_repo"

        # This should work - ensure_dir creates parent directories
        result = SupsrcDirectories.ensure_structure(repo_path)

        # Repository directory should have been created
        assert repo_path.exists()
        assert result["config_dir"].exists()

    def test_existing_directories_preserved(self, tmp_path: Path):
        """Test that existing directories and files are preserved."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Create some existing content
        supsrc_dir = repo_path / ".supsrc"
        supsrc_dir.mkdir()
        existing_file = supsrc_dir / "existing.txt"
        existing_file.write_text("existing content")

        result = SupsrcDirectories.ensure_structure(repo_path)

        # Existing file should be preserved
        assert existing_file.exists()
        assert existing_file.read_text() == "existing content"
        # New directories should also exist
        assert result["local_dir"].exists()
        assert result["logs_dir"].exists()


# 🔼⚙️🔚
