#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Test helpers for configuration and directory context testing.

This module provides utilities for testing supsrc with real configurations
from different directory contexts, enabling comprehensive integration testing."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest


@contextmanager
def with_parent_cwd() -> Generator[Path, None, None]:
    """
    Context manager to temporarily change to parent directory.

    This enables testing from the provide-io directory which contains
    the real supsrc.conf file for integration testing.

    Returns:
        Path to the parent directory (provide-io)
    """
    original_cwd = Path.cwd()
    parent_dir = Path(__file__).parent.parent.parent.parent

    try:
        os.chdir(parent_dir)
        yield parent_dir
    finally:
        os.chdir(original_cwd)


def real_config_path() -> Path:
    """
    Find the real supsrc.conf file in the parent directory.

    Returns:
        Path to the real configuration file

    Raises:
        pytest.skip: If config file doesn't exist (skips test instead of failing)
    """
    parent_dir = Path(__file__).parent.parent.parent.parent
    config_path = parent_dir / "supsrc.conf"

    if not config_path.exists():
        pytest.skip(f"Real config file not found at {config_path} - skipping test")

    return config_path


@contextmanager
def temp_config(base_config_path: Path | None = None) -> Generator[Path, None, None]:
    """
    Create a temporary config file based on real config for testing.

    Args:
        base_config_path: Base config to copy from (defaults to real config)

    Yields:
        Path to temporary config file
    """
    if base_config_path is None:
        base_config_path = real_config_path()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp_file:
        # Copy content from base config
        tmp_file.write(base_config_path.read_text())
        tmp_path = Path(tmp_file.name)

    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


async def wait_for_tui_ready(app, timeout: float = 5.0) -> bool:
    """
    Wait for TUI app to be ready for interaction.

    Args:
        app: The TUI application instance
        timeout: Maximum time to wait in seconds

    Returns:
        True if app is ready, False if timeout
    """
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            # Check if main widgets are available
            app.query_one("#repository_table")
            app.query_one("#event-feed")
            return True
        except Exception:
            # Wait a bit and try again
            await asyncio.sleep(0.1)

    return False


@contextmanager
def real_repo_context() -> Generator[dict[str, Path], None, None]:
    """
    Context manager providing real repository paths for testing.

    Yields:
        Dictionary with repository names and their paths
    """
    parent_dir = Path(__file__).parent.parent.parent.parent

    # Common repository locations in provide-io
    repo_paths = {
        "supsrc": parent_dir / "supsrc",
        "provide-foundation": parent_dir / "provide-foundation",
    }

    # Filter to only existing repositories
    existing_repos = {
        name: path
        for name, path in repo_paths.items()
        if path.exists() and (path / ".git").exists()
    }

    yield existing_repos


def verify_config_structure(config_path: Path) -> bool:
    """
    Verify that a config file has the expected structure.

    Args:
        config_path: Path to config file to verify

    Returns:
        True if config structure is valid
    """
    try:
        content = config_path.read_text()

        # Basic structure checks
        required_sections = ["[global]", "[repositories"]
        return all(section in content for section in required_sections)
    except Exception:
        return False


@pytest.fixture
def parent_cwd():
    """Pytest fixture for testing from parent directory."""
    with with_parent_cwd() as parent_dir:
        yield parent_dir


@pytest.fixture
def real_config():
    """Pytest fixture providing path to real config file."""
    return real_config_path()


@pytest.fixture
def temp_real_config(real_config):
    """Pytest fixture providing temporary copy of real config."""
    with temp_config(real_config) as tmp_config:
        yield tmp_config


# 🔼⚙️🔚
