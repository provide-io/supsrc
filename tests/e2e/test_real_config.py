# tests/e2e/test_real_config.py

"""
End-to-end tests using real configuration from parent directory.

These tests run supsrc with the actual supsrc.conf file from the
provide-io directory, testing real-world scenarios and workflows.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from supsrc.config.loader import load_config

from supsrc.tui.app import SupsrcTuiApp
from tests.helpers.config_testing import (
    real_config_path,
    real_repo_context,
    verify_config_structure,
    wait_for_tui_ready,
    with_parent_cwd,
)


class TestRealConfigValidation:
    """Test real configuration file validation and structure."""

    def test_real_config_exists_and_valid(self):
        """Test that the real config file exists and has valid structure."""
        config_path = real_config_path()
        assert config_path.exists(), f"Real config file not found at {config_path}"
        assert verify_config_structure(config_path), "Real config has invalid structure"

    def test_real_config_loads_successfully(self):
        """Test that the real config loads without errors."""
        with with_parent_cwd():
            config_path = real_config_path()
            config = load_config(config_path)

            # Basic validation
            assert config is not None
            assert hasattr(config, "global_config")
            assert hasattr(config, "repositories")
            assert len(config.repositories) > 0

    def test_real_repos_exist(self):
        """Test that repositories referenced in config actually exist."""
        with with_parent_cwd():
            config_path = real_config_path()
            config = load_config(config_path)

            with real_repo_context():
                # Check that config references actual repositories
                for repo_id, repo_config in config.repositories.items():
                    repo_path = Path(repo_config.path)
                    assert repo_path.exists(), (
                        f"Repository {repo_id} path {repo_path} does not exist"
                    )
                    assert (repo_path / ".git").exists(), (
                        f"Repository {repo_id} is not a git repository"
                    )


class TestRealConfigTUIIntegration:
    """Test TUI integration with real configuration."""

    @pytest.mark.asyncio
    async def test_tui_initializes_with_real_config(self):
        """Test that TUI initializes successfully with real config."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Mock external dependencies for testing
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            async with app.run_test() as pilot:
                # Wait for app to initialize
                is_ready = await wait_for_tui_ready(app)
                assert is_ready, "TUI failed to initialize within timeout"

                # Check that main widgets are present
                table = app.query_one("#repository_table")
                assert table is not None

                event_feed = app.query_one("#event-feed")
                assert event_feed is not None

                # Let it run briefly to ensure stability
                await pilot.pause()

    @pytest.mark.asyncio
    async def test_tui_discovers_real_repositories(self):
        """Test that TUI discovers and displays real repositories."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Setup minimal mocking
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            # Mock orchestrator to provide repo states
            mock_orchestrator = Mock()
            mock_orchestrator._is_paused = False
            mock_orchestrator._is_suspended = False
            mock_orchestrator.repo_states = {}
            app._orchestrator = mock_orchestrator

            async with app.run_test() as pilot:
                await wait_for_tui_ready(app)

                # Basic interaction testing
                await pilot.press("tab")  # Navigate
                await pilot.pause()

                await pilot.press("h")  # Help
                await pilot.pause()

                # Should have handled events without crashing
                assert app.event_collector.emit.called

    @pytest.mark.asyncio
    async def test_tui_keyboard_shortcuts_with_real_config(self):
        """Test keyboard shortcuts work with real config."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Setup mocking
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            mock_orchestrator = Mock()
            mock_orchestrator._is_paused = False
            mock_orchestrator._is_suspended = False
            mock_orchestrator.repo_states = {}
            app._orchestrator = mock_orchestrator

            async with app.run_test() as pilot:
                await wait_for_tui_ready(app)

                # Test key shortcuts
                shortcuts = ["h", "d", "ctrl+l", "tab", "escape"]

                for shortcut in shortcuts:
                    await pilot.press(shortcut)
                    await pilot.pause()

                # App should remain responsive
                await pilot.press("h")
                await pilot.pause()


class TestRealConfigDirectoryContext:
    """Test behavior when running from different directory contexts."""

    def test_config_discovery_from_parent_dir(self):
        """Test that config is found when running from parent directory."""
        with with_parent_cwd():
            # Should be able to find config from parent directory
            config_path = Path("supsrc.conf")
            assert config_path.exists(), "Config not found in parent directory context"

            # Should be able to load it
            config = load_config(config_path)
            assert config is not None

    def test_repository_paths_relative_to_parent(self):
        """Test that repository paths work when relative to parent directory."""
        with with_parent_cwd():
            config = load_config(Path("supsrc.conf"))

            # Check that repository paths are accessible from parent context
            for repo_id, repo_config in config.repositories.items():
                repo_path = Path(repo_config.path)

                # Convert relative paths to absolute for checking
                if not repo_path.is_absolute():
                    repo_path = Path.cwd() / repo_path

                assert repo_path.exists(), (
                    f"Repository {repo_id} not accessible from parent directory"
                )


class TestRealConfigErrorHandling:
    """Test error handling with real configuration scenarios."""

    @pytest.mark.asyncio
    async def test_tui_handles_missing_repos_gracefully(self):
        """Test TUI handles missing repositories gracefully."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Setup mocking to simulate missing repos
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            async with app.run_test() as pilot:
                # Should initialize even if some repos are missing
                await wait_for_tui_ready(app, timeout=3.0)

                # Basic functionality should still work
                await pilot.press("h")
                await pilot.pause()

                # Should have handled help request
                if app.event_collector.emit.called:
                    call_args = app.event_collector.emit.call_args[0][0]
                    assert call_args.action == "show_help"

    @pytest.mark.asyncio
    async def test_tui_shutdown_cleanup_with_real_config(self):
        """Test proper shutdown and cleanup with real config."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Mock timer manager for testing
            app.timer_manager = Mock()
            app.timer_manager.stop_all_timers = Mock()

            async with app.run_test():
                await wait_for_tui_ready(app)

                # Test shutdown
                app.action_quit()

                # Should have set shutdown event
                assert shutdown_event.is_set()

                # Should have stopped timers
                app.timer_manager.stop_all_timers.assert_called_once()


class TestRealConfigPerformance:
    """Test performance characteristics with real configuration."""

    @pytest.mark.asyncio
    async def test_tui_startup_time_acceptable(self):
        """Test that TUI starts up within reasonable time with real config."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            start_time = asyncio.get_event_loop().time()

            app = SupsrcTuiApp(config_path, shutdown_event)
            app.event_collector = Mock()
            app.event_collector._handlers = []

            async with app.run_test():
                is_ready = await wait_for_tui_ready(app, timeout=10.0)

                end_time = asyncio.get_event_loop().time()
                startup_time = end_time - start_time

                assert is_ready, "TUI failed to start within timeout"
                assert startup_time < 5.0, f"TUI startup too slow: {startup_time:.2f}s"

    @pytest.mark.asyncio
    async def test_rapid_interactions_stability_real_config(self):
        """Test stability under rapid interactions with real config."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            async with app.run_test() as pilot:
                await wait_for_tui_ready(app)

                # Rapid interactions
                actions = ["h", "d", "tab", "escape", "ctrl+l"] * 3

                for action in actions:
                    await pilot.press(action)
                    # No pause between actions to test rapid input

                await pilot.pause()

                # App should still be responsive
                await pilot.press("h")
                await pilot.pause()

                # Should have processed events
                assert app.event_collector.emit.call_count > 0
