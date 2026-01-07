#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from pathlib import Path

from click.testing import CliRunner
from provide.testkit.mocking import Mock, patch

from supsrc.cli.main import cli


class TestSuiCommand:
    """Test the sui command functionality (interactive UI mode)."""

    def test_sui_command_exists(self) -> None:
        """Test that sui command exists in CLI."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "sui" in result.output
        # The help should indicate it's the interactive mode
        assert "Interactive" in result.output or "dashboard" in result.output.lower()

    def test_sui_help(self) -> None:
        """Test sui command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--help"])

        assert result.exit_code == 0
        assert "sui" in result.output
        assert "--config-path" in result.output
        # Should NOT have --tui flag
        assert "--tui" not in result.output

    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", True)
    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp")
    def test_sui_runs_tui(self, mock_tui_app_class: Mock, tmp_path: Path) -> None:
        """Test sui command runs the TUI application."""
        mock_app_instance = mock_tui_app_class.return_value
        mock_app_instance.run = Mock()

        config_file = tmp_path / "test.conf"
        config_file.write_text("""
        [repositories.test]
        path = "/tmp/test"
        enabled = true

        [repositories.test.rule]
        type = "supsrc.rules.inactivity"
        period = "30s"

        [repositories.test.repository]
        type = "supsrc.engines.git"
        """)

        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--config-path", str(config_file)])

        assert result.exit_code == 0
        mock_tui_app_class.assert_called_once()
        _args, kwargs = mock_tui_app_class.call_args
        assert kwargs["config_path"] == config_file
        assert "cli_shutdown_event" in kwargs
        mock_app_instance.run.assert_called_once()

    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp", None)
    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", False)
    def test_sui_without_textual(self, tmp_path: Path) -> None:
        """Test sui command when textual is not available."""
        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")

        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--config-path", str(config_file)])

        assert result.exit_code == 1
        assert "textual" in result.output.lower()
        assert "tui" in result.output.lower()  # Check for hint about [tui] extra

    def test_sui_with_invalid_config(self) -> None:
        """Test sui command with invalid config path."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--config-path", "/nonexistent/config.conf"])

        assert result.exit_code != 0

    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", True)
    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp")
    def test_sui_with_env_config(self, mock_tui_app_class: Mock, tmp_path: Path) -> None:
        """Test sui command with config from environment variable."""
        mock_app_instance = mock_tui_app_class.return_value
        mock_app_instance.run = Mock()

        config_file = tmp_path / "env_test.conf"
        config_file.write_text("""
        [repositories.env-test]
        path = "/tmp/env-test"
        enabled = true

        [repositories.env-test.rule]
        type = "supsrc.rules.manual"

        [repositories.env-test.repository]
        type = "supsrc.engines.git"
        """)

        runner = CliRunner()

        with patch.dict("os.environ", {"SUPSRC_CONF": str(config_file)}):
            result = runner.invoke(cli, ["sui"])
            assert result.exit_code == 0
            mock_tui_app_class.assert_called_once()
            _args, kwargs = mock_tui_app_class.call_args
            assert str(kwargs["config_path"]) == str(config_file)

    @patch("supsrc.cli.sui_cmds.log")
    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", True)
    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp")
    def test_sui_logging_setup(self, mock_tui_app_class: Mock, mock_log: Mock, tmp_path: Path) -> None:
        """Test that sui command sets up logging correctly."""
        mock_app_instance = mock_tui_app_class.return_value
        mock_app_instance.run = Mock()

        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")

        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--config-path", str(config_file)])

        assert result.exit_code == 0
        # Use assert_any_call to check if this was logged at any point.
        mock_log.info.assert_any_call("Initializing interactive dashboard...")

    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", True)
    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp")
    def test_sui_handles_tui_errors(self, mock_tui_app_class: Mock, tmp_path: Path) -> None:
        """Test sui command handles TUI errors gracefully."""
        mock_tui_app_class.side_effect = Exception("TUI crashed!")

        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")

        runner = CliRunner()
        # Remove the invalid mix_stderr argument from the invoke call.
        result = runner.invoke(cli, ["sui", "--config-path", str(config_file)])

        assert result.exit_code != 0
        # Check the combined output stream for the error message.
        assert "error" in result.output.lower()
        assert "crashed" in result.output.lower()

    @patch("supsrc.cli.sui_cmds.TEXTUAL_AVAILABLE", True)
    @patch("supsrc.cli.sui_cmds.SupsrcTuiApp")
    def test_sui_keyboard_interrupt(self, mock_tui_app_class: Mock, tmp_path: Path) -> None:
        """Test sui command handles keyboard interrupt gracefully."""
        mock_app_instance = mock_tui_app_class.return_value
        mock_app_instance.run.side_effect = KeyboardInterrupt()

        config_file = tmp_path / "test.conf"
        config_file.write_text("[repositories]")

        runner = CliRunner()
        result = runner.invoke(cli, ["sui", "--config-path", str(config_file)])

        assert result.exit_code == 1
        assert "aborted" in result.output.lower()


# 🔼⚙️🔚
