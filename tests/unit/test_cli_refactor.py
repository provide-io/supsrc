#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests to ensure the CLI refactoring is complete and correct."""

from click.testing import CliRunner

from supsrc.cli.main import cli


class TestCLIRefactoring:
    """Test that the CLI refactoring from old watch/tui to sui/watch is complete."""

    def test_no_tui_flag_in_any_command(self) -> None:
        """Test that --tui flag is completely removed from all commands."""
        runner = CliRunner()

        # Check main help
        result = runner.invoke(cli, ["--help"])
        assert "--tui" not in result.output

        # Check sui command help (if it exists)
        result = runner.invoke(cli, ["sui", "--help"])
        if result.exit_code == 0:
            assert "--tui" not in result.output

        # Check watch command help (if it exists)
        result = runner.invoke(cli, ["watch", "--help"])
        if result.exit_code == 0:
            assert "--tui" not in result.output

    def test_no_old_tui_command(self) -> None:
        """Test that the old 'tui' command no longer exists."""
        runner = CliRunner()

        # Try to run old tui command
        result = runner.invoke(cli, ["tui"])

        # Should fail because command doesn't exist
        assert result.exit_code != 0
        assert "No such command" in result.output or "Error" in result.output

    def test_no_tail_command(self) -> None:
        """Test that the deprecated 'tail' command no longer exists."""
        runner = CliRunner()

        # Try to run deprecated tail command
        result = runner.invoke(cli, ["tail"])

        # Should fail because command doesn't exist
        assert result.exit_code != 0
        assert "No such command" in result.output or "Error" in result.output

    def test_new_commands_exist(self) -> None:
        """Test that sui and watch commands exist."""
        runner = CliRunner()

        # Check main help
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "sui" in result.output
        assert "watch" in result.output

        # sui should be for interactive monitoring
        assert "sui" in result.output

        # watch should be for non-interactive monitoring
        assert "watch" in result.output

    def test_command_descriptions_are_clear(self) -> None:
        """Test that command descriptions clearly differentiate sui vs watch."""
        runner = CliRunner()

        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

        output = result.output

        # Find the sui and watch descriptions
        lines = output.split("\n")
        sui_desc = ""
        watch_desc = ""

        for i, line in enumerate(lines):
            if "sui" in line and i + 1 < len(lines):
                # Usually description is on same line or next line
                sui_desc = line + " " + lines[i + 1]
            if "watch" in line and "sui" not in line and i + 1 < len(lines):
                watch_desc = line + " " + lines[i + 1]

        # Ensure descriptions are different and meaningful
        assert sui_desc != watch_desc
        assert len(sui_desc) > 10  # Has actual description
        assert len(watch_desc) > 10  # Has actual description

    def test_old_watch_behavior_moved_to_watch(self) -> None:
        """Test that the old watch (non-TUI) behavior is now in watch command."""
        runner = CliRunner()

        # Test watch command has config-path option
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--config-path" in result.output

        # Test watch command doesn't have TUI-related options
        assert "--tui" not in result.output

    def test_new_sui_is_interactive_only(self) -> None:
        """Test that sui command is for interactive UI only."""
        runner = CliRunner()

        # Test sui command help mentions interactive/UI
        result = runner.invoke(cli, ["sui", "--help"])
        assert result.exit_code == 0

        # Should mention it's interactive
        assert (
            "interactive" in result.output.lower()
            or "interface" in result.output.lower()
            or "dashboard" in result.output.lower()
            or "tui" in result.output.lower()
        )


# 🔼⚙️🔚
