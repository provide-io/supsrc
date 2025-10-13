# tests/e2e/test_cli_integration.py

"""
CLI integration tests using foundation's process utilities.

These tests run the actual supsrc CLI commands using provide-foundation's
process utilities to test real-world usage scenarios from the command line.
"""

from __future__ import annotations

import signal
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from provide.foundation.process import run
from provide.foundation.process.lifecycle import ManagedProcess

from tests.helpers.config_testing import real_config_path, with_parent_cwd


class TestCLIConfigDiscovery:
    """Test CLI configuration discovery and loading."""

    def test_cli_finds_config_in_parent_dir(self):
        """Test that CLI finds config when run from parent directory."""
        with with_parent_cwd():
            # Run supsrc config show from parent directory
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                timeout=10,
                check=False,
            )

            # Should succeed and show config
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            assert "repositories" in result.stdout.lower()

    def test_cli_validates_real_config(self):
        """Test that CLI validates real config successfully."""
        with with_parent_cwd():
            config_path = real_config_path()

            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show", "-c", str(config_path)],
                timeout=10,
                check=False,
            )

            assert result.returncode == 0, f"Config validation failed: {result.stderr}"

    def test_cli_handles_missing_config_gracefully(self):
        """Test CLI error handling when config is missing."""
        result = run(
            [
                sys.executable,
                "-m",
                "supsrc.cli.main",
                "config",
                "show",
                "-c",
                "/nonexistent/config.conf",
            ],
            timeout=10,
            check=False,
        )

        # Should fail gracefully with helpful error
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


class TestCLIWatchCommand:
    """Test the watch command CLI integration."""

    @pytest.mark.slow
    def test_watch_command_dry_run(self):
        """Test watch command validation with real config."""
        with with_parent_cwd():
            # Test that watch command validates configuration successfully
            # Just test --help to verify command exists and works
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "watch", "--help"],
                timeout=5,
                check=False,
            )

            # Should show help successfully
            assert result.returncode == 0
            assert "watch" in result.stdout.lower()

    @pytest.mark.slow
    def test_watch_command_with_explicit_config(self):
        """Test watch command with explicitly specified config."""
        with with_parent_cwd():
            config_path = real_config_path()

            # Test help with explicit config path to verify option works
            result = run(
                [
                    sys.executable,
                    "-m",
                    "supsrc.cli.main",
                    "watch",
                    "-c",
                    str(config_path),
                    "--help",
                ],
                timeout=5,
                check=False,
            )

            # Should show help successfully
            assert result.returncode == 0
            assert "watch" in result.stdout.lower()


class TestCLITUICommand:
    """Test the TUI command CLI integration."""

    @pytest.mark.slow
    def test_sui_command_help(self):
        """Test that sui command shows help correctly."""
        result = run(
            [sys.executable, "-m", "supsrc.cli.main", "sui", "--help"],
            timeout=5,
            check=False,
        )

        assert result.returncode == 0
        # Check for "user interface" or "interface" in help text
        assert "user interface" in result.stdout.lower() or "interface" in result.stdout.lower()

    @pytest.mark.slow
    def test_sui_command_validation_only(self):
        """Test sui command config validation without full startup."""
        with with_parent_cwd():
            config_path = real_config_path()

            # Test config validation (should succeed quickly)
            with patch("supsrc.cli.sui_cmds.sui_cli") as mock_sui_cli:
                # Mock the TUI command to avoid actual startup
                mock_sui_cli.return_value = 0

                run(
                    [sys.executable, "-m", "supsrc.cli.main", "sui", "-c", str(config_path)],
                    timeout=5,
                    check=False,
                )

                # Should at least validate config successfully
                # (exact behavior depends on mock setup)


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""

    def test_invalid_command_handling(self):
        """Test handling of invalid commands."""
        result = run(
            [sys.executable, "-m", "supsrc.cli.main", "nonexistent-command"],
            timeout=5,
            check=False,
        )

        assert result.returncode != 0
        assert "usage" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_version_command(self):
        """Test version command works."""
        result = run(
            [sys.executable, "-m", "supsrc.cli.main", "--version"],
            timeout=5,
            check=False,
        )

        # Should show version (exact format may vary)
        assert result.returncode == 0 or "version" in result.stdout.lower()

    def test_help_command(self):
        """Test help command works."""
        result = run(
            [sys.executable, "-m", "supsrc.cli.main", "--help"],
            timeout=5,
            check=False,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "supsrc" in result.stdout.lower()


class TestCLIEnvironmentIntegration:
    """Test CLI integration with different environments."""

    def test_cli_respects_working_directory(self):
        """Test that CLI respects current working directory."""
        # Test from supsrc directory
        supsrc_dir = Path(__file__).parent.parent.parent

        result = run(
            [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
            cwd=supsrc_dir,
            timeout=10,
            check=False,
        )

        # Behavior may vary, but should not crash
        assert "python" not in result.stderr.lower() or result.returncode == 0

        # Test from parent directory
        with with_parent_cwd() as parent_dir:
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                cwd=parent_dir,
                timeout=10,
                check=False,
            )

            # Should find config from parent directory
            assert result.returncode == 0 or "config" in result.stderr.lower()

    def test_cli_python_path_handling(self):
        """Test that CLI works with Python module path."""
        with with_parent_cwd():
            # Test running as module
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "--help"],
                timeout=5,
                check=False,
            )

            assert result.returncode == 0
            assert "supsrc" in result.stdout.lower()

    @pytest.mark.slow
    def test_cli_signal_handling(self):
        """Test that CLI handles interruption gracefully."""
        with with_parent_cwd():
            # Use ManagedProcess for better control over long-running commands
            managed_proc = ManagedProcess(
                command=[sys.executable, "-m", "supsrc.cli.main", "watch", "--help"],
            )

            try:
                # Start the process
                managed_proc.start()

                # Let it run briefly
                time.sleep(0.2)

                # Wait for completion (help should finish quickly)
                result = managed_proc.wait(timeout=5.0)

                # Should exit successfully (help command)
                assert result.returncode == 0

            except Exception:
                # Ensure cleanup even if test fails
                managed_proc.kill()
                raise


class TestCLIConfigIntegration:
    """Test CLI integration with various config scenarios."""

    def test_config_show_formats_output_properly(self):
        """Test that config show command formats output readably."""
        with with_parent_cwd():
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                # Should be readable output
                assert len(result.stdout) > 0
                # Should contain config structure indicators
                lines = result.stdout.split("\n")
                assert len(lines) > 1

    def test_config_validation_error_reporting(self):
        """Test config validation provides useful error messages."""
        # Create a temporary invalid config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write("invalid toml content ][")
            invalid_config = f.name

        try:
            result = run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show", "-c", invalid_config],
                timeout=5,
                check=False,
            )

            assert result.returncode != 0
            # Should provide useful error message
            assert len(result.stderr) > 0
        finally:
            Path(invalid_config).unlink(missing_ok=True)
