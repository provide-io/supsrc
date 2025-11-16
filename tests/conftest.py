#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Enhanced pytest configuration and fixtures for comprehensive testing."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from provide.testkit.mocking import Mock

from supsrc.config import (
    GlobalConfig,
    InactivityRuleConfig,
    RepositoryConfig,
    SupsrcConfig,
    load_config,
)
from supsrc.tui.app import SupsrcTuiApp
from tests.helpers.config_testing import (
    real_config_path,
    real_repo_context,
    temp_config,
    with_parent_cwd,
)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo_path = tmp_path / "test_repo"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir()

    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"Git is not available or `git --version` failed: {e}")

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    # Configure Git user for testing (disable GPG signing to avoid issues)
    subprocess.run(["git", "config", "user.name", "Supsrc Test Bot"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@supsrc.example.com"], cwd=repo_path, check=True
    )
    # Disable GPG signing to prevent tests from failing if user has global GPG config
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "gpg.program", ""], cwd=repo_path, check=True)

    (repo_path / "README.md").write_text("initial commit")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
    return repo_path


@pytest.fixture
def minimal_config(temp_git_repo: Path) -> SupsrcConfig:
    """Create a minimal configuration for testing."""
    repo_id = "test_repo_1"
    repo_path = temp_git_repo

    return SupsrcConfig(
        global_config=GlobalConfig(),
        repositories={
            repo_id: RepositoryConfig(
                path=repo_path,
                enabled=True,
                rule=InactivityRuleConfig(period=timedelta(seconds=30)),
                repository={"type": "supsrc.engines.git", "branch": "main"},
            )
        },
    )


# Real Config Testing Fixtures


@pytest.fixture
def parent_cwd():
    """Pytest fixture for testing from parent directory context."""
    with with_parent_cwd() as parent_dir:
        yield parent_dir


@pytest.fixture
def real_config():
    """Pytest fixture providing path to real config file."""
    return real_config_path()


@pytest.fixture
def real_config_loaded(parent_cwd, real_config):
    """Pytest fixture providing loaded real config object."""
    return load_config(real_config)


@pytest.fixture
def temp_real_config(real_config):
    """Pytest fixture providing temporary copy of real config."""
    with temp_config(real_config) as tmp_config:
        yield tmp_config


@pytest.fixture
def real_repos():
    """Pytest fixture providing real repository context."""
    with real_repo_context() as repos:
        yield repos


@pytest.fixture
def tui_with_real_config(real_config):
    """Pytest fixture providing TUI app with real config setup."""
    shutdown_event = asyncio.Event()
    app = SupsrcTuiApp(real_config, shutdown_event)

    # Setup basic mocking for testing
    app.event_collector = Mock()
    app.event_collector._handlers = []
    app.event_collector.emit = Mock()

    # Mock orchestrator
    mock_orchestrator = Mock()
    mock_orchestrator._is_paused = False
    mock_orchestrator._is_suspended = False
    mock_orchestrator.repo_states = {}
    app._orchestrator = mock_orchestrator

    return app, shutdown_event


@pytest.fixture
def subprocess_runner():
    """Pytest fixture for running CLI commands using foundation's process utilities."""
    from provide.foundation.process import run_command as foundation_run_command

    def run_command(args: list[str], cwd: Path | None = None, timeout: float = 10.0):
        """Run a supsrc CLI command and return the result."""
        import sys

        full_args = [sys.executable, "-m", "supsrc.cli.main", *args]

        return foundation_run_command(
            full_args,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )

    return run_command


@pytest.fixture
def mock_tui_app_setup():
    """Pytest fixture for setting up TUI app with proper mocks."""

    def setup_app(app: SupsrcTuiApp) -> tuple[Mock, Mock]:
        # Setup event collector mock
        mock_event_collector = Mock()
        mock_event_collector._handlers = []
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        # Setup orchestrator mock
        mock_orchestrator = Mock()
        mock_orchestrator._is_paused = False
        mock_orchestrator._is_suspended = False
        mock_orchestrator.repo_states = {}
        app._orchestrator = mock_orchestrator

        return mock_event_collector, mock_orchestrator

    return setup_app


# Performance Testing Fixtures


@pytest.fixture
def performance_config(temp_git_repo):
    """Fixture for performance testing with multiple repositories."""
    repos = {}

    # Create multiple test repositories
    for i in range(5):
        repo_id = f"perf_repo_{i}"
        repos[repo_id] = RepositoryConfig(
            path=temp_git_repo,  # Reuse same repo for simplicity
            enabled=True,
            rule=InactivityRuleConfig(period=timedelta(seconds=10)),
            repository={"type": "supsrc.engines.git", "branch": "main"},
        )

    return SupsrcConfig(
        global_config=GlobalConfig(),
        repositories=repos,
    )


# Integration Testing Fixtures


@pytest.fixture
def integration_test_context(parent_cwd, real_config, real_repos):
    """Comprehensive fixture for integration testing."""
    return {
        "parent_dir": parent_cwd,
        "config_path": real_config,
        "config": load_config(real_config),
        "repositories": real_repos,
    }


# 🔼⚙️🔚
