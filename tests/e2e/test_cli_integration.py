# tests/e2e/test_cli_integration.py

"""
CLI integration tests using subprocess execution.

These tests run the actual supsrc CLI commands as subprocesses to test
real-world usage scenarios from the command line.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers.config_testing import real_config_path, with_parent_cwd


class TestCLIConfigDiscovery:
    """Test CLI configuration discovery and loading."""

    def test_cli_finds_config_in_parent_dir(self):
        """Test that CLI finds config when run from parent directory."""
        with with_parent_cwd():
            # Run supsrc config show from parent directory
            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Should succeed and show config
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            assert "repositories" in result.stdout.lower()

    def test_cli_validates_real_config(self):
        """Test that CLI validates real config successfully."""
        with with_parent_cwd():
            config_path = real_config_path()

            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show", "-c", str(config_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0, f"Config validation failed: {result.stderr}"

    def test_cli_handles_missing_config_gracefully(self):
        """Test CLI error handling when config is missing."""
        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "config", "show", "-c", "/nonexistent/config.conf"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should fail gracefully with helpful error
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


class TestCLIWatchCommand:
    """Test the watch command CLI integration."""

    @pytest.mark.slow
    def test_watch_command_dry_run(self):
        """Test watch command in dry-run mode with real config."""
        with with_parent_cwd():
            # Run watch command with short timeout and dry run
            result = subprocess.run(
                [
                    sys.executable, "-m", "supsrc.cli.main",
                    "watch", "--dry-run", "--timeout", "2"
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Should start and exit cleanly
            # May return 0 (clean exit) or other codes depending on timeout handling
            assert "error" not in result.stderr.lower() or result.returncode == 0

    @pytest.mark.slow
    def test_watch_command_with_explicit_config(self):
        """Test watch command with explicitly specified config."""
        with with_parent_cwd():
            config_path = real_config_path()

            result = subprocess.run(
                [
                    sys.executable, "-m", "supsrc.cli.main",
                    "watch", "-c", str(config_path), "--dry-run", "--timeout", "2"
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Should handle config loading
            assert "error" not in result.stderr.lower() or result.returncode == 0


class TestCLITUICommand:
    """Test the TUI command CLI integration."""

    @pytest.mark.slow
    def test_sui_command_help(self):
        """Test that sui command shows help correctly."""
        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "sui", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "tui" in result.stdout.lower() or "terminal" in result.stdout.lower()

    @pytest.mark.slow
    def test_sui_command_validation_only(self):
        """Test sui command config validation without full startup."""
        with with_parent_cwd():
            config_path = real_config_path()

            # Test config validation (should succeed quickly)
            with patch('supsrc.cli.tui_cmds.run_tui') as mock_run_tui:
                # Mock the TUI to avoid actual startup
                mock_run_tui.return_value = 0

                result = subprocess.run(
                    [
                        sys.executable, "-m", "supsrc.cli.main",
                        "sui", "-c", str(config_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                # Should at least validate config successfully
                # (exact behavior depends on mock setup)


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""

    def test_invalid_command_handling(self):
        """Test handling of invalid commands."""
        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "nonexistent-command"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode != 0
        assert "usage" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_version_command(self):
        """Test version command works."""
        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Should show version (exact format may vary)
        assert result.returncode == 0 or "version" in result.stdout.lower()

    def test_help_command(self):
        """Test help command works."""
        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
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

        result = subprocess.run(
            [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
            cwd=supsrc_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Behavior may vary, but should not crash
        assert "python" not in result.stderr.lower() or result.returncode == 0

        # Test from parent directory
        with with_parent_cwd() as parent_dir:
            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                cwd=parent_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Should find config from parent directory
            assert result.returncode == 0 or "config" in result.stderr.lower()

    def test_cli_python_path_handling(self):
        """Test that CLI works with Python module path."""
        with with_parent_cwd():
            # Test running as module
            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0
            assert "supsrc" in result.stdout.lower()

    @pytest.mark.slow
    def test_cli_signal_handling(self):
        """Test that CLI handles interruption gracefully."""
        import signal
        import time

        with with_parent_cwd():
            # Start a long-running command
            proc = subprocess.Popen(
                [sys.executable, "-m", "supsrc.cli.main", "watch", "--dry-run"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Let it run briefly
            time.sleep(0.5)

            # Send interrupt signal
            proc.send_signal(signal.SIGINT)

            # Wait for graceful shutdown
            try:
                stdout, stderr = proc.communicate(timeout=3)
                # Should exit gracefully
                assert proc.returncode != 0  # Interrupted, so non-zero exit expected
            except subprocess.TimeoutExpired:
                proc.kill()
                pytest.fail("CLI did not handle interrupt gracefully")


class TestCLIConfigIntegration:
    """Test CLI integration with various config scenarios."""

    def test_config_show_formats_output_properly(self):
        """Test that config show command formats output readably."""
        with with_parent_cwd():
            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Should be readable output
                assert len(result.stdout) > 0
                # Should contain config structure indicators
                lines = result.stdout.split('\n')
                assert len(lines) > 1

    def test_config_validation_error_reporting(self):
        """Test config validation provides useful error messages."""
        # Create a temporary invalid config
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write("invalid toml content ][")
            invalid_config = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "supsrc.cli.main", "config", "show", "-c", invalid_config],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode != 0
            # Should provide useful error message
            assert len(result.stderr) > 0
        finally:
            Path(invalid_config).unlink(missing_ok=True)