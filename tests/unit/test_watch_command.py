#
# tests/unit/test_watch_command.py
#
"""
Tests for the new 'watch' command (formerly 'tail' in non-TUI mode).
"""

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from supsrc.cli.main import cli


class TestWatchCommand:
    """Test the watch command functionality."""

    def test_watch_command_exists(self) -> None:
        """Test that watch command exists in CLI."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "watch" in result.output
        assert "Watch repository changes" in result.output

    def test_watch_help(self) -> None:
        """Test watch command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "watch" in result.output
        assert "--config-path" in result.output
        assert "--tui" not in result.output

    @patch("provide.foundation.get_hub")
    @patch("supsrc.cli.watch_cmds._run_headless_orchestrator")
    @patch("supsrc.cli.watch_cmds.WatchOrchestrator")
    def test_watch_basic_operation(
        self, mock_orchestrator_class: Mock, mock_runner: Mock, mock_foundation: Mock, tmp_path: Path
    ) -> None:
        """Test watch command basic operation."""
        # Mock Foundation to avoid stream issues
        mock_hub = Mock()
        mock_foundation.return_value = mock_hub

        mock_orchestrator_instance = mock_orchestrator_class.return_value
        mock_runner.return_value = 0  # Simulate successful run
        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories.test]\npath = '/tmp/test'")
        runner = CliRunner()

        result = runner.invoke(cli, ["watch", "--config-path", str(config_file)])

        # Asserting the result's exit code is the correct way to test for success.
        assert result.exit_code == 0
        mock_orchestrator_class.assert_called_once()
        _args, kwargs = mock_orchestrator_class.call_args
        assert kwargs["config_path"] == config_file
        assert kwargs["app"] is None
        # Console is created in watch_cli, so we can't easily assert it's None
        mock_runner.assert_called_once_with(mock_orchestrator_instance)

    def test_watch_with_invalid_config(self) -> None:
        """Test watch command with invalid config path."""
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--config-path", "/nonexistent/config.conf"])
        assert result.exit_code != 0
        assert "Error" in result.output or "does not exist" in result.output

    @patch("provide.foundation.get_hub")
    @patch("supsrc.cli.watch_cmds._run_headless_orchestrator")
    @patch("supsrc.cli.watch_cmds.WatchOrchestrator")
    def test_watch_with_env_config(
        self, mock_orchestrator_class: Mock, mock_runner: Mock, mock_foundation: Mock, tmp_path: Path
    ) -> None:
        """Test watch command with config from environment variable."""
        # Mock Foundation to avoid stream issues
        mock_hub = Mock()
        mock_foundation.return_value = mock_hub

        mock_runner.return_value = 0
        config_file = tmp_path / "env_test.conf"
        config_file.write_text("[repositories.env-test]\npath = '/tmp/env-test'")
        runner = CliRunner()

        with patch.dict("os.environ", {"SUPSRC_CONF": str(config_file)}):
            result = runner.invoke(cli, ["watch"])

        assert result.exit_code == 0
        mock_orchestrator_class.assert_called_once()
        _args, kwargs = mock_orchestrator_class.call_args
        assert kwargs["config_path"] == config_file

    # Note: Logging setup is now handled by Foundation's CLI decorators
    # No need for explicit logging setup test

    @patch("provide.foundation.get_hub")
    @patch("supsrc.cli.watch_cmds._run_headless_orchestrator")
    def test_watch_runner_returns_error_code(self, mock_runner: Mock, mock_foundation: Mock, tmp_path: Path) -> None:
        """Test that a non-zero exit code from the runner is propagated."""
        # Mock Foundation to avoid stream issues
        mock_hub = Mock()
        mock_foundation.return_value = mock_hub

        mock_runner.return_value = 130  # Simulate exit code from interrupt
        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")
        runner = CliRunner()

        result = runner.invoke(cli, ["watch", "--config-path", str(config_file)])

        mock_runner.assert_called_once()
        # The CliRunner catches the sys.exit and reports the code here. This is the robust way to test it.
        assert result.exit_code == 130

    @patch("provide.foundation.get_hub")
    @patch("supsrc.cli.watch_cmds._run_headless_orchestrator")
    def test_watch_runner_raises_keyboard_interrupt(
        self, mock_runner: Mock, mock_foundation: Mock, tmp_path: Path
    ) -> None:
        """Test that watch command handles KeyboardInterrupt from the runner."""
        # Mock Foundation to avoid stream issues
        mock_hub = Mock()
        mock_foundation.return_value = mock_hub

        mock_runner.side_effect = KeyboardInterrupt()
        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")
        runner = CliRunner()

        # The runner will catch the exception and store it in the result object.
        result = runner.invoke(cli, ["watch", "--config-path", str(config_file)])

        # Click translates KeyboardInterrupt into a non-zero exit.
        # It does NOT store the exception in result.exception for this specific case.
        # Instead, it aborts execution and returns an exit code of 1.
        assert result.exit_code == 1
